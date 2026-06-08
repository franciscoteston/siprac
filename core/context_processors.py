from core.models import Servidor


def siprac_navbar(request):
    context = {"vinculo_navbar": None}
    if not request.user.is_authenticated:
        return context

    try:
        servidor = request.user.servidor
    except Servidor.DoesNotExist:
        return context

    vinculo = (
        servidor.vinculos_unidade.filter(data_fim__isnull=True)
        .select_related("unidade", "perfil")
        .order_by("-perfil__pode_homologar")
        .first()
    )
    if vinculo:
        context["vinculo_navbar"] = vinculo
    return context
