import json
import logging
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
import datetime
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import DetailView, FormView, ListView, TemplateView

from core.forms import (
    DESPACHO_VALUE,
    EncaminhamentoForm,
    ImovelForm,
    ISICForm,
    OSEncerramentoForm,
    OSForm,
    ProducaoForm,
    SiatUploadForm,
)
from core.middleware import obter_vinculo_unidade_ativo
from core.mixins import RequerAdminMixin, RequerLoginJSONMixin, RequerLoginMixin
from core.os_service import contar_producoes_por_status_unidades, derivar_macroetapa_os
from core.siat_config import SIAT_ARQUIVO_PATH
from core.siat_service import (
    atualizar_inscricao_do_arquivo,
    carregar_arquivo_siat,
    obter_coordenadas_bloco,
)
from core.models import (
    Encaminhamento,
    Finalidade,
    Imovel,
    MacroetapaLog,
    Natureza,
    OS,
    OsImovel,
    OsProcesso,
    ProcessoSei,
    LogAuditoria,
    Producao,
    ProducaoImovel,
    ProducaoImovelDados,
    ProducaoStatusLog,
    Servidor,
    TarefaInterna,
    TipoDemanda,
    TipoProducao,
)


MSG_SEM_PERMISSAO = "Você não tem permissão para realizar esta ação."

logger = logging.getLogger(__name__)


def _contexto_dashboard_vazio():
    return {
        "os_abertas": 0,
        "na_minha_fila": 0,
        "aguard_retorno": 0,
        "producao_mes": 0,
        "fila_os": [],
        "producoes_por_status": contar_producoes_por_status_unidades([]),
    }


def _producoes_pendentes_os(os):
    """Produções ativas que ainda não foram homologadas nem canceladas."""
    return (
        Producao.objects.filter(os=os)
        .exclude(
            status__in=[Producao.STATUS_HOMOLOGADO, Producao.STATUS_CANCELADO],
        )
        .select_related("tipo_producao")
    )


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


def _obter_tipo_producao_despacho():
    tipo, _ = TipoProducao.objects.get_or_create(
        prefixo="Despacho",
        defaults={"descricao": "Despacho", "ativo": True},
    )
    return tipo


def _gerar_numero_producao(tipo_producao):
    ano = timezone.localdate().year
    prefixo = tipo_producao.prefixo
    maior_sequencia = 0

    for numero in Producao.objects.filter(
        tipo_producao=tipo_producao,
        ano=ano,
    ).exclude(numero_producao__isnull=True).exclude(numero_producao="").values_list(
        "numero_producao",
        flat=True,
    ):
        partes = numero.split("_")
        if len(partes) == 3 and partes[0] == prefixo and partes[2] == str(ano):
            try:
                maior_sequencia = max(maior_sequencia, int(partes[1]))
            except ValueError:
                continue

    return f"{prefixo}_{maior_sequencia + 1:03d}_{ano}"


def _gerar_codigo_isic():
    maior_sequencia = 0

    for codigo in Imovel.objects.exclude(codigo_isic__isnull=True).exclude(
        codigo_isic="",
    ).values_list("codigo_isic", flat=True):
        partes = codigo.split("_")
        if len(partes) == 2 and partes[0] == "ISIC":
            try:
                maior_sequencia = max(maior_sequencia, int(partes[1]))
            except ValueError:
                continue

    return f"ISIC_{maior_sequencia + 1:04d}"


def _salvar_imovel_from_form(dados, imovel=None):
    if imovel is None:
        imovel = Imovel()

    imovel.tipo_identificacao = dados["tipo_identificacao"]
    for campo in ImovelForm.CAMPOS_IMOVEL:
        valor = dados.get(campo)
        if campo == "observacao_interna":
            valor = valor or None
        elif campo == "origem_dados":
            valor = valor or "MANUAL"
        elif campo == "num_versao" and valor is None:
            valor = 0
        setattr(imovel, campo, valor)

    if dados["tipo_identificacao"] == "ISIC":
        if not imovel.codigo_isic:
            imovel.codigo_isic = _gerar_codigo_isic()
        imovel.inscricao_cadastral = None
    else:
        imovel.inscricao_cadastral = dados["inscricao_cadastral"]
        imovel.codigo_isic = None

    imovel.editado_manualmente = True
    imovel.save()
    return imovel


def _salvar_isic_from_form(dados):
    imovel = Imovel(
        tipo_identificacao="ISIC",
        codigo_isic=_gerar_codigo_isic(),
        origem_dados="MANUAL",
    )

    for campo in ISICForm.CAMPOS_ISIC:
        valor = dados.get(campo)
        if campo == "observacao_interna":
            valor = valor or None
        setattr(imovel, campo, valor)

    num_bloco = dados.get("num_bloco")
    if num_bloco and SIAT_ARQUIVO_PATH.exists():
        coordenadas = obter_coordenadas_bloco(num_bloco, SIAT_ARQUIVO_PATH)
        if coordenadas:
            for campo in ("latitude", "longitude", "coord_x", "coord_y"):
                if getattr(imovel, campo) is None and coordenadas.get(campo) is not None:
                    setattr(imovel, campo, coordenadas[campo])

    imovel.editado_manualmente = True
    imovel.save()
    return imovel


def _decimal_para_json(valor):
    return str(valor) if valor is not None else None


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

    status_producao = request.GET.get("status_producao", "").strip()
    if status_producao:
        queryset = queryset.filter(producoes__status=status_producao).distinct()

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
        context["producoes_por_status"] = contar_producoes_por_status_unidades(
            unidades_ids,
        )
        return context


