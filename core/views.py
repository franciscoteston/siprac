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
from django.views import View
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
    Producao,
    ProducaoImovel,
    Servidor,
    TarefaInterna,
    TipoDemanda,
    TipoProducao,
)


MSG_SEM_PERMISSAO = "Você não tem permissão para realizar esta ação."


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
            numero_producao = None
            numero_sei = dados["numero_sei"]
        else:
            tipo_producao = dados["tipo_producao_obj"]
            numero_producao = _gerar_numero_producao(tipo_producao)
            numero_sei = dados.get("numero_sei") or None

        Producao.objects.create(
            os=self.os_obj,
            tipo_producao=tipo_producao,
            numero_producao=numero_producao,
            numero_sei=numero_sei,
            ano=ano,
            status="EM_ELABORACAO",
            criado_por=servidor,
            observacao=dados.get("observacao") or None,
        )

        messages.success(self.request, "Produção registrada.")
        return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))


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
        return context

    def form_valid(self, form):
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
