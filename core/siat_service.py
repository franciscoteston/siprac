from django.utils import timezone

from core.models import Imovel
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


def _aplicar_dados_siat(imovel, dados):
    for campo in CAMPOS_SIAT:
        if campo in dados:
            setattr(imovel, campo, dados[campo])
    imovel.origem_dados = "SIAT"
    imovel.data_ultima_importacao = timezone.localdate()


def carregar_arquivo_siat(filepath):
    resultado = {
        "criados": 0,
        "atualizados": 0,
        "ignorados": 0,
        "erros": 0,
        "detalhes_erros": [],
    }

    try:
        registros = parse_siat_file(filepath)
    except OSError as exc:
        resultado["erros"] = 1
        resultado["detalhes_erros"].append(str(exc))
        return resultado

    for dados in registros:
        inscricao = dados.get("inscricao_cadastral")
        if not inscricao:
            resultado["erros"] += 1
            resultado["detalhes_erros"].append("Registro sem inscrição cadastral.")
            continue

        try:
            imovel = Imovel.objects.filter(inscricao_cadastral=inscricao).first()
            if imovel:
                if imovel.editado_manualmente:
                    resultado["ignorados"] += 1
                    continue
                _aplicar_dados_siat(imovel, dados)
                imovel.save()
                resultado["atualizados"] += 1
            else:
                imovel = Imovel(tipo_identificacao="CADASTRAL")
                _aplicar_dados_siat(imovel, dados)
                imovel.save()
                resultado["criados"] += 1
        except Exception as exc:
            resultado["erros"] += 1
            resultado["detalhes_erros"].append(
                f"Inscrição {inscricao}: {exc}",
            )

    return resultado


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