class OSCreateView(RequerLoginMixin, FormView):
    template_name = "os_form.html"
    form_class = OSForm

    def dispatch(self, request, *args, **kwargs):
        perfil = getattr(request, "perfil_acesso", None)
        if perfil is None or not perfil.pode_criar_os:
            messages.error(request, MSG_SEM_PERMISSAO)
            return redirect("os_list")
        return super().dispatch(request, *args, **kwargs)

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

        messages.success(
            self.request,
            f"{os_obj.numero_os} criada com sucesso.",
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
        context["filtro_status_producao"] = self.request.GET.get("status_producao", "")
        context["naturezas"] = Natureza.objects.filter(ativa=True).order_by("descricao")
        context["status_producao_opcoes"] = Producao.STATUS_CHOICES
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
        context["imoveis"] = OsImovel.objects.filter(os=os_obj).select_related(
            "imovel",
            "vinculado_por",
        )
        context["producoes"] = Producao.objects.filter(os=os_obj).select_related(
            "tipo_producao",
        )
        context["macroetapa_atual"] = (
            MacroetapaLog.objects.filter(os=os_obj)
            .order_by("-data_hora", "-id")
            .first()
        )
        context["tem_servidor"] = _obter_servidor(self.request.user) is not None
        context["producoes_pendentes"] = _producoes_pendentes_os(os_obj)
        return context


class EncaminhamentoCreateView(RequerLoginMixin, FormView):
    template_name = "encaminhamento_form.html"
    form_class = EncaminhamentoForm

    def dispatch(self, request, *args, **kwargs):
        self.os_obj = get_object_or_404(OS, pk=kwargs["pk"])
        if _obter_servidor(request.user) is None:
            messages.error(request, MSG_SEM_PERMISSAO)
            return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["os"] = self.os_obj
        return context

    def form_valid(self, form):
        servidor = _obter_servidor(self.request.user)
        if servidor is None:
            messages.error(self.request, MSG_SEM_PERMISSAO)
            return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))

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

        messages.success(self.request, "Encaminhamento registrado.")
        return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))


class ProducaoCreateView(RequerLoginMixin, FormView):
    template_name = "producao_form.html"
    form_class = ProducaoForm

    def dispatch(self, request, *args, **kwargs):
        self.os_obj = get_object_or_404(OS, pk=kwargs["pk"])
        if _obter_servidor(request.user) is None:
            messages.error(request, MSG_SEM_PERMISSAO)
            return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["os"] = self.os_obj
        return context

    def form_valid(self, form):
        servidor = _obter_servidor(self.request.user)
        if servidor is None:
            messages.error(self.request, MSG_SEM_PERMISSAO)
            return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))

        dados = form.cleaned_data
        ano = timezone.localdate().year

        if dados.get("is_despacho"):
            tipo_producao = _obter_tipo_producao_despacho()
            numero_sei = dados["numero_sei"]
        else:
            tipo_producao = dados["tipo_producao_obj"]
            numero_sei = dados.get("numero_sei") or None

        producao = Producao.objects.create(
            os=self.os_obj,
            tipo_producao=tipo_producao,
            numero_producao=None,
            numero_sei=numero_sei,
            ano=ano,
            status=Producao.STATUS_ENTRADA,
            criado_por=servidor,
            observacao=dados.get("observacao") or None,
        )

        messages.success(self.request, "Produção registrada.")
        return redirect(reverse("producao_detail", kwargs={"pk": producao.pk}))


class OSEncerramentoView(RequerLoginMixin, FormView):
    template_name = "os_encerramento.html"
    form_class = OSEncerramentoForm

    def dispatch(self, request, *args, **kwargs):
        self.os_obj = get_object_or_404(OS, pk=kwargs["pk"])
        perfil = getattr(request, "perfil_acesso", None)
        if perfil is None or not perfil.pode_encerrar_os:
            messages.error(request, MSG_SEM_PERMISSAO)
            return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["os"] = self.os_obj
        context["processos_a_encerrar"] = OsProcesso.objects.filter(
            os=self.os_obj,
            data_encerramento__isnull=True,
        ).select_related("processo_sei")
        context["producoes_pendentes"] = _producoes_pendentes_os(self.os_obj)
        return context

    def form_valid(self, form):
        producoes_pendentes = _producoes_pendentes_os(self.os_obj)
        if producoes_pendentes.exists():
            total = producoes_pendentes.count()
            messages.error(
                self.request,
                f"Não é possível encerrar a OS. Há {total} produção(ões) "
                f"pendente(s) de homologação.",
            )
            return self.form_invalid(form)

        servidor = _obter_servidor(self.request.user)
        if servidor is None:
            messages.error(self.request, MSG_SEM_PERMISSAO)
            return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))

        hoje = timezone.localdate()
        motivo = form.cleaned_data["motivo_encerramento"]

        with transaction.atomic():
            MacroetapaLog.objects.create(
                os=self.os_obj,
                macroetapa="ENCERRADO",
                servidor=servidor,
                observacao=motivo,
            )
            OsProcesso.objects.filter(
                os=self.os_obj,
                data_encerramento__isnull=True,
            ).update(
                data_encerramento=hoje,
                motivo_encerramento=motivo,
                encerrado_por=servidor,
            )

        messages.success(self.request, "OS encerrada com sucesso.")
        return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))


class ProximoNumeroAPIView(RequerLoginJSONMixin, View):
    def get(self, request):
        tipo_id = request.GET.get("tipo_id")
        if not tipo_id or tipo_id == DESPACHO_VALUE:
            return JsonResponse({"numero": None})

        try:
            tipo_producao = TipoProducao.objects.get(pk=tipo_id, ativo=True)
        except (TipoProducao.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"error": "Tipo de produção inválido."}, status=404)

        return JsonResponse({"numero": _gerar_numero_producao(tipo_producao)})


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


