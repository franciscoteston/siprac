import datetime
import os

from django.db.models import Exists, OuterRef

from core.models import Imovel, OsImovel
from core.siat_parser import parse_linha_siat, parse_siat_file

CAMPOS_CABECALHO_ESPERADOS = ("NUM_BLOCO", "NUM_INSCRICAO", "NME_ENDLOC_LOGRADOURO")

CAMPOS_OS_IMOVEL_SIAT = (
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
    "exercicio_referencia",
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


def vincular_imovel_a_os(os, dados_siat, servidor=None):
    """
    Vincula imóvel cadastral a uma OS com dados do SIAT.
    Cria Imovel se não existir (apenas identidade).
    Cria OsImovel com todos os dados cadastrais.
    Retorna OsImovel criado.
    """
    inscricao = dados_siat.get("inscricao_cadastral")
    imovel, _ = Imovel.objects.get_or_create(
        inscricao_cadastral=inscricao,
        defaults={"tipo_identificacao": "CADASTRAL"},
    )

    return OsImovel.objects.create(
        os=os,
        imovel=imovel,
        vinculado_por=servidor,
        num_bloco=dados_siat.get("num_bloco"),
        cod_logradouro=dados_siat.get("cod_logradouro"),
        nom_logradouro=dados_siat.get("nom_logradouro"),
        num_endereco=dados_siat.get("num_endereco"),
        num_unidade=dados_siat.get("num_unidade"),
        bairro=dados_siat.get("bairro"),
        des_finalidade=dados_siat.get("des_finalidade"),
        area_territorial=dados_siat.get("area_territorial"),
        area_construida=dados_siat.get("area_construida"),
        rh_nome=dados_siat.get("rh_nome"),
        rh_valor=dados_siat.get("rh_valor"),
        idf_regiao_homogenea=dados_siat.get("idf_regiao_homogenea"),
        latitude=dados_siat.get("latitude"),
        longitude=dados_siat.get("longitude"),
        coord_x=dados_siat.get("coord_x"),
        coord_y=dados_siat.get("coord_y"),
        exercicio_referencia=dados_siat.get("exercicio_referencia"),
        origem_dados="SIAT",
    )


def vincular_isic_a_os(os, dados_manuais, servidor=None):
    """Vincula imóvel ISIC a uma OS com dados manuais."""
    codigo_isic = dados_manuais.get("codigo_isic")
    imovel, _ = Imovel.objects.get_or_create(
        codigo_isic=codigo_isic,
        defaults={"tipo_identificacao": "ISIC"},
    )

    campos_cadastrais = {
        campo: dados_manuais.get(campo)
        for campo in CAMPOS_OS_IMOVEL_SIAT
        if campo in dados_manuais
    }

    return OsImovel.objects.create(
        os=os,
        imovel=imovel,
        vinculado_por=servidor,
        exercicio_referencia=dados_manuais.get(
            "exercicio_referencia",
            datetime.date.today().year,
        ),
        origem_dados="MANUAL",
        **campos_cadastrais,
    )


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
    """Verifica se a inscrição existe no arquivo SIAT."""
    if not imovel.inscricao_cadastral:
        return False

    dados = buscar_inscricao_no_arquivo(imovel.inscricao_cadastral, filepath)
    return dados is not None


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
    """Imóveis sem vínculo em OS."""
    return Imovel.objects.exclude(
        Exists(OsImovel.objects.filter(imovel_id=OuterRef("pk"))),
    )


def contar_imoveis_siat_orfaos():
    return queryset_imoveis_siat_orfaos().count()


def limpar_imoveis_siat_orfaos():
    queryset = queryset_imoveis_siat_orfaos()
    total = queryset.count()
    queryset.delete()
    return total
