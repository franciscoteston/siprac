from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from core.forms import EncaminhamentoForm, OSForm
from core.middleware import obter_vinculo_unidade_ativo
from core.mixins import RequerCriarOSMixin, RequerLoginJSONMixin, RequerLoginMixin
from core.models import (
    Encaminhamento,
    Finalidade,
    MacroetapaLog,
    Natureza,
    OS,
    OsImovel,
    OsProcesso,
    ProcessoSei,
    Producao,
    Servidor,
    TarefaInterna,
    TipoDemanda,
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


def _gerar_numero_os():
    ano = timezone.localdate().year
    sufixo = f"_{ano}"
    maior_sequencia = 0

    for numero in OS.objects.filter(numero_os__endswith=sufixo).values_list(
        "numero_os",
        flat=True,
    ):
        partes = numero.split("_")
        if len(partes) == 3 and partes[0] == "OS":
            try:
                maior_sequencia = max(maior_sequencia, int(partes[1]))
            except ValueError:
                continue

    return f"OS_{maior_sequencia + 1:05d}_{ano}"


def _queryset_os_anotado():
    ultima_macroetapa = MacroetapaLog.objects.filter(
        os_id=OuterRef("pk"),
    ).order_by("-data_hora", "-id")
    processo_principal = OsProcesso.objects.filter(
        os_id=OuterRef("pk"),
        tipo_vinculo="PRINCIPAL",
    )

    return OS.objects.select_related("natureza").annotate(
        macroetapa_atual=Subquery(ultima_macroetapa.values("macroetapa")[:1]),
        processo_sei_numero=Subquery(
            processo_principal.values("processo_sei__numero_processo")[:1],
        ),
        prazo=Subquery(processo_principal.values("data_entrada_divisao")[:1]),
    )


def _aplicar_visibilidade_os(queryset, request):
    perfil = getattr(request, "perfil_acesso", None)
    if perfil and perfil.visibilidade_total:
        return queryset

    servidor = _obter_servidor(request.user)
    if servidor is None:
        return queryset.none()

    unidades_ids = list(_obter_unidades_ativas(servidor))
    if not unidades_ids:
        return queryset.none()

    return queryset.filter(
        encaminhamentos__unidade_interna_destino_id__in=unidades_ids,
    ).distinct()


def _aplicar_filtros_os(queryset, request):
    macroetapa = request.GET.get("macroetapa", "").strip()
    natureza_id = request.GET.get("natureza", "").strip()
    prioridade = request.GET.get("prioridade", "").strip()
    busca_processo = request.GET.get("q", "").strip()

    if macroetapa:
        queryset = queryset.filter(macroetapa_atual=macroetapa)
    if natureza_id:
        queryset = queryset.filter(natureza_id=natureza_id)
    if prioridade:
        queryset = queryset.filter(prioridade=prioridade)
    if busca_processo:
        queryset = queryset.filter(
            processos_vinculados__processo_sei__numero_processo__icontains=busca_processo,
        ).distinct()

    return queryset


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


class OSCreateView(RequerCriarOSMixin, FormView):
    template_name = "os_form.html"
    form_class = OSForm

    def form_valid(self, form):
        servidor = _obter_servidor(self.request.user)
        if servidor is None:
            raise PermissionDenied

        with transaction.atomic():
            os_obj = OS.objects.create(
                numero_os=_gerar_numero_os(),
                data_entrada_divisao=form.cleaned_data["processo_sei_data_entrada"],
                natureza=form.cleaned_data["natureza"],
                tipo_demanda=form.cleaned_data["tipo_demanda"],
                finalidade=form.cleaned_data["finalidade"],
                prioridade=form.cleaned_data["prioridade"],
                observacao=form.cleaned_data.get("observacao") or None,
                criado_por=servidor,
            )

            processo_sei, _ = ProcessoSei.objects.get_or_create(
                numero_processo=form.cleaned_data["processo_sei_numero"],
            )

            OsProcesso.objects.create(
                os=os_obj,
                processo_sei=processo_sei,
                tipo_vinculo="PRINCIPAL",
                data_entrada_divisao=form.cleaned_data["processo_sei_data_entrada"],
            )

            MacroetapaLog.objects.create(
                os=os_obj,
                macroetapa="ENTRADA_DIVISAO",
                servidor=servidor,
                automatico=True,
            )

        return redirect(reverse("os_detalhe", kwargs={"pk": os_obj.pk}))


class OSListView(RequerLoginMixin, ListView):
    template_name = "os_list.html"
    context_object_name = "ordens"
    paginate_by = 20

    def get_queryset(self):
        queryset = _aplicar_visibilidade_os(
            _queryset_os_anotado(),
            self.request,
        )
        queryset = _aplicar_filtros_os(queryset, self.request)
        return queryset.order_by("-data_criacao_sgbd", "numero_os")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filtro_macroetapa"] = self.request.GET.get("macroetapa", "")
        context["filtro_natureza"] = self.request.GET.get("natureza", "")
        context["filtro_prioridade"] = self.request.GET.get("prioridade", "")
        context["filtro_q"] = self.request.GET.get("q", "")
        context["naturezas"] = Natureza.objects.filter(ativa=True).order_by("descricao")
        context["macroetapas"] = (
            MacroetapaLog.objects.values_list("macroetapa", flat=True)
            .distinct()
            .order_by("macroetapa")
        )
        context["prioridades"] = ["NORMAL", "PRIORITARIO", "URGENTE"]
        return context


class OSDetailView(RequerLoginMixin, DetailView):
    model = OS
    template_name = "os_detail.html"
    context_object_name = "os"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "natureza",
            "tipo_demanda",
            "finalidade",
            "criado_por",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        os_obj = self.object

        context["processos"] = OsProcesso.objects.filter(os=os_obj).select_related(
            "processo_sei",
        )
        context["macroetapas"] = MacroetapaLog.objects.filter(os=os_obj).order_by(
            "data_hora",
        )
        context["encaminhamentos"] = (
            Encaminhamento.objects.filter(os=os_obj)
            .select_related(
                "unidade_interna_origem",
                "servidor_origem",
                "unidade_interna_destino",
                "servidor_destino",
                "unidade_externa_destino",
            )
            .order_by("data_hora")
        )
        context["imoveis"] = OsImovel.objects.filter(os=os_obj).select_related("imovel")
        context["producoes"] = Producao.objects.filter(os=os_obj).select_related(
            "tipo_producao",
        )
        context["macroetapa_atual"] = (
            MacroetapaLog.objects.filter(os=os_obj)
            .order_by("-data_hora", "-id")
            .first()
        )
        return context


class EncaminhamentoCreateView(RequerLoginMixin, FormView):
    template_name = "encaminhamento_form.html"
    form_class = EncaminhamentoForm

    def dispatch(self, request, *args, **kwargs):
        self.os_obj = get_object_or_404(OS, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["os"] = self.os_obj
        return context

    def form_valid(self, form):
        servidor = _obter_servidor(self.request.user)
        if servidor is None:
            raise PermissionDenied

        vinculo = obter_vinculo_unidade_ativo(servidor)
        if vinculo is None:
            form.add_error(None, "Servidor sem vínculo ativo em unidade.")
            return self.form_invalid(form)

        agora = timezone.now()
        dados = form.cleaned_data
        tipo_destino = dados["tipo_destino"]

        with transaction.atomic():
            encaminhamento = Encaminhamento.objects.create(
                os=self.os_obj,
                unidade_interna_origem=vinculo.unidade,
                servidor_origem=servidor,
                unidade_interna_destino=dados.get("unidade_interna_destino"),
                servidor_destino=dados.get("servidor_destino"),
                unidade_externa_destino=dados.get("unidade_externa_destino"),
                etapa_interna=dados["etapa_interna"],
                tipo_acao=dados["tipo_acao"],
                aguarda_retorno=dados.get("aguarda_retorno") or False,
                data_retorno_prevista=dados.get("data_retorno_prevista"),
                observacao=dados.get("observacao") or None,
            )

            if tipo_destino == "INTERNO":
                unidade_tarefa = dados["unidade_interna_destino"]
                servidor_tarefa = dados.get("servidor_destino") or servidor
            else:
                unidade_tarefa = vinculo.unidade
                servidor_tarefa = servidor

            TarefaInterna.objects.create(
                os=self.os_obj,
                encaminhamento=encaminhamento,
                unidade=unidade_tarefa,
                servidor=servidor_tarefa,
                etapa_interna=dados["etapa_interna"],
                status="PENDENTE",
                data_inicio=agora,
            )

            if tipo_destino == "INTERNO":
                MacroetapaLog.objects.create(
                    os=self.os_obj,
                    macroetapa="ATENDIMENTO_INTERNO",
                    servidor=servidor,
                    automatico=True,
                )
            elif dados.get("aguarda_retorno"):
                MacroetapaLog.objects.create(
                    os=self.os_obj,
                    macroetapa="ATENDIMENTO_EXTERNO",
                    servidor=servidor,
                    automatico=True,
                )

        return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))


class TiposDemandaAPIView(RequerLoginJSONMixin, View):
    def get(self, request):
        natureza_id = request.GET.get("natureza_id")
        if not natureza_id:
            return JsonResponse([], safe=False)

        tipos = list(
            TipoDemanda.objects.filter(
                combinacoes_validas__natureza_id=natureza_id,
                ativa=True,
            )
            .distinct()
            .order_by("descricao")
            .values("id", "descricao")
        )
        return JsonResponse(tipos, safe=False)


class FinalidadesAPIView(RequerLoginJSONMixin, View):
    def get(self, request):
        tipo_demanda_id = request.GET.get("tipo_demanda_id")
        if not tipo_demanda_id:
            return JsonResponse([], safe=False)

        finalidades = list(
            Finalidade.objects.filter(
                combinacoes_validas__tipo_demanda_id=tipo_demanda_id,
                ativa=True,
            )
            .distinct()
            .order_by("descricao")
            .values("id", "descricao")
        )
        return JsonResponse(finalidades, safe=False)
