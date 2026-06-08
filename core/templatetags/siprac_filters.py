from django import template

register = template.Library()

PRIORIDADE_LABELS = {
    "NORMAL": "Normal",
    "PRIORITARIO": "Prioritário",
    "URGENTE": "Urgente",
}

MACROETAPA_LABELS = {
    "ENTRADA_DIVISAO": "Entrada na Divisão",
    "ATENDIMENTO_INTERNO": "Atendimento Interno",
    "ATENDIMENTO_EXTERNO": "Atendimento Externo",
    "RETORNO_EXTERNO": "Retorno Externo",
    "INCLUSAO_PROCESSO_RELACIONADO": "Inclusão de Processo Relacionado",
    "REABERTURA": "Reabertura",
    "ENCERRADO": "Encerrado na Divisão",
}


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return None
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def prioridade_display(value):
    if not value:
        return "—"
    return PRIORIDADE_LABELS.get(value, value)


@register.filter
def macroetapa_display(value):
    if not value:
        return "—"
    return MACROETAPA_LABELS.get(value, value)


STATUS_PRODUCAO_LABELS = {
    "ENTRADA": "Entrada",
    "DISTRIBUIDO": "Distribuído",
    "EM_ELABORACAO": "Em elaboração",
    "PARA_REVISAO": "Para revisão",
    "PARA_AJUSTES": "Para ajustes",
    "HOMOLOGADO": "Homologado",
    "CANCELADO": "Cancelado",
}

STATUS_PRODUCAO_CORES = {
    "ENTRADA": "secondary",
    "DISTRIBUIDO": "info",
    "EM_ELABORACAO": "primary",
    "PARA_REVISAO": "warning",
    "PARA_AJUSTES": "warning",
    "HOMOLOGADO": "success",
    "CANCELADO": "danger",
}

GRUPO_BADGE_CLASSES = (
    "text-bg-primary",
    "text-bg-success",
    "text-bg-info",
    "text-bg-warning",
    "text-bg-danger",
)

GRUPO_CORES_FUNDO = (
    "#cfe2ff",
    "#d1e7dd",
    "#cff4fc",
    "#fff3cd",
    "#f8d7da",
)


@register.filter
def status_producao_display(value):
    if not value:
        return "—"
    return STATUS_PRODUCAO_LABELS.get(value, value)


@register.filter
def status_producao_cor(value):
    if not value:
        return "secondary"
    return STATUS_PRODUCAO_CORES.get(value, "secondary")


NATUREZA_BADGE_CLASSES = (
    "text-bg-primary",
    "text-bg-success",
    "text-bg-info",
    "text-bg-warning",
    "text-bg-danger",
)


@register.filter
def natureza_badge_class(natureza_id):
    if not natureza_id:
        return "text-bg-secondary"
    try:
        return NATUREZA_BADGE_CLASSES[(int(natureza_id) - 1) % len(NATUREZA_BADGE_CLASSES)]
    except (ValueError, TypeError):
        return "text-bg-secondary"


@register.filter
def grupo_badge_class(grupo_ref):
    if not grupo_ref:
        return "text-bg-secondary"
    try:
        numero = int(str(grupo_ref).replace("G", ""))
        return GRUPO_BADGE_CLASSES[(numero - 1) % len(GRUPO_BADGE_CLASSES)]
    except (ValueError, TypeError):
        return "text-bg-dark"


@register.filter
def grupo_cor_fundo(grupo_ref):
    if not grupo_ref:
        return ""
    try:
        numero = int(str(grupo_ref).replace("G", ""))
        return GRUPO_CORES_FUNDO[(numero - 1) % len(GRUPO_CORES_FUNDO)]
    except (ValueError, TypeError):
        return "#f8f9fa"


@register.filter
def decimal_br(value):
    """Formata decimal no padrão brasileiro: 492000.00 → 492.000,00"""
    if value is None:
        return "—"
    try:
        from decimal import Decimal

        value = Decimal(str(value))
        parts = f"{value:,.2f}".split(".")
        inteiro = parts[0].replace(",", ".")
        decimal = parts[1]
        return f"{inteiro},{decimal}"
    except Exception:
        return value


@register.filter
def decimal_br_simples(value):
    """Formata decimal sem casas decimais: 492000.00 → 492.000"""
    if value is None:
        return "—"
    try:
        from decimal import Decimal

        value = Decimal(str(value))
        return f"{int(value):,}".replace(",", ".")
    except Exception:
        return value