class ImovelListView(RequerLoginMixin, ListView):
    model = Imovel
    template_name = "imovel_list.html"
    context_object_name = "imoveis"
    paginate_by = 20

    def get_queryset(self):
        queryset = Imovel.objects.all()
        busca = self.request.GET.get("q", "").strip()
        if busca:
            filtros = (
                Q(codigo_isic__icontains=busca)
                | Q(nom_logradouro__icontains=busca)
                | Q(bairro__icontains=busca)
                | Q(num_endereco__icontains=busca)
            )
            try:
                filtros |= Q(inscricao_cadastral=int(busca))
            except ValueError:
                pass
            queryset = queryset.filter(filtros)
        return queryset.order_by("-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filtro_q"] = self.request.GET.get("q", "")
        return context


class ImovelCreateView(RequerLoginMixin, FormView):
    template_name = "imovel_form.html"
    form_class = ISICForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["proximo_codigo_isic"] = _gerar_codigo_isic()
        return context

    def form_valid(self, form):
        imovel = _salvar_isic_from_form(form.cleaned_data)
        messages.success(self.request, "Imóvel cadastrado com sucesso.")
        return redirect(reverse("imovel_detalhe", kwargs={"pk": imovel.pk}))


class ImovelDetailView(RequerLoginMixin, DetailView):
    model = Imovel
    template_name = "imovel_detail.html"
    context_object_name = "imovel"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        imovel = self.object
        context["vinculos_os"] = (
            OsImovel.objects.filter(imovel=imovel)
            .select_related("os")
            .order_by("-os__data_criacao_sgbd")
        )
        context["vinculos_producao"] = (
            ProducaoImovel.objects.filter(imovel=imovel)
            .select_related("producao", "producao__tipo_producao", "producao__os")
            .order_by("-producao__data_criacao")
        )
        return context


class ImovelUpdateView(RequerLoginMixin, FormView):
    template_name = "imovel_edit_form.html"
    form_class = ImovelForm

    def dispatch(self, request, *args, **kwargs):
        self.imovel_obj = get_object_or_404(Imovel, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["imovel"] = self.imovel_obj
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["imovel"] = self.imovel_obj
        context["editando"] = True
        return context

    def form_valid(self, form):
        _salvar_imovel_from_form(form.cleaned_data, self.imovel_obj)
        messages.success(self.request, "Imóvel atualizado com sucesso.")
        return redirect(reverse("imovel_detalhe", kwargs={"pk": self.imovel_obj.pk}))


class ProximoIsicAPIView(RequerLoginJSONMixin, View):
    def get(self, request):
        return JsonResponse({"codigo": _gerar_codigo_isic()})


def _contexto_arquivo_siat():
    if not SIAT_ARQUIVO_PATH.exists():
        return {"arquivo_existe": False}

    stat = SIAT_ARQUIVO_PATH.stat()
    modificado = timezone.localtime(
        datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.timezone.utc),
    )
    tamanho = stat.st_size
    if tamanho >= 1024 * 1024:
        tamanho_formatado = f"{tamanho / (1024 * 1024):.1f} MB"
    elif tamanho >= 1024:
        tamanho_formatado = f"{tamanho / 1024:.1f} KB"
    else:
        tamanho_formatado = f"{tamanho} bytes"

    return {
        "arquivo_existe": True,
        "arquivo_nome": SIAT_ARQUIVO_PATH.name,
        "arquivo_modificado": modificado,
        "arquivo_tamanho": tamanho_formatado,
    }


def _processar_arquivo_siat(request):
    request.session["siat_relatorio"] = carregar_arquivo_siat(SIAT_ARQUIVO_PATH)


class SiatCarregarArquivoView(RequerAdminMixin, FormView):
    template_name = "siat_carregar.html"
    form_class = SiatUploadForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_contexto_arquivo_siat())
        context["relatorio"] = self.request.session.pop("siat_relatorio", None)
        return context

    def form_valid(self, form):
        SIAT_ARQUIVO_PATH.parent.mkdir(parents=True, exist_ok=True)
        uploaded = form.cleaned_data["arquivo"]
        with open(SIAT_ARQUIVO_PATH, "wb") as destino:
            for chunk in uploaded.chunks():
                destino.write(chunk)

        return redirect("siat_processar")


class SiatProcessarArquivoView(RequerAdminMixin, View):
    def get(self, request):
        if not SIAT_ARQUIVO_PATH.exists():
            messages.error(
                request,
                "Arquivo SIAT não encontrado em data/siat_view.txt.",
            )
            return redirect("siat_carregar")

        _processar_arquivo_siat(request)
        messages.success(request, "Arquivo SIAT processado com sucesso.")
        return redirect("siat_carregar")


class SiatAtualizarInscricaoView(RequerLoginJSONMixin, View):
    def post(self, request, inscricao):
        imovel = Imovel.objects.filter(
            inscricao_cadastral=inscricao,
            tipo_identificacao="CADASTRAL",
        ).first()
        if imovel is None:
            return JsonResponse(
                {
                    "sucesso": False,
                    "mensagem": "Imóvel cadastral não encontrado.",
                },
                status=404,
            )

        if not SIAT_ARQUIVO_PATH.exists():
            return JsonResponse(
                {
                    "sucesso": False,
                    "mensagem": "Arquivo SIAT não disponível no servidor.",
                },
                status=404,
            )

        if atualizar_inscricao_do_arquivo(imovel, SIAT_ARQUIVO_PATH):
            return JsonResponse(
                {
                    "sucesso": True,
                    "mensagem": f"Inscrição {inscricao} atualizada da View SIAT.",
                },
            )

        return JsonResponse(
            {
                "sucesso": False,
                "mensagem": f"Inscrição {inscricao} não encontrada no arquivo SIAT.",
            },
            status=404,
        )


def _formatar_identificacao_imovel(imovel):
    if imovel.inscricao_cadastral:
        return str(imovel.inscricao_cadastral)
    if imovel.codigo_isic:
        return imovel.codigo_isic
    return f"Imóvel #{imovel.pk}"


