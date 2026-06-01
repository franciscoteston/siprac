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
