from core.models import Servidor

PENDENCIAS_VAZIAS = {
    "total": 0,
    "os_novas": 0,
}


def siprac_navbar(request):
    context = {
        "vinculo_navbar": None,
        "pendencias": PENDENCIAS_VAZIAS,
    }
    if not request.user.is_authenticated:
        return context

    try:
        servidor = request.user.servidor
    except Servidor.DoesNotExist:
        return context

    vinculo = getattr(request, "vinculo_ativo", None)
    if vinculo is None:
        vinculo = (
            servidor.vinculos_unidade.filter(data_fim__isnull=True)
            .select_related("unidade", "perfil")
            .order_by("-perfil__pode_homologar")
            .first()
        )
    if vinculo:
        context["vinculo_navbar"] = vinculo

    try:
        from core.os_service import itens_pendentes_usuario

        if servidor:
            context["pendencias"] = itens_pendentes_usuario(servidor)
    except Exception:
        context["pendencias"] = PENDENCIAS_VAZIAS

    return context