def _formatar_endereco_imovel(imovel):
    partes = []
    if imovel.nom_logradouro:
        partes.append(imovel.nom_logradouro)
    if imovel.num_endereco:
        partes.append(imovel.num_endereco)
    return ", ".join(partes)


def _proximo_grupo_ref(producao):
    grupos = (
        ProducaoImovel.objects.filter(
            producao=producao,
            grupo_ref__isnull=False,
        )
        .exclude(grupo_ref="")
        .values_list("grupo_ref", flat=True)
        .distinct()
    )
    numeros = []
    for grupo in grupos:
        try:
            numeros.append(int(str(grupo).replace("G", "")))
        except ValueError:
            pass
    proximo = max(numeros) + 1 if numeros else 1
    return f"G{proximo:02d}"


def _pode_agrupar_producao(request):
    perfil = getattr(request, "perfil_acesso", None)
    return perfil is not None and perfil.pode_homologar


def _formatar_identificacao_snap(registro):
    if registro.snap_inscricao_cadastral:
        return str(registro.snap_inscricao_cadastral)
    if registro.snap_codigo_isic:
        return registro.snap_codigo_isic
    return f"Imóvel #{registro.imovel_id}"


def _formatar_endereco_snap(registro):
    partes = []
    if registro.snap_nom_logradouro:
        partes.append(registro.snap_nom_logradouro)
    if registro.snap_num_endereco:
        partes.append(registro.snap_num_endereco)
    return ", ".join(partes) or "—"


def _formatar_area_snap(registro):
    if registro.snap_area_territorial is not None:
        return str(registro.snap_area_territorial)
    return None


def _serializar_os_imovel(vinculo):
    return {
        "imovel_id": vinculo.imovel_id,
        "identificacao": _formatar_identificacao_snap(vinculo),
        "endereco": _formatar_endereco_snap(vinculo),
        "area_territorial": _formatar_area_snap(vinculo),
    }


def _serializar_producao_imovel(item):
    return {
        "id": item.pk,
        "imovel_id": item.imovel_id,
        "identificacao": _formatar_identificacao_snap(item),
        "endereco": _formatar_endereco_snap(item),
        "area_territorial": _formatar_area_snap(item),
        "grupo_ref": item.grupo_ref or "",
    }


def _contexto_imoveis_producao(producao):
    vinculados_ids = ProducaoImovel.objects.filter(producao=producao).values_list(
        "imovel_id",
        flat=True,
    )
    imoveis_disponiveis = [
        _serializar_os_imovel(vinculo)
        for vinculo in OsImovel.objects.filter(os=producao.os)
        .exclude(imovel_id__in=vinculados_ids)
        .select_related("imovel")
        .order_by("snap_inscricao_cadastral", "snap_codigo_isic", "imovel_id")
    ]
    imoveis_producao = [
        _serializar_producao_imovel(item)
        for item in ProducaoImovel.objects.filter(producao=producao)
        .select_related("imovel")
        .order_by("grupo_ref", "pk")
    ]
    return imoveis_disponiveis, imoveis_producao


def _validar_justificativa_homologada(producao, justificativa):
    if producao.status == Producao.STATUS_HOMOLOGADO and not (justificativa or "").strip():
        return "Justificativa obrigatória para alterações em produção homologada."
    return None


def _registrar_auditoria_producao_imovel(
    servidor,
    producao_imovel,
    justificativa,
    *,
    operacao="EDICAO_POS_HOMOLOGACAO",
    campo_alterado=None,
    valor_anterior=None,
    valor_novo=None,
):
    LogAuditoria.objects.create(
        servidor=servidor,
        entidade="ProducaoImovel",
        entidade_id=producao_imovel.pk,
        operacao=operacao,
        campo_alterado=campo_alterado,
        valor_anterior=valor_anterior,
        valor_novo=valor_novo,
        justificativa=justificativa,
    )


