from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import OuterRef, Q, Subquery
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView

from core.mixins import RequerLoginMixin
from core.models import (
    Encaminhamento,
    MacroetapaLog,
    OS,
    OsProcesso,
    Producao,
    Servidor,
    TarefaInterna,
)


def _contexto_dashboard_vazio():
    return {
        "os_abertas": 0,
        "na_minha_fila": 0,
        "aguard_retorno": 0,
        "producao_mes": 0,
        "fila_os": [],
    }


def _obter_servidor(user):
    try:
        return user.servidor
    except Servidor.DoesNotExist:
        return None


def _obter_unidades_ativas(servidor):
    hoje = timezone.localdate()
    return servidor.vinculos_unidade.filter(
        Q(data_fim__isnull=True) | Q(data_fim__gte=hoje),
    ).values_list("unidade_id", flat=True)


def _contar_os_abertas():
    ultima_macroetapa = MacroetapaLog.objects.filter(
        os_id=OuterRef("pk"),
    ).order_by("-data_hora", "-id")

    return (
        OS.objects.annotate(
            macroetapa_atual=Subquery(ultima_macroetapa.values("macroetapa")[:1]),
        )
        .exclude(macroetapa_atual="ENCERRADO")
        .count()
    )


def _montar_fila_os(unidades_ids):
    os_ids = (
        TarefaInterna.objects.filter(unidade_id__in=unidades_ids)
        .exclude(status="CONCLUIDO")
        .values_list("os_id", flat=True)
        .distinct()
    )

    ordens = OS.objects.filter(id__in=os_ids).select_related("natureza").order_by(
        "-prioridade",
        "numero_os",
    )

    processos_principais = {
        vinculo.os_id: vinculo
        for vinculo in OsProcesso.objects.filter(
            os_id__in=os_ids,
            tipo_vinculo="PRINCIPAL",
        ).select_related("processo_sei")
    }

    macroetapas_por_os = {}
    for log in MacroetapaLog.objects.filter(os_id__in=os_ids).order_by(
        "-data_hora",
        "-id",
    ):
        if log.os_id not in macroetapas_por_os:
            macroetapas_por_os[log.os_id] = log.macroetapa

    fila_os = []
    for os_obj in ordens:
        vinculo = processos_principais.get(os_obj.id)
        fila_os.append(
            {
                "numero_os": os_obj.numero_os,
                "processo_sei": (
                    vinculo.processo_sei.numero_processo
                    if vinculo and vinculo.processo_sei
                    else "—"
                ),
                "natureza": os_obj.natureza.descricao,
                "macroetapa": macroetapas_por_os.get(os_obj.id, "—"),
                "prazo": (
                    vinculo.data_entrada_divisao
                    if vinculo and vinculo.data_entrada_divisao
                    else None
                ),
                "prioridade": os_obj.prioridade,
                "pk": os_obj.pk,
            }
        )

    return fila_os


class SipracLoginView(LoginView):
    template_name = "login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("dashboard")


class SipracLogoutView(LogoutView):
    next_page = reverse_lazy("login")


class DashboardView(RequerLoginMixin, TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        servidor = _obter_servidor(self.request.user)

        if servidor is None:
            context.update(_contexto_dashboard_vazio())
            return context

        hoje = timezone.localdate()
        unidades_ids = list(_obter_unidades_ativas(servidor))

        context["os_abertas"] = _contar_os_abertas()
        context["na_minha_fila"] = TarefaInterna.objects.filter(
            servidor=servidor,
        ).exclude(status="CONCLUIDO").count()
        context["aguard_retorno"] = Encaminhamento.objects.filter(
            aguarda_retorno=True,
            data_retorno_efetiva__isnull=True,
        ).count()
        context["producao_mes"] = Producao.objects.filter(
            data_criacao__year=hoje.year,
            data_criacao__month=hoje.month,
        ).count()
        context["fila_os"] = (
            _montar_fila_os(unidades_ids) if unidades_ids else []
        )
        return context
