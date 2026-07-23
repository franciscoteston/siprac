from urllib.parse import urlencode

from django.urls import reverse

from core.models import Servidor

PENDENCIAS_VAZIAS = {
    "total": 0,
    "os_novas": 0,
}

# Ordem das pills do filtro por unidade (menu lateral).
FILTRO_UNIDADE_MENU = (
    ("", "Todas"),
    ("EAV", "EAV"),
    ("ESJL", "ESJL"),
    ("EPGV", "EPGV"),
    ("DAI", "DAI"),
    ("DEPARTAMENTO", "DEPARTAMENTO"),
)

OS_URL_NAMES_MENU = frozenset({
    "os_list",
    "os_nova",
    "os_nova_passo2",
    "os_nova_passo3",
})


def _montar_pills_dashboard(request, unidade_atual):
    base = reverse("dashboard")
    pills = []
    for valor, label in FILTRO_UNIDADE_MENU:
        if valor:
            href = f"{base}?{urlencode({'unidade': valor})}"
        else:
            href = base
        pills.append({
            "valor": valor,
            "label": label,
            "href": href,
            "ativa": unidade_atual == valor,
        })
    return pills


def _montar_pills_os(request, unidade_atual):
    base = reverse("os_list")
    url_name = (
        request.resolver_match.url_name if request.resolver_match else ""
    )
    pills = []
    for valor, label in FILTRO_UNIDADE_MENU:
        if url_name == "os_list":
            params = request.GET.copy()
            params.pop("page", None)
            if getattr(request, "visibilidade", "") in ("TOTAL", "DEPARTAMENTO"):
                if not params.get("view"):
                    params["view"] = "gerencial"
            if valor:
                params["unidade"] = valor
            else:
                params.pop("unidade", None)
            qs = params.urlencode()
            href = f"{base}?{qs}" if qs else base
        else:
            params = {}
            if getattr(request, "visibilidade", "") in ("TOTAL", "DEPARTAMENTO"):
                params["view"] = "gerencial"
            if valor:
                params["unidade"] = valor
            qs = urlencode(params)
            href = f"{base}?{qs}" if qs else base
        pills.append({
            "valor": valor,
            "label": label,
            "href": href,
            "ativa": unidade_atual == valor,
        })
    return pills


def siprac_navbar(request):
    context = {
        "vinculo_navbar": None,
        "pendencias": PENDENCIAS_VAZIAS,
        "exibir_filtro_unidade_menu": False,
        "filtro_unidade_menu_atual": "",
        "mostrar_pills_dashboard": False,
        "mostrar_pills_os": False,
        "pills_filtro_dashboard": [],
        "pills_filtro_os": [],
    }
    if not request.user.is_authenticated:
        return context

    try:
        servidor = request.user.servidor
    except Servidor.DoesNotExist:
        return context

    vinculo = getattr(request, "vinculo_ativo", None)
    if vinculo is None:
        from django.db.models import Case, IntegerField, Value, When

        vinculo = (
            servidor.vinculos_unidade.filter(data_fim__isnull=True)
            .select_related("unidade", "perfil")
            .annotate(
                _ordem_vis=(
                    Case(
                        When(perfil__visibilidade="TOTAL", then=Value(0)),
                        When(perfil__visibilidade="DEPARTAMENTO", then=Value(1)),
                        When(perfil__visibilidade="UNIDADE", then=Value(2)),
                        default=Value(99),
                        output_field=IntegerField(),
                    )
                ),
            )
            .order_by("_ordem_vis", "-data_inicio")
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

    visibilidade = getattr(request, "visibilidade", "UNIDADE")
    if visibilidade in ("TOTAL", "DEPARTAMENTO"):
        unidade_atual = (request.GET.get("unidade") or "").strip()
        url_name = (
            request.resolver_match.url_name if request.resolver_match else ""
        )
        context["exibir_filtro_unidade_menu"] = True
        context["filtro_unidade_menu_atual"] = unidade_atual
        context["mostrar_pills_dashboard"] = url_name == "dashboard"
        context["mostrar_pills_os"] = url_name in OS_URL_NAMES_MENU
        context["pills_filtro_dashboard"] = _montar_pills_dashboard(
            request,
            unidade_atual,
        )
        context["pills_filtro_os"] = _montar_pills_os(request, unidade_atual)

    return context