class ProducaoDetailView(RequerLoginMixin, DetailView):
    model = Producao
    template_name = "producao_detail.html"
    context_object_name = "producao"

    def get_queryset(self):
        return Producao.objects.select_related(
            "os",
            "tipo_producao",
            "criado_por",
            "homologado_por",
            "servidor_responsavel",
            "autor_trabalho",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        producao = self.object
        imoveis = (
            ProducaoImovel.objects.filter(producao=producao)
            .select_related("imovel")
            .order_by("grupo_ref", "pk")
        )
        dados_por_exercicio = defaultdict(list)
        for dado in (
            ProducaoImovelDados.objects.filter(producao_imovel__producao=producao)
            .select_related("producao_imovel", "producao_imovel__imovel")
            .order_by("producao_imovel_id", "exercicio")
        ):
            dados_por_exercicio[dado.producao_imovel_id].append(dado)

        context["os"] = producao.os
        context["imoveis"] = imoveis
        context["dados_por_exercicio"] = dict(dados_por_exercicio)
        context["status_logs"] = (
            ProducaoStatusLog.objects.filter(producao=producao)
            .select_related(
                "servidor_origem",
                "servidor_destino",
                "unidade_destino",
            )
            .order_by("data_hora")
        )
        context["tem_servidor"] = _obter_servidor(self.request.user) is not None
        return context


TRANSICOES_PERMITIDAS_PRODUCAO = {
    Producao.STATUS_ENTRADA: [
        (Producao.STATUS_DISTRIBUIDO, True),
        (Producao.STATUS_CANCELADO, True),
    ],
    Producao.STATUS_DISTRIBUIDO: [
        (Producao.STATUS_EM_ELABORACAO, False),
        (Producao.STATUS_ENTRADA, True),
        (Producao.STATUS_CANCELADO, True),
    ],
    Producao.STATUS_EM_ELABORACAO: [
        (Producao.STATUS_PARA_REVISAO, False),
        (Producao.STATUS_CANCELADO, True),
    ],
    Producao.STATUS_PARA_REVISAO: [
        (Producao.STATUS_PARA_AJUSTES, True),
        (Producao.STATUS_HOMOLOGADO, True),
        (Producao.STATUS_EM_ELABORACAO, True),
        (Producao.STATUS_CANCELADO, True),
    ],
    Producao.STATUS_PARA_AJUSTES: [
        (Producao.STATUS_PARA_REVISAO, False),
        (Producao.STATUS_HOMOLOGADO, True),
        (Producao.STATUS_EM_ELABORACAO, True),
        (Producao.STATUS_CANCELADO, True),
    ],
}

STATUS_PRODUCAO_BOTAO_CLASSES = {
    Producao.STATUS_ENTRADA: "btn-secondary",
    Producao.STATUS_DISTRIBUIDO: "btn-primary",
    Producao.STATUS_EM_ELABORACAO: "btn-primary",
    Producao.STATUS_PARA_REVISAO: "btn-warning",
    Producao.STATUS_PARA_AJUSTES: "btn-warning btn-ajustes",
    Producao.STATUS_HOMOLOGADO: "btn-success",
    Producao.STATUS_CANCELADO: "btn-danger",
}


def _justificativa_obrigatoria_status(status_atual, status_novo):
    if status_novo == Producao.STATUS_CANCELADO:
        return True
    if status_novo == Producao.STATUS_EM_ELABORACAO and status_atual in (
        Producao.STATUS_PARA_REVISAO,
        Producao.STATUS_PARA_AJUSTES,
    ):
        return True
    return False


def _transicoes_status_disponiveis(producao, request):
    perfil = getattr(request, "perfil_acesso", None)
    pode_homologar = perfil is not None and perfil.pode_homologar
    status_atual = producao.status
    transicoes = []

    for destino, requer_homologar in TRANSICOES_PERMITIDAS_PRODUCAO.get(status_atual, []):
        if requer_homologar and not pode_homologar:
            continue
        transicoes.append(
            {
                "destino": destino,
                "label": dict(Producao.STATUS_CHOICES).get(destino, destino),
                "requer_homologar": requer_homologar,
                "justificativa_obrigatoria": _justificativa_obrigatoria_status(
                    status_atual,
                    destino,
                ),
                "botao_classe": STATUS_PRODUCAO_BOTAO_CLASSES.get(destino, "btn-secondary"),
            },
        )
    return transicoes


def _transicao_status_permitida(producao, request, status_novo):
    for transicao in _transicoes_status_disponiveis(producao, request):
        if transicao["destino"] == status_novo:
            return transicao
    return None


def _pode_redistribuir_producao(producao, request):
    perfil = getattr(request, "perfil_acesso", None)
    if perfil is None or not perfil.pode_homologar:
        return False
    return producao.status not in (
        Producao.STATUS_HOMOLOGADO,
        Producao.STATUS_CANCELADO,
    )


def _obter_servidor_responsavel_post(request):
    servidor_id = request.POST.get("servidor_responsavel")
    if not servidor_id:
        return None, "Selecione o servidor responsável."
    try:
        return Servidor.objects.get(pk=int(servidor_id)), None
    except (Servidor.DoesNotExist, ValueError, TypeError):
        return None, "Servidor responsável inválido."


def _obter_autor_trabalho_post(request):
    autor_id = request.POST.get("autor_trabalho")
    if not autor_id:
        return None, "Selecione o autor do trabalho."
    try:
        return Servidor.objects.get(pk=int(autor_id)), None
    except (Servidor.DoesNotExist, ValueError, TypeError):
        return None, "Autor do trabalho inválido."


def _criar_producao_status_log(
    producao,
    status_anterior,
    status_novo,
    servidor_origem,
    *,
    servidor_destino=None,
    unidade_destino=None,
    justificativa=None,
):
    ProducaoStatusLog.objects.create(
        producao=producao,
        status_anterior=status_anterior,
        status_novo=status_novo,
        servidor_origem=servidor_origem,
        servidor_destino=servidor_destino,
        unidade_destino=unidade_destino,
        justificativa=justificativa or None,
    )


class ProducaoAlterarStatusView(RequerLoginMixin, View):
    template_name = "producao_alterar_status.html"

    def dispatch(self, request, *args, **kwargs):
        self.producao_obj = get_object_or_404(
            Producao.objects.select_related(
                "os",
                "tipo_producao",
                "servidor_responsavel",
            ),
            pk=kwargs["pk"],
        )
        if _obter_servidor(request.user) is None:
            messages.error(request, MSG_SEM_PERMISSAO)
            return redirect(reverse("producao_detail", kwargs={"pk": self.producao_obj.pk}))
        return super().dispatch(request, *args, **kwargs)

    def _contexto_formulario(self, request):
        return {
            "producao": self.producao_obj,
            "os": self.producao_obj.os,
            "transicoes": _transicoes_status_disponiveis(self.producao_obj, request),
            "pode_redistribuir": _pode_redistribuir_producao(self.producao_obj, request),
            "servidores": Servidor.objects.order_by("nome"),
            "servidor_responsavel_atual_id": self.producao_obj.servidor_responsavel_id,
        }

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._contexto_formulario(request))

    def post(self, request, *args, **kwargs):
        servidor = _obter_servidor(request.user)
        if servidor is None:
            messages.error(request, MSG_SEM_PERMISSAO)
            return redirect(reverse("producao_detail", kwargs={"pk": self.producao_obj.pk}))

        acao = (request.POST.get("acao") or "").strip()
        justificativa = (request.POST.get("justificativa") or "").strip()

        if acao == "redistribuir":
            return self._processar_redistribuicao(request, servidor, justificativa)

        return self._processar_transicao_status(request, servidor, justificativa)

    def _processar_redistribuicao(self, request, servidor, justificativa):
        if not _pode_redistribuir_producao(self.producao_obj, request):
            messages.error(request, "Você não tem permissão para redistribuir esta produção.")
            return redirect(
                reverse("producao_alterar_status", kwargs={"pk": self.producao_obj.pk}),
            )

        novo_responsavel, erro = _obter_servidor_responsavel_post(request)
        if erro:
            messages.error(request, erro)
            return redirect(
                reverse("producao_alterar_status", kwargs={"pk": self.producao_obj.pk}),
            )

        if self.producao_obj.servidor_responsavel_id == novo_responsavel.pk:
            messages.warning(request, "O servidor selecionado já é o responsável atual.")
            return redirect(
                reverse("producao_alterar_status", kwargs={"pk": self.producao_obj.pk}),
            )

        status_atual = self.producao_obj.status
        self.producao_obj.servidor_responsavel = novo_responsavel
        self.producao_obj.save(update_fields=["servidor_responsavel"])

        _criar_producao_status_log(
            self.producao_obj,
            status_atual,
            status_atual,
            servidor,
            servidor_destino=novo_responsavel,
            justificativa=justificativa,
        )

        messages.success(
            request,
            f"Produção redistribuída para {novo_responsavel.nome}.",
        )
        return redirect(reverse("producao_detail", kwargs={"pk": self.producao_obj.pk}))

    def _processar_transicao_status(self, request, servidor, justificativa):
        status_novo = (request.POST.get("novo_status") or "").strip()
        transicao = _transicao_status_permitida(self.producao_obj, request, status_novo)

        if transicao is None:
            messages.error(request, "Transição de status não permitida.")
            return redirect(
                reverse("producao_alterar_status", kwargs={"pk": self.producao_obj.pk}),
            )

        if transicao["justificativa_obrigatoria"] and not justificativa:
            messages.error(request, "Justificativa obrigatória para esta transição.")
            return redirect(
                reverse("producao_alterar_status", kwargs={"pk": self.producao_obj.pk}),
            )

        status_anterior = self.producao_obj.status
        servidor_destino_log = self.producao_obj.servidor_responsavel
        campos_atualizar = ["status"]

        if status_novo == Producao.STATUS_DISTRIBUIDO:
            novo_responsavel, erro = _obter_servidor_responsavel_post(request)
            if erro:
                messages.error(request, erro)
                return redirect(
                    reverse("producao_alterar_status", kwargs={"pk": self.producao_obj.pk}),
                )
            self.producao_obj.servidor_responsavel = novo_responsavel
            servidor_destino_log = novo_responsavel
            campos_atualizar.append("servidor_responsavel")

        if status_novo == Producao.STATUS_HOMOLOGADO:
            autor_trabalho, erro = _obter_autor_trabalho_post(request)
            if erro:
                messages.error(request, erro)
                return redirect(
                    reverse("producao_alterar_status", kwargs={"pk": self.producao_obj.pk}),
                )
            if not self.producao_obj.numero_producao:
                self.producao_obj.numero_producao = _gerar_numero_producao(
                    self.producao_obj.tipo_producao,
                )
                campos_atualizar.append("numero_producao")
            self.producao_obj.autor_trabalho = autor_trabalho
            self.producao_obj.homologado_por = servidor
            self.producao_obj.data_homologacao = timezone.localdate()
            campos_atualizar.extend(["autor_trabalho", "homologado_por", "data_homologacao"])

        self.producao_obj.status = status_novo
        self.producao_obj.save(update_fields=campos_atualizar)

        _criar_producao_status_log(
            self.producao_obj,
            status_anterior,
            status_novo,
            servidor,
            servidor_destino=servidor_destino_log,
            justificativa=justificativa,
        )

        LogAuditoria.objects.create(
            servidor=servidor,
            entidade="Producao",
            entidade_id=self.producao_obj.pk,
            operacao="ALTERACAO_STATUS",
            campo_alterado="status",
            valor_anterior=status_anterior,
            valor_novo=status_novo,
            justificativa=justificativa or None,
        )

        messages.success(
            request,
            f"Status alterado para {dict(Producao.STATUS_CHOICES).get(status_novo, status_novo)}.",
        )
        derivar_macroetapa_os(self.producao_obj.os, servidor=servidor)
        return redirect(reverse("producao_detail", kwargs={"pk": self.producao_obj.pk}))


