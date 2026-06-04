from django.db.models import Count
from django.utils import timezone

from core.models import MacroetapaLog, OS, Producao, TarefaInterna

STATUS_ATENDIMENTO_INTERNO = [
    "ENTRADA",
    "DISTRIBUIDO",
    "EM_ELABORACAO",
    "PARA_REVISAO",
    "PARA_AJUSTES",
]

MACROETAPAS_SEM_DERIVACAO = (
    "ENCERRADO",
    "ATENDIMENTO_EXTERNO",
    "RETORNO_EXTERNO",
)


def derivar_macroetapa_os(os, servidor=None):
    """
    Avalia o estado das produções da OS e registra nova macroetapa
    automaticamente se necessário.
    Retorna True se houve mudança, False caso contrário.
    """
    producoes_ativas = Producao.objects.filter(os=os).exclude(
        status=Producao.STATUS_CANCELADO,
    )

    if not producoes_ativas.exists():
        return False

    macroetapa_atual = (
        MacroetapaLog.objects.filter(os=os).order_by("-data_hora", "-id").first()
    )

    status_atual = macroetapa_atual.macroetapa if macroetapa_atual else None

    if status_atual in MACROETAPAS_SEM_DERIVACAO:
        return False

    tem_producao_ativa = producoes_ativas.filter(
        status__in=STATUS_ATENDIMENTO_INTERNO,
    ).exists()

    if tem_producao_ativa and status_atual != "ATENDIMENTO_INTERNO":
        if servidor is None:
            return False
        MacroetapaLog.objects.create(
            os=os,
            macroetapa="ATENDIMENTO_INTERNO",
            servidor=servidor,
            automatico=True,
            observacao="Derivado automaticamente a partir do status das produções.",
        )
        return True

    return False


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
