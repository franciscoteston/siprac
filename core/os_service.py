from django.db.models import Count, OuterRef, Subquery
from django.utils import timezone

from core.models import Encaminhamento, MacroetapaLog, OS, Producao, TarefaInterna

CHAVE_ENTRADA_DIVISAO = "Entrada na Divisão"

STATUS_ATIVOS = [
    Producao.STATUS_ENTRADA,
    Producao.STATUS_DISTRIBUIDO,
    Producao.STATUS_EM_ELABORACAO,
    Producao.STATUS_PARA_REVISAO,
    Producao.STATUS_PARA_AJUSTES,
]


def derivar_macroetapa_os(os, servidor=None):
    """
    Avalia o estado das produções da OS e registra nova macroetapa
    automaticamente se necessário.
    Retorna True se houve mudança, False caso contrário.
    """
    producoes_ativas = Producao.objects.filter(os=os, status__in=STATUS_ATIVOS)

    if not producoes_ativas.exists():
        return False

    macroetapa_atual = (
        MacroetapaLog.objects.filter(os=os).order_by("-data_hora", "-id").first()
    )

    status_atual = macroetapa_atual.macroetapa if macroetapa_atual else None

    if status_atual == "ATENDIMENTO_INTERNO":
        return False

    if servidor is None:
        return False

    MacroetapaLog.objects.create(
        os=os,
        macroetapa="ATENDIMENTO_INTERNO",
        servidor=servidor,
        automatico=True,
        observacao="Derivado automaticamente: nova produção ativa registrada.",
    )
    return True


def contar_producoes_por_status_unidades(unidades_ids):
    """Contagem de produções por status para OS das unidades informadas."""
    hoje = timezone.localdate()
    resultado = {
        "ENTRADA": 0,
        "DISTRIBUIDO": 0,
        "EM_ELABORACAO": 0,
        "PARA_REVISAO": 0,
        "PARA_AJUSTES": 0,
        "HOMOLOGADO_MES": 0,
    }

    if not unidades_ids:
        return resultado

    os_ids_enc = set(
        OS.objects.filter(
            encaminhamentos__unidade_interna_destino_id__in=unidades_ids,
        ).values_list("pk", flat=True),
    )
    os_ids_tarefa = set(
        TarefaInterna.objects.filter(unidade_id__in=unidades_ids).values_list(
            "os_id",
            flat=True,
        ),
    )
    os_ids = os_ids_enc | os_ids_tarefa

    if not os_ids:
        return resultado

    queryset = Producao.objects.filter(os_id__in=os_ids).exclude(
        status=Producao.STATUS_CANCELADO,
    )

    for item in queryset.values("status").annotate(total=Count("id")):
        if item["status"] in resultado:
            resultado[item["status"]] = item["total"]

    resultado["HOMOLOGADO_MES"] = queryset.filter(
        status=Producao.STATUS_HOMOLOGADO,
        data_homologacao__year=hoje.year,
        data_homologacao__month=hoje.month,
    ).count()

    return resultado


def _queryset_os_nao_encerradas():
    ultima_macroetapa = MacroetapaLog.objects.filter(
        os_id=OuterRef("pk"),
    ).order_by("-data_hora", "-id")
    return OS.objects.annotate(
        macroetapa_atual=Subquery(ultima_macroetapa.values("macroetapa")[:1]),
    ).exclude(macroetapa_atual="ENCERRADO")


def _mapa_unidade_atual_por_os(os_ids):
    if not os_ids:
        return {}

    mapa = {}
    encaminhamentos = (
        Encaminhamento.objects.filter(
            os_id__in=os_ids,
            unidade_interna_destino__isnull=False,
        )
        .select_related("unidade_interna_destino")
        .order_by("os_id", "-data_hora", "-id")
    )
    for encaminhamento in encaminhamentos:
        if encaminhamento.os_id not in mapa:
            mapa[encaminhamento.os_id] = encaminhamento.unidade_interna_destino
    return mapa


def unidade_atual_da_os(os):
    """
    Retorna a UnidadeInterna atual da OS baseada no último encaminhamento
    interno recebido. Se não houver encaminhamento interno, retorna None
    (OS ainda não distribuída — na entrada da Divisão).
    """
    ultimo = (
        Encaminhamento.objects.filter(
            os=os,
            unidade_interna_destino__isnull=False,
        )
        .select_related("unidade_interna_destino")
        .order_by("-data_hora", "-id")
        .first()
    )
    return ultimo.unidade_interna_destino if ultimo else None