class ProducaoVincularImovelView(RequerLoginMixin, View):
    template_name = "producao_vincular_imovel.html"

    def dispatch(self, request, *args, **kwargs):
        self.producao_obj = get_object_or_404(
            Producao.objects.select_related("os", "tipo_producao"),
            pk=kwargs["pk"],
        )
        if _obter_servidor(request.user) is None:
            if request.content_type and "application/json" in request.content_type:
                return JsonResponse(
                    {"sucesso": False, "erro": MSG_SEM_PERMISSAO},
                    status=403,
                )
            messages.error(request, MSG_SEM_PERMISSAO)
            return redirect(reverse("producao_detail", kwargs={"pk": self.producao_obj.pk}))
        return super().dispatch(request, *args, **kwargs)

    @method_decorator(ensure_csrf_cookie)
    def get(self, request, *args, **kwargs):
        imoveis_disponiveis, imoveis_producao = _contexto_imoveis_producao(self.producao_obj)
        return render(
            request,
            self.template_name,
            {
                "producao": self.producao_obj,
                "os": self.producao_obj.os,
                "imoveis_disponiveis": imoveis_disponiveis,
                "imoveis_producao": imoveis_producao,
                "pode_agrupar": _pode_agrupar_producao(request),
                "producao_homologada": self.producao_obj.status == Producao.STATUS_HOMOLOGADO,
                "proximo_grupo_ref": _proximo_grupo_ref(self.producao_obj),
            },
        )

    def _resposta_json(self, request, *, sucesso=True, status=200, **dados):
        imoveis_disponiveis, imoveis_producao = _contexto_imoveis_producao(self.producao_obj)
        payload = {
            "sucesso": sucesso,
            "imoveis_disponiveis": imoveis_disponiveis,
            "imoveis_producao": imoveis_producao,
            "proximo_grupo_ref": _proximo_grupo_ref(self.producao_obj),
            "pode_agrupar": _pode_agrupar_producao(request),
        }
        payload.update(dados)
        return JsonResponse(payload, status=status)

    def _obter_producao_imovel(self, producao_imovel_id):
        if producao_imovel_id in (None, ""):
            return None
        try:
            producao_imovel_id = int(producao_imovel_id)
        except (TypeError, ValueError):
            return None
        return ProducaoImovel.objects.filter(
            pk=producao_imovel_id,
            producao=self.producao_obj,
        ).first()

    def _auditar_se_homologada(self, servidor, producao_imovel, justificativa, **kwargs):
        if self.producao_obj.status == Producao.STATUS_HOMOLOGADO:
            _registrar_auditoria_producao_imovel(
                servidor,
                producao_imovel,
                justificativa,
                **kwargs,
            )

    def _processar_acao(self, request, acao, servidor, justificativa):
        tipo = acao.get("tipo")
        pode_agrupar = _pode_agrupar_producao(request)

        if tipo == "vincular":
            imovel_id = acao.get("imovel_id")
            if not imovel_id:
                return {"sucesso": False, "erro": "imovel_id é obrigatório."}

            if ProducaoImovel.objects.filter(
                producao=self.producao_obj,
                imovel_id=imovel_id,
            ).exists():
                return {"sucesso": False, "erro": "Imóvel já vinculado à produção."}

            os_imovel = OsImovel.objects.filter(
                os=self.producao_obj.os,
                imovel_id=imovel_id,
            ).first()
            if os_imovel is None:
                return {"sucesso": False, "erro": "Imóvel não pertence à OS desta produção."}

            producao_imovel = ProducaoImovel.objects.create(
                producao=self.producao_obj,
                imovel_id=imovel_id,
            )
            producao_imovel.capturar_snapshot_de_osimovel(os_imovel)
            self._auditar_se_homologada(
                servidor,
                producao_imovel,
                justificativa,
                operacao="EDICAO_POS_HOMOLOGACAO",
                campo_alterado="vinculo",
                valor_novo=str(imovel_id),
            )
            return {
                "sucesso": True,
                "tipo": tipo,
                "item": _serializar_producao_imovel(producao_imovel),
            }

        if tipo in {"agrupar", "novo_grupo", "remover_grupo"}:
            if not pode_agrupar:
                return {
                    "sucesso": False,
                    "erro": "Você não tem permissão para gerenciar agrupamentos.",
                    "status": 403,
                }

        if tipo == "agrupar":
            producao_imovel = self._obter_producao_imovel(acao.get("producao_imovel_id"))
            if producao_imovel is None:
                return {"sucesso": False, "erro": "Imóvel da produção não encontrado."}
            grupo_ref = (acao.get("grupo_ref") or "").strip()
            if not grupo_ref:
                return {"sucesso": False, "erro": "grupo_ref é obrigatório."}

            valor_anterior = producao_imovel.grupo_ref
            producao_imovel.grupo_ref = grupo_ref
            producao_imovel.save(update_fields=["grupo_ref"])
            self._auditar_se_homologada(
                servidor,
                producao_imovel,
                justificativa,
                campo_alterado="grupo_ref",
                valor_anterior=valor_anterior,
                valor_novo=grupo_ref,
            )
            return {
                "sucesso": True,
                "tipo": tipo,
                "item": _serializar_producao_imovel(producao_imovel),
            }

        if tipo == "novo_grupo":
            ids = acao.get("ids") or []
            if len(ids) < 2:
                return {
                    "sucesso": False,
                    "erro": "Selecione ao menos dois imóveis para agrupar.",
                }

            ids_int = []
            for raw_id in ids:
                try:
                    ids_int.append(int(raw_id))
                except (TypeError, ValueError):
                    return {"sucesso": False, "erro": f"ID inválido: {raw_id}"}

            registros = list(
                ProducaoImovel.objects.filter(
                    producao=self.producao_obj,
                    pk__in=ids_int,
                ),
            )
            if len(registros) != len(set(ids_int)):
                return {
                    "sucesso": False,
                    "erro": "Um ou mais imóveis não pertencem a esta produção.",
                }

            grupo_ref = _proximo_grupo_ref(self.producao_obj)
            for producao_imovel in registros:
                valor_anterior = producao_imovel.grupo_ref
                self._auditar_se_homologada(
                    servidor,
                    producao_imovel,
                    justificativa,
                    campo_alterado="grupo_ref",
                    valor_anterior=valor_anterior,
                    valor_novo=grupo_ref,
                )

            atualizados = ProducaoImovel.objects.filter(
                producao=self.producao_obj,
                pk__in=ids_int,
            ).update(grupo_ref=grupo_ref)
            logger.info(
                "novo_grupo producao=%s grupo_ref=%s ids=%s atualizados=%s",
                self.producao_obj.pk,
                grupo_ref,
                ids_int,
                atualizados,
            )
            itens = [
                _serializar_producao_imovel(item)
                for item in ProducaoImovel.objects.filter(
                    producao=self.producao_obj,
                    pk__in=ids_int,
                ).order_by("pk")
            ]
            return {
                "sucesso": True,
                "tipo": tipo,
                "grupo_ref": grupo_ref,
                "ids_atualizados": ids_int,
                "itens": itens,
            }

        if tipo == "remover_grupo":
            producao_imovel = self._obter_producao_imovel(acao.get("producao_imovel_id"))
            if producao_imovel is None:
                return {"sucesso": False, "erro": "Imóvel da produção não encontrado."}
            valor_anterior = producao_imovel.grupo_ref
            producao_imovel.grupo_ref = None
            producao_imovel.save(update_fields=["grupo_ref"])
            self._auditar_se_homologada(
                servidor,
                producao_imovel,
                justificativa,
                campo_alterado="grupo_ref",
                valor_anterior=valor_anterior,
                valor_novo=None,
            )
            return {
                "sucesso": True,
                "tipo": tipo,
                "item": _serializar_producao_imovel(producao_imovel),
            }

        if tipo == "desvincular":
            producao_imovel = self._obter_producao_imovel(acao.get("producao_imovel_id"))
            if producao_imovel is None:
                return {"sucesso": False, "erro": "Imóvel da produção não encontrado."}
            item_id = producao_imovel.pk
            imovel_id = producao_imovel.imovel_id
            self._auditar_se_homologada(
                servidor,
                producao_imovel,
                justificativa,
                operacao="EDICAO_POS_HOMOLOGACAO",
                campo_alterado="vinculo",
                valor_anterior=str(imovel_id),
                valor_novo=None,
            )
            producao_imovel.delete()
            return {"sucesso": True, "tipo": tipo, "id": item_id, "imovel_id": imovel_id}

        return {"sucesso": False, "erro": f"Ação desconhecida: {tipo}"}

    def post(self, request, *args, **kwargs):
        servidor = _obter_servidor(request.user)
        if servidor is None:
            return JsonResponse(
                {"sucesso": False, "erro": MSG_SEM_PERMISSAO},
                status=403,
            )

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"sucesso": False, "erro": "JSON inválido."}, status=400)

        acoes = payload.get("acoes") or []
        if not acoes:
            return JsonResponse({"sucesso": False, "erro": "Nenhuma ação informada."}, status=400)

        logger.info(
            "ProducaoVincularImovelView POST producao=%s acoes=%s",
            self.producao_obj.pk,
            acoes,
        )

        justificativa = (payload.get("justificativa") or "").strip()
        erro_justificativa = _validar_justificativa_homologada(
            self.producao_obj,
            justificativa,
        )
        if erro_justificativa:
            return JsonResponse({"sucesso": False, "erro": erro_justificativa}, status=400)

        resultados = []
        with transaction.atomic():
            for acao in acoes:
                resultado = self._processar_acao(request, acao, servidor, justificativa)
                if not resultado.get("sucesso"):
                    status = resultado.pop("status", 400)
                    return self._resposta_json(
                        request,
                        sucesso=False,
                        status=status,
                        erro=resultado.get("erro", "Erro ao processar ação."),
                        resultados=resultados,
                    )
                resultados.append(resultado)

        return self._resposta_json(
            request,
            sucesso=True,
            mensagem="Alterações salvas com sucesso.",
            resultados=resultados,
        )


