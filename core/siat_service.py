import datetime
import os

from django.db.models import Exists, OuterRef

from core.models import Imovel, ImovelVersao, OsImovel, ProducaoImovel
from core.siat_parser import SIAT_COLUMN_MAP, parse_linha_siat, parse_siat_file

CAMPOS_CABECALHO_ESPERADOS = ("NUM_BLOCO", "NUM_INSCRICAO", "NME_ENDLOC_LOGRADOURO")

CAMPOS_VERSAO_SIAT = (
    "num_bloco",
    "cod_logradouro",
    "nom_logradouro",
    "num_endereco",
    "num_unidade",
    "bairro",
    "des_finalidade",
    "area_territorial",
    "area_construida",
    "rh_nome",
    "rh_valor",
    "idf_regiao_homogenea",
    "latitude",
    "longitude",
    "coord_x",
    "coord_y",
)


def carregar_arquivo_siat(filepath):
    """
    Valida o arquivo SIAT e o disponibiliza para consultas.
    NÃO importa registros para o banco.
    Retorna dict com informações do arquivo.
    """
    if not os.path.exists(filepath):
        return {"valido": False, "erro": "Arquivo não encontrado."}

    with open(filepath, "r", encoding="utf-8", errors="replace") as arquivo:
        cabecalho = arquivo.readline()
        total_linhas = sum(1 for _ in arquivo)

    campos_presentes = [campo in cabecalho for campo in CAMPOS_CABECALHO_ESPERADOS]
    if not all(campos_presentes):
        return {"valido": False, "erro": "Formato de arquivo inválido."}

    return {
        "valido": True,
        "total_registros": total_linhas,
        "data_arquivo": datetime.date.today(),
    }


def obter_status_arquivo_siat(filepath):
    """Retorna informações do arquivo SIAT disponível para consulta."""
    if not os.path.exists(filepath):
        return {"disponivel": False}

    stat = os.stat(filepath)
    validacao = carregar_arquivo_siat(filepath)
    return {
        "disponivel": validacao.get("valido", False),
        "total_registros": validacao.get("total_registros", 0),
        "data_arquivo": validacao.get("data_arquivo"),
        "tamanho_bytes": stat.st_size,
        "modificado_em": datetime.datetime.fromtimestamp(
            stat.st_mtime,
            tz=datetime.timezone.utc,
        ).isoformat(),
        "erro": validacao.get("erro"),
    }


def _defaults_versao_siat(dados_siat):
    defaults = {campo: dados_siat.get(campo) for campo in CAMPOS_VERSAO_SIAT}
    defaults["origem_dados"] = "SIAT"
    return defaults


def obter_ou_criar_versao(dados_siat):
    """
    Busca ou cria Imovel + ImovelVersao a partir dos dados do arquivo SIAT.
    Retorna tupla (imovel, imovel_versao, criado).
    """
    inscricao = dados_siat.get("inscricao_cadastral")
    exercicio = dados_siat.get("exercicio_referencia")
    num_versao = dados_siat.get("num_versao", 0)

    imovel, _ = Imovel.objects.get_or_create(
        inscricao_cadastral=inscricao,
        defaults={"tipo_identificacao": "CADASTRAL"},
    )

    versao, criada = ImovelVersao.objects.get_or_create(
        imovel=imovel,
        exercicio=exercicio,
        num_versao=num_versao,
        defaults=_defaults_versao_siat(dados_siat),
    )

    return imovel, versao, criada


def obter_ou_criar_versao_isic(dados_manuais):
    """Cria Imovel ISIC + ImovelVersao a partir de dados manuais."""
    codigo_isic = dados_manuais.get("codigo_isic")
    imovel, _ = Imovel.objects.get_or_create(
        codigo_isic=codigo_isic,
        defaults={"tipo_identificacao": "ISIC"},
    )

    campos_versao = {
        campo: dados_manuais.get(campo)
        for campo in CAMPOS_VERSAO_SIAT
        if campo in dados_manuais
    }
    versao = ImovelVersao.objects.create(
        imovel=imovel,
        exercicio=dados_manuais.get("exercicio", datetime.date.today().year),
        num_versao=dados_manuais.get("num_versao", 0),
        origem_dados="MANUAL",
        **campos_versao,
    )

    return imovel, versao


def buscar_inscricao_no_arquivo(inscricao_cadastral, filepath):
    for registro in parse_siat_file(filepath):
        if registro.get("inscricao_cadastral") == inscricao_cadastral:
            return registro
    return None


def buscar_por_logradouro_no_arquivo(termo, filepath, limite=20):
    """
    Busca registros no arquivo SIAT por nome de logradouro ou num_bloco.
    Retorna lista de dicts com os primeiros `limite` resultados.
    """
    if not os.path.exists(filepath):
        return []

    resultados = []
    termo_upper = termo.upper()

    with open(filepath, "r", encoding="utf-8", errors="replace") as arquivo:
        cabecalho = [
            coluna.strip()
            for coluna in arquivo.readline().strip().split("|")
        ]
        for linha in arquivo:
            valores = linha.strip().split("|")
            if len(valores) < len(cabecalho):
                continue
            linha_dict = {
                cabecalho[indice]: valores[indice] if indice < len(valores) else ""
                for indice in range(len(cabecalho))
            }
            logradouro = linha_dict.get("NME_ENDLOC_LOGRADOURO", "")
            bloco = linha_dict.get("NUM_BLOCO", "")
            if termo_upper in logradouro.upper() or termo == bloco:
                registro = parse_linha_siat(cabecalho, valores)
                if registro:
                    resultados.append(registro)
                if len(resultados) >= limite:
                    break

    return resultados


def atualizar_inscricao_do_arquivo(imovel, filepath):
    if not imovel.inscricao_cadastral:
        return False

    dados = buscar_inscricao_no_arquivo(imovel.inscricao_cadastral, filepath)
    if not dados:
        return False

    obter_ou_criar_versao(dados)
    return True


def buscar_bloco_no_arquivo(num_bloco, filepath):
    num_bloco = str(num_bloco).strip()
    if not num_bloco:
        return None

    try:
        registros = [
            registro
            for registro in parse_siat_file(filepath)
            if str(registro.get("num_bloco", "")).strip() == num_bloco
        ]
    except OSError:
        return None

    return registros or None


def obter_coordenadas_bloco(num_bloco, filepath):
    registros = buscar_bloco_no_arquivo(num_bloco, filepath)
    if not registros:
        return None

    primeiro = registros[0]
    return {
        "latitude": primeiro.get("latitude"),
        "longitude": primeiro.get("longitude"),
        "coord_x": primeiro.get("coord_x"),
        "coord_y": primeiro.get("coord_y"),
    }


def queryset_imoveis_siat_orfaos():
    """Imóveis sem vínculo em OS ou produção."""
    return Imovel.objects.exclude(
        Exists(OsImovel.objects.filter(imovel_id=OuterRef("pk"))),
    ).exclude(
        Exists(ProducaoImovel.objects.filter(imovel_id=OuterRef("pk"))),
    )


def contar_imoveis_siat_orfaos():
    return queryset_imoveis_siat_orfaos().count()


def limpar_imoveis_siat_orfaos():
    queryset = queryset_imoveis_siat_orfaos()
    total = queryset.count()
    queryset.delete()
    return total
