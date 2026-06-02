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
def prioridade_display(value):
    if not value:
        return "—"
    return PRIORIDADE_LABELS.get(value, value)


@register.filter
def macroetapa_display(value):
    if not value:
        return "—"
    return MACROETAPA_LABELS.get(value, value)


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