def os_ativas_por_unidade():
    """
    Retorna distribuição de OSs ativas por unidade atual.
    OSs sem encaminhamento interno aparecem como 'Entrada na Divisão'.
    """
    hoje = timezone.localdate()
    os_ids = list(_queryset_os_nao_encerradas().values_list("pk", flat=True))
    if not os_ids:
        return []

    mapa_unidade = _mapa_unidade_atual_por_os(os_ids)
    distribuicao = {}

    for os_id in os_ids:
        unidade = mapa_unidade.get(os_id)
        if unidade:
            chave = unidade.sigla
            nome = unidade.nome
        else:
            chave = CHAVE_ENTRADA_DIVISAO
            nome = CHAVE_ENTRADA_DIVISAO

        if chave not in distribuicao:
            distribuicao[chave] = {
                "nome": nome,
                "sigla": chave,
                "total": 0,
                "em_elaboracao": 0,
                "para_revisao": 0,
                "homologadas_mes": 0,
                "_os_ids": [],
            }
        distribuicao[chave]["total"] += 1
        distribuicao[chave]["_os_ids"].append(os_id)

    resultado = []
    for dados in distribuicao.values():
        os_ids_grupo = dados.pop("_os_ids")
        producoes = Producao.objects.filter(os_id__in=os_ids_grupo)
        dados["em_elaboracao"] = producoes.filter(
            status=Producao.STATUS_EM_ELABORACAO,
        ).count()
        dados["para_revisao"] = producoes.filter(
            status=Producao.STATUS_PARA_REVISAO,
        ).count()
        dados["homologadas_mes"] = producoes.filter(
            status=Producao.STATUS_HOMOLOGADO,
            data_homologacao__year=hoje.year,
            data_homologacao__month=hoje.month,
        ).count()
        resultado.append(dados)

    return sorted(resultado, key=lambda item: item["sigla"])


def os_da_unidade_atual(unidade_interna):
    """
    Retorna OSs cuja unidade atual (último encaminhamento interno)
    é a unidade informada.
    """
    if unidade_interna is None:
        return OS.objects.none()

    os_ids = list(_queryset_os_nao_encerradas().values_list("pk", flat=True))
    if not os_ids:
        return OS.objects.none()

    mapa_unidade = _mapa_unidade_atual_por_os(os_ids)
    filtrados = [
        os_id
        for os_id in os_ids
        if mapa_unidade.get(os_id)
        and mapa_unidade[os_id].pk == unidade_interna.pk
    ]
    return OS.objects.filter(pk__in=filtrados)


def contar_producoes_por_os_ids(os_ids):
    """Contagem de produções por status para as OS informadas."""
    hoje = timezone.localdate()
    resultado = {
        "ENTRADA": 0,
        "DISTRIBUIDO": 0,
        "EM_ELABORACAO": 0,
        "PARA_REVISAO": 0,
        "PARA_AJUSTES": 0,
        "HOMOLOGADO_MES": 0,
    }

    if not os_ids:
        return resultado

    queryset = Producao.objects.filter(os_id__in=os_ids).exclude(
        status=Producao.STATUS_CANCELADO,
    )

    for item in queryset.values("status").annotate(total=Count("id")):
        if item["status"] in resultado:
            resultado[item["status"]] = item["total"]

    resultado["HOMOLOGADO_MES"] = queryset.filter(
        status=Producao.STATUS_HOMOLOGADO,
        data_homologacao__year=hoje.year,
        data_homologacao__month=hoje.month,
    ).count()

    return resultado


def data_entrada_unidade(os, unidade):
    """
    Retorna a data do último encaminhamento recebido pela unidade
    para esta OS. Representa a entrada mais recente da OS na unidade.
    Retorna None se a OS nunca foi encaminhada para esta unidade.
    """
    enc = Encaminhamento.objects.filter(
        os=os,
        unidade_interna_destino=unidade,
    ).order_by("-data_hora").first()
    return enc.data_hora if enc else None


def historico_entradas_unidade(os, unidade):
    """
    Retorna todos os encaminhamentos recebidos pela unidade para
    esta OS, ordenados do mais recente para o mais antigo.
    Útil para relatório histórico de entradas e saídas.
    """
    return Encaminhamento.objects.filter(
        os=os,
        unidade_interna_destino=unidade,
    ).order_by("-data_hora")
