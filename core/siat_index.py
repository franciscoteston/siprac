import threading

from core.siat_parser import parse_linha_siat

_lock = threading.Lock()
_indice_inscricoes = {}
_indice_blocos = {}
_indice_logradouros = {}
_carregado = False


def carregar_indice(filepath):
    """Carrega índices em memória a partir do arquivo SIAT."""
    global _indice_inscricoes, _indice_blocos, _indice_logradouros, _carregado

    inscricoes = {}
    blocos = {}
    logradouros = {}

    with open(filepath, "r", encoding="utf-8", errors="replace") as arquivo:
        cabecalho = [coluna.strip() for coluna in arquivo.readline().split("|")]
        for linha in arquivo:
            campos = linha.strip().split("|")
            if len(campos) < len(cabecalho):
                continue
            raw = dict(zip(cabecalho, campos))
            dados = parse_linha_siat(cabecalho, campos)
            if not dados:
                continue

            insc = dados.get("inscricao_cadastral")
            bloco = str(raw.get("NUM_BLOCO", "")).strip()
            logr = str(raw.get("NME_ENDLOC_LOGRADOURO", "")).strip().upper()

            if insc is not None:
                inscricoes[insc] = dados
            if bloco:
                blocos.setdefault(bloco, []).append(dados)
            if logr:
                lista = logradouros.setdefault(logr, [])
                if len(lista) < 5:
                    lista.append(dados)

    with _lock:
        _indice_inscricoes = inscricoes
        _indice_blocos = blocos
        _indice_logradouros = logradouros
        _carregado = True


def indice_pronto():
    with _lock:
        return _carregado


def buscar_por_inscricao(inscricao_int):
    with _lock:
        return _indice_inscricoes.get(inscricao_int)


def buscar_por_bloco(num_bloco, limite=20):
    with _lock:
        return list(_indice_blocos.get(num_bloco, []))[:limite]


def buscar_por_logradouro(termo, limite=20):
    termo_upper = termo.upper()
    resultados = []
    with _lock:
        for logr, registros in _indice_logradouros.items():
            if termo_upper in logr:
                resultados.extend(registros[:3])
            if len(resultados) >= limite:
                break
    return resultados[:limite]