class OSVincularImovelView(RequerLoginMixin, View):
    template_name = "os_vincular_imovel.html"

    def dispatch(self, request, *args, **kwargs):
        self.os_obj = get_object_or_404(OS, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"os": self.os_obj})

    def post(self, request, *args, **kwargs):
        servidor = _obter_servidor(request.user)
        if servidor is None:
            messages.error(request, MSG_SEM_PERMISSAO)
            return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))

        imovel_id = request.POST.get("imovel_id")
        if not imovel_id:
            messages.error(request, "Selecione um imóvel para vincular.")
            return redirect(reverse("os_vincular_imovel", kwargs={"pk": self.os_obj.pk}))

        imovel = get_object_or_404(Imovel, pk=imovel_id)
        if OsImovel.objects.filter(os=self.os_obj, imovel=imovel).exists():
            messages.error(request, "Este imóvel já está vinculado à OS.")
            return redirect(reverse("os_vincular_imovel", kwargs={"pk": self.os_obj.pk}))

        vinculo = OsImovel.objects.create(os=self.os_obj, imovel=imovel)
        vinculo.capturar_snapshot(servidor=servidor)
        messages.success(request, "Imóvel vinculado à OS com sucesso.")
        return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))


class BuscarImoveisAPIView(RequerLoginJSONMixin, View):
    def get(self, request):
        busca = request.GET.get("q", "").strip()
        if not busca:
            return JsonResponse([], safe=False)

        filtros = Q(codigo_isic__icontains=busca) | Q(nom_logradouro__icontains=busca)
        filtros |= Q(num_bloco=busca)
        try:
            filtros |= Q(inscricao_cadastral=int(busca))
        except ValueError:
            pass

        resultados = []
        for imovel in Imovel.objects.filter(filtros).order_by(
            "inscricao_cadastral",
            "codigo_isic",
        )[:20]:
            resultados.append(
                {
                    "id": imovel.pk,
                    "identificacao": _formatar_identificacao_imovel(imovel),
                    "num_bloco": imovel.num_bloco or "",
                    "endereco": _formatar_endereco_imovel(imovel),
                    "bairro": imovel.bairro or "",
                    "area_territorial": (
                        str(imovel.area_territorial)
                        if imovel.area_territorial is not None
                        else None
                    ),
                    "origem_dados": imovel.origem_dados,
                },
            )

        return JsonResponse(resultados, safe=False)


class SiatCoordenadasBlocoView(RequerLoginJSONMixin, View):
    def get(self, request, num_bloco):
        if not SIAT_ARQUIVO_PATH.exists():
            return JsonResponse({"encontrado": False})

        coordenadas = obter_coordenadas_bloco(num_bloco, SIAT_ARQUIVO_PATH)
        if not coordenadas:
            return JsonResponse({"encontrado": False})

        return JsonResponse(
            {
                "encontrado": True,
                "latitude": _decimal_para_json(coordenadas.get("latitude")),
                "longitude": _decimal_para_json(coordenadas.get("longitude")),
                "coord_x": _decimal_para_json(coordenadas.get("coord_x")),
                "coord_y": _decimal_para_json(coordenadas.get("coord_y")),
            },
        )
