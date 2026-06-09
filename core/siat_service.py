import datetime
import os

from django.db.models import Exists, OuterRef
from django.utils import timezone

from core.models import Imovel, OsImovel, ProducaoImovel
from core.siat_parser import parse_siat_file

CAMPOS_SIAT = (
    "num_bloco",
    "inscricao_cadastral",
    "cod_logradouro",
    "nom_logradouro",
    "num_endereco",
    "num_unidade",
    "bairro",
    "des_finalidade",
    "area_territorial",
    "area_construida",
    "exercicio_referencia",
    "num_versao",
    "rh_nome",
    "rh_valor",
    "idf_regiao_homogenea",
    "latitude",
    "longitude",
    "coord_x",
    "coord_y",
)

CAMPOS_CABECALHO_ESPERADOS = ("NUM_BLOCO", "NUM_INSCRICAO", "NME_ENDLOC_LOGRADOURO")


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


def _aplicar_dados_siat(imovel, dados):
    for campo in CAMPOS_SIAT:
        if campo in dados:
            setattr(imovel, campo, dados[campo])
    imovel.origem_dados = "SIAT"
    imovel.data_ultima_importacao = timezone.localdate()


def buscar_inscricao_no_arquivo(inscricao_cadastral, filepath):
    for registro in parse_siat_file(filepath):
        if registro.get("inscricao_cadastral") == inscricao_cadastral:
            return registro
    return None


def atualizar_inscricao_do_arquivo(imovel, filepath):
    if not imovel.inscricao_cadastral:
        return False

    dados = buscar_inscricao_no_arquivo(imovel.inscricao_cadastral, filepath)
    if not dados:
        return False

    _aplicar_dados_siat(imovel, dados)
    imovel.save()
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
    """Imóveis SIAT sem vínculo em OS ou produção."""
    return Imovel.objects.filter(origem_dados="SIAT").exclude(
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
