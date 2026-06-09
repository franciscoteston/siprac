from decimal import Decimal

SIAT_COLUMN_MAP = {
    "NUM_BLOCO": "num_bloco",
    "NUM_INSCRICAO": "inscricao_cadastral",
    "COD_ENDLOC_LOGRADOURO": "cod_logradouro",
    "NME_ENDLOC_LOGRADOURO": "nom_logradouro",
    "NUM_ENDLOC_ENDERECO": "num_endereco",
    "NUM_ENDLOC_UNIDADE": "num_unidade",
    "NME_ENDLOC_BAIRRO_CDL": "bairro",
    "DES_FINALIDADE": "des_finalidade",
    "AREA_TERRITORIAL": "area_territorial",
    "AREA_CONSTRUIDA": "area_construida",
    "RH_NOME": "rh_nome",
    "RH_VALOR": "rh_valor",
    "ANO_EXERCICIO": "exercicio_referencia",
    "NUM_VERSAO": "num_versao",
    "IDF_REG_REGIAO_HOMOGENEA": "idf_regiao_homogenea",
    "LATITUDE": "latitude",
    "LONGITUDE": "longitude",
    "COORD_X": "coord_x",
    "COORD_Y": "coord_y",
}

INTEGER_FIELDS = {
    "inscricao_cadastral",
    "cod_logradouro",
    "rh_valor",
    "exercicio_referencia",
    "num_versao",
    "idf_regiao_homogenea",
}

DECIMAL_FIELDS = {
    "area_territorial",
    "area_construida",
    "latitude",
    "longitude",
    "coord_x",
    "coord_y",
}


def _normalizar_valor(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def _parse_decimal_br(valor):
    if not valor or valor.strip() == "":
        return None
    valor = valor.strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(valor)
    except Exception:
        return None


def _parse_int_br(valor):
    if not valor or valor.strip() == "":
        return None
    valor = valor.strip().replace(".", "").replace(",", ".")
    try:
        return int(float(valor))
    except Exception:
        return None


def _parse_field(campo, valor):
    if campo in INTEGER_FIELDS:
        return _parse_int_br(valor)
    if campo in DECIMAL_FIELDS:
        return _parse_decimal_br(valor)
    texto = _normalizar_valor(valor)
    return texto or None


def parse_linha_siat(cabecalho, valores):
    """Converte uma linha bruta do arquivo SIAT em dict mapeado."""
    linha_dict = {
        cabecalho[indice]: valores[indice] if indice < len(valores) else ""
        for indice in range(len(cabecalho))
    }
    registro = {}
    for coluna_siat, campo in SIAT_COLUMN_MAP.items():
        if coluna_siat not in linha_dict:
            continue
        valor = _parse_field(campo, linha_dict[coluna_siat])
        if valor is not None:
            registro[campo] = valor
    return registro


def parse_siat_file(filepath):
    """Lê arquivo SIAT delimitado por | e retorna lista de dicts mapeados."""
    registros = []

    with open(filepath, encoding="utf-8", errors="replace") as arquivo:
        linhas = [linha.rstrip("\n\r") for linha in arquivo if linha.strip()]

    if not linhas:
        return registros

    cabecalho = [_normalizar_valor(coluna) for coluna in linhas[0].split("|")]

    for linha in linhas[1:]:
        registro = parse_linha_siat(cabecalho, linha.split("|"))
        if registro:
            registros.append(registro)

    return registros
