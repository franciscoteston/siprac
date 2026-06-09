import json
import logging
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
import datetime
from django.db import transaction
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
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
    RelatorioProducaoForm,
    SiatUploadForm,
)
from core.relatorios import (
    exportar_producao_excel,
    linhas_relatorio_producao,
    relatorio_producao_por_servidor,
)
from core.middleware import obter_vinculo_unidade_ativo
from core.mixins import RequerAdminMixin, RequerLoginJSONMixin, RequerLoginMixin
from core.os_service import (
    contar_producoes_por_os_ids,
    contar_producoes_por_status_unidades,
    derivar_macroetapa_os,
    os_ativas_por_unidade,
    os_da_unidade_atual,
    _queryset_os_nao_encerradas,
)
from core.siat_config import SIAT_ARQUIVO_PATH
from core.siat_service import (
    atualizar_inscricao_do_arquivo,
    buscar_inscricao_no_arquivo,
    buscar_por_logradouro_no_arquivo,
    carregar_arquivo_siat,
    contar_imoveis_siat_orfaos,
    limpar_imoveis_siat_orfaos,
    obter_coordenadas_bloco,
    obter_ou_criar_versao,
    obter_ou_criar_versao_isic,
    obter_status_arquivo_siat,
)
from core.models import (
    Encaminhamento,
    Finalidade,
    Imovel,
    ImovelVersao,
    MacroetapaLog,
    Natureza,
    OS,
    OsImovel,
    OsProcesso,
    ProcessoSei,
    LogAuditoria,
    Producao,
    ProducaoImovel,
    ProducaoStatusLog,
    Servidor,
    TarefaInterna,
    TipoDemanda,
    TipoProducao,
    UnidadeInterna,
)


MSG_SEM_PERMISSAO = "Você não tem permissão para realizar esta ação."

NIVEL_VISAO_SISTEMICA = "SISTEMICA"
NIVEL_VISAO_UNIDADE = "UNIDADE"
NIVEL_VISAO_PESSOAL = "PESSOAL"

PRIORIDADE_ORDEM = {
    "URGENTE": 0,
    "PRIORITARIO": 1,
    "NORMAL": 2,
}

STATUS_PRODUCAO_FINAL = [
    Producao.STATUS_HOMOLOGADO,
    Producao.STATUS_CANCELADO,
]

logger = logging.getLogger(__name__)


def _determinar_nivel_visao(perfil):
    if perfil and perfil.visibilidade_total:
        return NIVEL_VISAO_SISTEMICA
    if perfil and perfil.pode_homologar:
        return NIVEL_VISAO_UNIDADE
    return NIVEL_VISAO_PESSOAL


def _obter_unidade_principal_servidor(servidor):
    vinculo = obter_vinculo_unidade_ativo(servidor)
    return vinculo.unidade if vinculo else None


def _obter_visao_label(nivel_visao, servidor):
    if nivel_visao == NIVEL_VISAO_SISTEMICA:
        return "Visão sistêmica — Divisão de Avaliação de Imóveis"
    if nivel_visao == NIVEL_VISAO_UNIDADE:
        unidade = _obter_unidade_principal_servidor(servidor)
        if unidade:
            return f"Visão da unidade — {unidade.sigla}"
        return "Visão da unidade"
    return f"Minha visão — {servidor.nome}"


def _contexto_dashboard_vazio():
    return {
        "nivel_visao": NIVEL_VISAO_PESSOAL,
        "servidor_logado": None,
        "visao_label": "",
        "total_os_ativas": 0,
        "total_os_unidade": 0,
        "os_por_unidade": [],
        "os_prazo_proximo": [],
        "os_aguardando_retorno": [],
        "producao_por_tipo_mes": [],
        "producao_por_semana": [],
        "os_por_macroetapa": [],
        "os_por_natureza": [],
        "producoes_unidade_por_status": contar_producoes_por_status_unidades([]),
        "producoes_minha_por_status": {
            "ENTRADA": 0,
            "DISTRIBUIDO": 0,
            "EM_ELABORACAO": 0,
            "PARA_REVISAO": 0,
            "PARA_AJUSTES": 0,
            "HOMOLOGADO_MES": 0,
        },
        "fila_unidade": [],
        "fila_pessoal": [],
        "dashboard_chart_data": {},
        "card_aguard_retorno": 0,
        "card_producao_mes": 0,
        "card_prazo_proximo": 0,
        "card_em_elaboracao": 0,
        "card_para_revisao_ajustes": 0,
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
    return _contar_os_ativas()


def _contar_os_ativas(os_ids=None):
    qs = _queryset_os_anotado().exclude(macroetapa_atual="ENCERRADO")
    if os_ids is not None:
        if not os_ids:
            return 0
        qs = qs.filter(pk__in=os_ids)
    return qs.count()


def _obter_os_ids_unidades(unidades_ids):
    if not unidades_ids:
        return set()
    return set(
        TarefaInterna.objects.filter(unidade_id__in=unidades_ids)
        .exclude(status="CONCLUIDO")
        .values_list("os_id", flat=True)
        .distinct(),
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


def _obter_os_prazo_proximo(os_ids=None):
    """OSs com entrada na divisão há mais de 25 dias e não encerradas."""
    hoje = timezone.localdate()
    corte = hoje - datetime.timedelta(days=25)

    ordens = (
        _queryset_os_anotado()
        .filter(prazo__lt=corte)
        .exclude(prazo__isnull=True)
        .exclude(macroetapa_atual="ENCERRADO")
        .order_by("prazo")
    )
    if os_ids is not None:
        if not os_ids:
            return []
        ordens = ordens.filter(pk__in=os_ids)

    resultado = []
    for os_obj in ordens:
        dias = (hoje - os_obj.prazo).days
        resultado.append(
            {
                "pk": os_obj.pk,
                "numero_os": os_obj.numero_os,
                "processo_sei": os_obj.processo_sei_numero or "—",
                "dias": dias,
            },
        )
    return sorted(resultado, key=lambda item: item["dias"], reverse=True)


def _obter_os_aguardando_retorno():
    encaminhamentos = (
        Encaminhamento.objects.filter(
            aguarda_retorno=True,
            data_retorno_efetiva__isnull=True,
        )
        .select_related("os", "unidade_externa_destino")
        .order_by("data_retorno_prevista", "os__numero_os")
    )
    return [
        {
            "os_pk": enc.os_id,
            "numero_os": enc.os.numero_os,
            "unidade_externa": (
                enc.unidade_externa_destino.nome
                if enc.unidade_externa_destino
                else "—"
            ),
            "data_retorno_prevista": enc.data_retorno_prevista,
        }
        for enc in encaminhamentos
    ]


def _obter_producao_por_tipo_mes(os_ids=None):
    hoje = timezone.localdate()
    queryset = Producao.objects.filter(
        status=Producao.STATUS_HOMOLOGADO,
        data_homologacao__year=hoje.year,
        data_homologacao__month=hoje.month,
    )
    if os_ids is not None:
        if not os_ids:
            return []
        queryset = queryset.filter(os_id__in=os_ids)

    linhas = (
        queryset.values("tipo_producao__prefixo")
        .annotate(total=Count("id"))
        .order_by("tipo_producao__prefixo")
    )
    return [
        {
            "prefixo": linha["tipo_producao__prefixo"] or "—",
            "total": linha["total"],
        }
        for linha in linhas
    ]


def _obter_producao_por_semana(os_ids=None):
    hoje = timezone.localdate()
    inicio = hoje - datetime.timedelta(days=7 * 8 - 1)
    resultado = []
    for indice in range(8):
        semana_inicio = inicio + datetime.timedelta(days=7 * indice)
        semana_fim = semana_inicio + datetime.timedelta(days=6)
        queryset = Producao.objects.filter(
            status=Producao.STATUS_HOMOLOGADO,
            data_homologacao__gte=semana_inicio,
            data_homologacao__lte=semana_fim,
        )
        if os_ids is not None:
            if not os_ids:
                resultado.append({"semana": f"S{indice + 1}", "total": 0})
                continue
            queryset = queryset.filter(os_id__in=os_ids)
        resultado.append(
            {"semana": f"S{indice + 1}", "total": queryset.count()},
        )
    return resultado


def _contar_producao_homologada_mes(os_ids=None):
    hoje = timezone.localdate()
    queryset = Producao.objects.filter(
        status=Producao.STATUS_HOMOLOGADO,
        data_homologacao__year=hoje.year,
        data_homologacao__month=hoje.month,
    )
    if os_ids is not None:
        if not os_ids:
            return 0
        queryset = queryset.filter(os_id__in=os_ids)
    return queryset.count()


def _obter_os_por_macroetapa(os_ids=None):
    qs = (
        _queryset_os_anotado()
        .exclude(macroetapa_atual="ENCERRADO")
        .exclude(macroetapa_atual__isnull=True)
    )
    if os_ids is not None:
        if not os_ids:
            return []
        qs = qs.filter(pk__in=os_ids)

    linhas = (
        qs.values("macroetapa_atual")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    return [
        {"macroetapa": linha["macroetapa_atual"], "total": linha["total"]}
        for linha in linhas
    ]


def _obter_os_por_natureza(os_ids=None):
    qs = _queryset_os_anotado().exclude(macroetapa_atual="ENCERRADO")
    if os_ids is not None:
        if not os_ids:
            return []
        qs = qs.filter(pk__in=os_ids)

    linhas = (
        qs.values("natureza__descricao")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    return [
        {"natureza": linha["natureza__descricao"], "total": linha["total"]}
        for linha in linhas
    ]


def _mapa_prazos_os(os_ids):
    if not os_ids:
        return {}
    return {
        vinculo.os_id: vinculo.data_entrada_divisao
        for vinculo in OsProcesso.objects.filter(
            os_id__in=os_ids,
            tipo_vinculo="PRINCIPAL",
        )
        if vinculo.data_entrada_divisao
    }


def _serializar_fila_producoes(queryset):
    producoes = _ordenar_producoes_fila(
        queryset.select_related("os", "tipo_producao", "servidor_responsavel"),
    )
    os_ids = [producao.os_id for producao in producoes]
    prazos = _mapa_prazos_os(os_ids)
    fila = []
    for producao in producoes:
        fila.append(
            {
                "pk": producao.pk,
                "os_pk": producao.os_id,
                "numero_os": producao.os.numero_os,
                "tipo": producao.tipo_producao.prefixo,
                "status": producao.status,
                "servidor_responsavel": (
                    producao.servidor_responsavel.nome
                    if producao.servidor_responsavel
                    else "—"
                ),
                "prazo": prazos.get(producao.os_id),
                "prioridade": producao.os.prioridade,
            },
        )
    return fila


def _mapa_processos_principais_os(os_ids):
    if not os_ids:
        return {}
    return {
        vinculo.os_id: vinculo.processo_sei.numero_processo
        for vinculo in OsProcesso.objects.filter(
            os_id__in=os_ids,
            tipo_vinculo="PRINCIPAL",
        ).select_related("processo_sei")
    }


def _mapa_etapas_internas_os(os_ids):
    if not os_ids:
        return {}
    mapa = {}
    for tarefa in (
        TarefaInterna.objects.filter(os_id__in=os_ids)
        .exclude(status="CONCLUIDO")
        .order_by("os_id", "-data_inicio")
    ):
        if tarefa.os_id not in mapa:
            mapa[tarefa.os_id] = tarefa.etapa_interna
    return mapa


def _serializar_minha_fila_padronizada(queryset):
    producoes = _ordenar_producoes_fila(
        queryset.select_related(
            "os",
            "os__natureza",
            "tipo_producao",
            "servidor_responsavel",
        ),
    )
    os_ids = [producao.os_id for producao in producoes]
    prazos = _mapa_prazos_os(os_ids)
    processos = _mapa_processos_principais_os(os_ids)
    etapas = _mapa_etapas_internas_os(os_ids)
    fila = []
    for producao in producoes:
        fila.append(
            {
                "pk": producao.pk,
                "os_pk": producao.os_id,
                "numero_os": producao.os.numero_os,
                "processo_sei": processos.get(producao.os_id, "—"),
                "natureza": producao.os.natureza.descricao,
                "natureza_id": producao.os.natureza_id,
                "etapa_interna": etapas.get(producao.os_id),
                "tipo": producao.tipo_producao.prefixo,
                "status": producao.status,
                "prazo": prazos.get(producao.os_id),
                "prioridade": producao.os.prioridade,
            },
        )
    return fila


def _statuses_chefia_fila(perfil):
    if perfil and perfil.visibilidade_total:
        return [Producao.STATUS_PARA_REVISAO]
    if perfil and perfil.pode_homologar:
        return [Producao.STATUS_PARA_REVISAO, Producao.STATUS_PARA_AJUSTES]
    return []


def _obter_minha_fila(servidor, unidades_ids, perfil):
    statuses_chefia = _statuses_chefia_fila(perfil)
    queryset = _queryset_fila_pessoal(servidor, unidades_ids, statuses_chefia)
    os_ativas = set(_queryset_os_nao_encerradas().values_list("pk", flat=True))
    queryset = queryset.filter(os_id__in=os_ativas)
    return _serializar_minha_fila_padronizada(queryset)


def _ordenar_producoes_fila(queryset):
    producoes = list(queryset)
    producoes.sort(
        key=lambda producao: (
            PRIORIDADE_ORDEM.get(producao.os.prioridade, 9),
            producao.data_criacao,
        ),
    )
    return producoes


def _queryset_fila_pessoal(servidor, unidades_ids, statuses_chefia):
    filtro = Q(servidor_responsavel=servidor)
    if statuses_chefia and unidades_ids:
        os_ids = _obter_os_ids_unidades(unidades_ids)
        if os_ids:
            filtro |= Q(os_id__in=os_ids, status__in=statuses_chefia)

    return (
        Producao.objects.filter(filtro)
        .exclude(status__in=STATUS_PRODUCAO_FINAL)
    )


def _obter_fila_pessoal_sistemica(servidor, unidades_ids, perfil):
    return _obter_minha_fila(servidor, unidades_ids, perfil)


def _obter_fila_pessoal_unidade(servidor, unidades_ids, perfil):
    return _obter_minha_fila(servidor, unidades_ids, perfil)


def _obter_fila_unidade(unidade):
    if unidade is None:
        return []
    os_ids = os_da_unidade_atual(unidade).values_list("pk", flat=True)
    if not os_ids:
        return []
    return _serializar_fila_producoes(
        Producao.objects.filter(os_id__in=os_ids).exclude(
            status__in=STATUS_PRODUCAO_FINAL,
        ),
    )


def _contar_producoes_minhas_por_status(servidor):
    hoje = timezone.localdate()
    resultado = {
        "ENTRADA": 0,
        "DISTRIBUIDO": 0,
        "EM_ELABORACAO": 0,
        "PARA_REVISAO": 0,
        "PARA_AJUSTES": 0,
        "HOMOLOGADO_MES": 0,
    }
    queryset = Producao.objects.filter(servidor_responsavel=servidor).exclude(
        status=Producao.STATUS_CANCELADO,
    )
    for item in queryset.values("status").annotate(total=Count("id")):
        if item["status"] in resultado:
            resultado[item["status"]] = item["total"]

    resultado["HOMOLOGADO_MES"] = queryset.filter(
        status=Producao.STATUS_HOMOLOGADO,
        data_homologacao__year=hoje.year,
        data_homologacao__month=hoje.month,
    ).count()
    return resultado


def _contexto_dashboard_sistemica(servidor, unidades_ids, perfil):
    os_prazo_proximo = _obter_os_prazo_proximo()
    os_aguardando_retorno = _obter_os_aguardando_retorno()
    producao_por_tipo_mes = _obter_producao_por_tipo_mes()
    producao_por_semana = _obter_producao_por_semana()
    os_por_macroetapa = _obter_os_por_macroetapa()
    os_por_natureza = _obter_os_por_natureza()

    return {
        "total_os_ativas": _contar_os_ativas(),
        "os_por_unidade": os_ativas_por_unidade(),
        "os_prazo_proximo": os_prazo_proximo,
        "os_aguardando_retorno": os_aguardando_retorno,
        "producao_por_tipo_mes": producao_por_tipo_mes,
        "producao_por_semana": producao_por_semana,
        "os_por_macroetapa": os_por_macroetapa,
        "os_por_natureza": os_por_natureza,
        "fila_pessoal": _obter_fila_pessoal_sistemica(servidor, unidades_ids, perfil),
        "dashboard_chart_data": _montar_dashboard_chart_data(
            producao_por_tipo_mes,
            producao_por_semana,
            os_por_macroetapa,
            os_por_natureza,
        ),
        "card_aguard_retorno": len(os_aguardando_retorno),
        "card_producao_mes": _contar_producao_homologada_mes(),
        "card_prazo_proximo": len(os_prazo_proximo),
    }


def _contexto_dashboard_unidade(servidor, unidades_ids, perfil):
    unidade = _obter_unidade_principal_servidor(servidor)
    os_ids = set(os_da_unidade_atual(unidade).values_list("pk", flat=True))
    os_prazo_proximo = _obter_os_prazo_proximo(os_ids=os_ids)
    producao_por_tipo_mes = _obter_producao_por_tipo_mes(os_ids=os_ids)
    producao_por_semana = _obter_producao_por_semana(os_ids=os_ids)
    producoes_unidade = contar_producoes_por_os_ids(os_ids)

    return {
        "total_os_unidade": _contar_os_ativas(os_ids=os_ids),
        "producoes_unidade_por_status": producoes_unidade,
        "fila_unidade": _obter_fila_unidade(unidade),
        "os_prazo_proximo": os_prazo_proximo,
        "producao_por_tipo_mes": producao_por_tipo_mes,
        "producao_por_semana": producao_por_semana,
        "fila_pessoal": _obter_fila_pessoal_unidade(servidor, unidades_ids, perfil),
        "unidade_sigla": unidade.sigla if unidade else "",
        "dashboard_chart_data": _montar_dashboard_chart_data(
            producao_por_tipo_mes,
            producao_por_semana,
            [],
            [],
        ),
        "card_em_elaboracao": producoes_unidade.get("EM_ELABORACAO", 0),
        "card_para_revisao_ajustes": (
            producoes_unidade.get("PARA_REVISAO", 0)
            + producoes_unidade.get("PARA_AJUSTES", 0)
        ),
        "card_producao_mes": producoes_unidade.get("HOMOLOGADO_MES", 0),
    }


def _contexto_dashboard_pessoal(servidor, perfil):
    unidades_ids = list(_obter_unidades_ativas(servidor))
    return {
        "producoes_minha_por_status": _contar_producoes_minhas_por_status(servidor),
        "fila_pessoal": _obter_minha_fila(servidor, unidades_ids, perfil),
    }


def _montar_dashboard_chart_data(
    producao_por_tipo_mes,
    producao_por_semana,
    os_por_macroetapa,
    os_por_natureza,
):
    from core.templatetags.siprac_filters import MACROETAPA_LABELS

    return {
        "producao_tipo": {
            "labels": [item["prefixo"] for item in producao_por_tipo_mes],
            "data": [item["total"] for item in producao_por_tipo_mes],
        },
        "producao_semana": {
            "labels": [item["semana"] for item in producao_por_semana],
            "data": [item["total"] for item in producao_por_semana],
        },
        "os_macroetapa": {
            "labels": [
                MACROETAPA_LABELS.get(item["macroetapa"], item["macroetapa"])
                for item in os_por_macroetapa
            ],
            "data": [item["total"] for item in os_por_macroetapa],
        },
        "os_natureza": {
            "labels": [item["natureza"] for item in os_por_natureza],
            "data": [item["total"] for item in os_por_natureza],
        },
    }


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


def _ultima_versao_imovel(imovel):
    return imovel.versoes.order_by("-exercicio", "-num_versao", "-data_registro", "-pk").first()


def _versao_vinculo(vinculo):
    return vinculo.imovel_versao


def _salvar_imovel_from_form(dados, imovel=None):
    if imovel is None:
        imovel = Imovel(tipo_identificacao=dados["tipo_identificacao"])

    imovel.tipo_identificacao = dados["tipo_identificacao"]
    imovel.observacao_interna = dados.get("observacao_interna") or None

    if dados["tipo_identificacao"] == "ISIC":
        if not imovel.codigo_isic:
            imovel.codigo_isic = _gerar_codigo_isic()
        imovel.inscricao_cadastral = None
    else:
        imovel.inscricao_cadastral = dados["inscricao_cadastral"]
        imovel.codigo_isic = None

    imovel.save()

    campos_versao = {}
    for campo in ImovelForm.CAMPOS_IMOVEL:
        if campo in ("origem_dados", "observacao_interna", "exercicio_referencia", "num_versao"):
            continue
        if hasattr(ImovelVersao, campo):
            campos_versao[campo] = dados.get(campo)

    ImovelVersao.objects.create(
        imovel=imovel,
        exercicio=dados.get("exercicio_referencia") or timezone.localdate().year,
        num_versao=dados.get("num_versao") or 0,
        origem_dados=dados.get("origem_dados") or "MANUAL",
        **campos_versao,
    )
    return imovel


def _salvar_isic_from_form(dados):
    dados_versao = {
        campo: dados.get(campo)
        for campo in ISICForm.CAMPOS_ISIC
        if campo != "observacao_interna"
    }

    num_bloco = dados.get("num_bloco")
    if num_bloco and SIAT_ARQUIVO_PATH.exists():
        coordenadas = obter_coordenadas_bloco(num_bloco, SIAT_ARQUIVO_PATH)
        if coordenadas:
            for campo in ("latitude", "longitude", "coord_x", "coord_y"):
                if dados_versao.get(campo) is None and coordenadas.get(campo) is not None:
                    dados_versao[campo] = coordenadas[campo]

    imovel, _ = obter_ou_criar_versao_isic(
        {
            "codigo_isic": _gerar_codigo_isic(),
            **dados_versao,
        },
    )
    if dados.get("observacao_interna"):
        imovel.observacao_interna = dados["observacao_interna"]
        imovel.save()
    return imovel


def _decimal_para_json(valor):
    return str(valor) if valor is not None else None


def _format_area_mapa(area):
    if area is None:
        return "—"
    try:
        from decimal import Decimal

        value = Decimal(str(area))
        parts = f"{value:,.2f}".split(".")
        inteiro = parts[0].replace(",", ".")
        return f"{inteiro},{parts[1]}"
    except Exception:
        return str(area)


def _endereco_versao(versao):
    if versao is None or not versao.nom_logradouro:
        return "—"
    endereco = versao.nom_logradouro
    if versao.num_endereco:
        endereco = f"{endereco}, {versao.num_endereco}"
    return endereco


def _endereco_imovel(imovel):
    return _endereco_versao(_ultima_versao_imovel(imovel))


def _endereco_os_imovel(vinculo):
    return _endereco_versao(_versao_vinculo(vinculo))


def _identificacao_imovel(imovel):
    if imovel.inscricao_cadastral:
        return str(imovel.inscricao_cadastral)
    if imovel.codigo_isic:
        return imovel.codigo_isic
    return "—"


def _identificacao_os_imovel(vinculo):
    versao = _versao_vinculo(vinculo)
    if versao and vinculo.imovel.inscricao_cadastral:
        return str(vinculo.imovel.inscricao_cadastral)
    if vinculo.imovel.codigo_isic:
        return vinculo.imovel.codigo_isic
    return "—"


def _coords_versao(versao):
    if versao is None or versao.latitude is None or versao.longitude is None:
        return None, None
    return float(versao.latitude), float(versao.longitude)


def _coords_os_imovel(vinculo):
    return _coords_versao(_versao_vinculo(vinculo))


def _montar_imoveis_coords_os(vinculos):
    com_coords = []
    sem_coords = 0
    for vinculo in vinculos:
        versao = _versao_vinculo(vinculo)
        lat, lng = _coords_os_imovel(vinculo)
        if lat is None or lng is None:
            sem_coords += 1
            continue
        area = versao.area_territorial if versao else None
        com_coords.append(
            {
                "id": vinculo.imovel_id,
                "identificacao": _identificacao_os_imovel(vinculo),
                "endereco": _endereco_os_imovel(vinculo),
                "area": _format_area_mapa(area),
                "lat": lat,
                "lng": lng,
            },
        )
    return com_coords, sem_coords


def _imovel_para_mapa(imovel, versao=None):
    versao = versao or _ultima_versao_imovel(imovel)
    lat, lng = _coords_versao(versao)
    return {
        "id": imovel.pk,
        "identificacao": _identificacao_imovel(imovel),
        "endereco": _endereco_versao(versao),
        "bairro": (versao.bairro if versao else None) or "—",
        "area": _format_area_mapa(versao.area_territorial if versao else None),
        "tipo_identificacao": imovel.tipo_identificacao,
        "lat": lat,
        "lng": lng,
    }


def _versao_para_dict(versao):
    if versao is None:
        return {}
    return {
        "num_bloco": versao.num_bloco,
        "cod_logradouro": versao.cod_logradouro,
        "nom_logradouro": versao.nom_logradouro,
        "num_endereco": versao.num_endereco,
        "num_unidade": versao.num_unidade,
        "bairro": versao.bairro,
        "des_finalidade": versao.des_finalidade,
        "area_territorial": versao.area_territorial,
        "area_construida": versao.area_construida,
        "exercicio_referencia": versao.exercicio,
        "num_versao": versao.num_versao,
        "rh_nome": versao.rh_nome,
        "rh_valor": versao.rh_valor,
        "idf_regiao_homogenea": versao.idf_regiao_homogenea,
        "latitude": versao.latitude,
        "longitude": versao.longitude,
        "coord_x": versao.coord_x,
        "coord_y": versao.coord_y,
        "origem_dados": versao.origem_dados,
    }


def _montar_resultado_busca(dados, fonte):
    endereco_partes = []
    if dados.get("nom_logradouro"):
        endereco_partes.append(dados["nom_logradouro"])
    if dados.get("num_endereco"):
        endereco_partes.append(str(dados["num_endereco"]))

    identificacao = dados.get("inscricao_cadastral") or dados.get("codigo_isic") or ""
    exercicio = dados.get("exercicio_referencia") or dados.get("exercicio")

    return {
        "inscricao_cadastral": dados.get("inscricao_cadastral"),
        "identificacao": str(identificacao),
        "endereco": ", ".join(endereco_partes),
        "bairro": dados.get("bairro") or "",
        "area_territorial": _format_area_mapa(dados.get("area_territorial")),
        "exercicio": exercicio,
        "num_versao": dados.get("num_versao", 0),
        "fonte": fonte,
        "num_bloco": dados.get("num_bloco") or "",
        "dados_completos": dados,
    }


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

    if macroetapa == "ativas":
        queryset = queryset.exclude(macroetapa_atual="ENCERRADO")
    elif macroetapa:
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

    if request.GET.get("aguarda_retorno") == "1":
        os_ids = Encaminhamento.objects.filter(
            aguarda_retorno=True,
            data_retorno_efetiva__isnull=True,
        ).values_list("os_id", flat=True)
        queryset = queryset.filter(pk__in=os_ids)

    if request.GET.get("prazo") == "proximo":
        hoje = timezone.localdate()
        corte = hoje - datetime.timedelta(days=25)
        queryset = (
            queryset.filter(prazo__lt=corte)
            .exclude(prazo__isnull=True)
            .exclude(macroetapa_atual="ENCERRADO")
        )

    unidade_sigla = request.GET.get("unidade", "").strip()
    if unidade_sigla:
        try:
            unidade = UnidadeInterna.objects.get(sigla=unidade_sigla)
            os_ids = os_da_unidade_atual(unidade).values_list("pk", flat=True)
            queryset = queryset.filter(pk__in=os_ids)
        except UnidadeInterna.DoesNotExist:
            pass

    return queryset


def _aplicar_visibilidade_producao(queryset, request):
    perfil = getattr(request, "perfil_acesso", None)
    servidor = _obter_servidor(request.user)
    if servidor is None:
        return queryset.none()

    if perfil and perfil.visibilidade_total:
        return queryset

    if perfil and perfil.pode_homologar:
        unidade = _obter_unidade_principal_servidor(servidor)
        if unidade is None:
            return queryset.none()
        os_ids = os_da_unidade_atual(unidade).values_list("pk", flat=True)
        return queryset.filter(os_id__in=os_ids)

    return queryset.filter(servidor_responsavel=servidor)


def _aplicar_filtros_producao(queryset, request):
    status = request.GET.get("status", "").strip()
    if status:
        queryset = queryset.filter(status=status)

    tipo_id = request.GET.get("tipo_producao", "").strip()
    if tipo_id:
        queryset = queryset.filter(tipo_producao_id=tipo_id)

    periodo = request.GET.get("periodo", "").strip()
    if periodo == "mes_atual":
        hoje = timezone.localdate()
        queryset = queryset.filter(
            data_homologacao__year=hoje.year,
            data_homologacao__month=hoje.month,
            status=Producao.STATUS_HOMOLOGADO,
        )

    unidade_sigla = request.GET.get("unidade", "").strip()
    if unidade_sigla:
        try:
            unidade = UnidadeInterna.objects.get(sigla=unidade_sigla)
            os_ids = os_da_unidade_atual(unidade).values_list("pk", flat=True)
            queryset = queryset.filter(os_id__in=os_ids)
        except UnidadeInterna.DoesNotExist:
            pass

    if request.GET.get("responsavel") == "eu":
        servidor = _obter_servidor(request.user)
        if servidor:
            queryset = queryset.filter(servidor_responsavel=servidor)

    return queryset


def _obter_outras_os_mesmo_imovel(processo):
    os_ids_processo = set(
        OsProcesso.objects.filter(processo_sei=processo).values_list("os_id", flat=True),
    )
    if not os_ids_processo:
        return []

    imovel_ids = (
        OsImovel.objects.filter(os_id__in=os_ids_processo)
        .values_list("imovel_id", flat=True)
        .distinct()
    )
    if not imovel_ids:
        return []

    outros_os_ids = (
        OsImovel.objects.filter(imovel_id__in=imovel_ids)
        .exclude(os_id__in=os_ids_processo)
        .values_list("os_id", flat=True)
        .distinct()
    )
    if not outros_os_ids:
        return []

    vinculos_principais = {
        vinculo.os_id: vinculo
        for vinculo in OsProcesso.objects.filter(
            os_id__in=outros_os_ids,
            tipo_vinculo="PRINCIPAL",
        ).select_related("processo_sei", "os")
    }

    resultado = []
    vistos = set()
    for os_id in outros_os_ids:
        if os_id in vistos:
            continue
        vinculo = vinculos_principais.get(os_id)
        if vinculo is None or vinculo.processo_sei_id == processo.pk:
            continue
        vistos.add(os_id)
        resultado.append(
            {
                "processo_pk": vinculo.processo_sei_id,
                "numero_processo": vinculo.processo_sei.numero_processo,
                "os_pk": vinculo.os_id,
                "numero_os": vinculo.os.numero_os,
                "periodo_inicio": vinculo.data_entrada_divisao,
                "periodo_fim": vinculo.data_encerramento,
            },
        )
    return resultado


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
        perfil = getattr(self.request, "perfil_acesso", None)
        servidor = _obter_servidor(self.request.user)

        if servidor is None:
            context.update(_contexto_dashboard_vazio())
            return context

        nivel_visao = _determinar_nivel_visao(perfil)
        unidades_ids = list(_obter_unidades_ativas(servidor))

        context["nivel_visao"] = nivel_visao
        context["servidor_logado"] = servidor

        if nivel_visao == NIVEL_VISAO_SISTEMICA:
            context.update(_contexto_dashboard_sistemica(servidor, unidades_ids, perfil))
        elif nivel_visao == NIVEL_VISAO_UNIDADE:
            context.update(_contexto_dashboard_unidade(servidor, unidades_ids, perfil))
        else:
            context.update(_contexto_dashboard_pessoal(servidor, perfil))

        context["visao_label"] = _obter_visao_label(nivel_visao, servidor)
        return context


RELATORIOS_DISPONIVEIS = [
    {
        "titulo": "Produção por Servidor",
        "descricao": (
            "Produções homologadas agrupadas por autor do trabalho, com filtros "
            "por período, tipo de produção e unidade."
        ),
        "url_name": "relatorio_producao",
    },
]


def _filtros_relatorio_producao(form):
    dados = form.cleaned_data
    filtros = {}
    if dados.get("servidor"):
        filtros["servidor_id"] = dados["servidor"].pk
    if dados.get("data_inicio"):
        filtros["data_inicio"] = dados["data_inicio"]
    if dados.get("data_fim"):
        filtros["data_fim"] = dados["data_fim"]
    if dados.get("tipo_producao"):
        filtros["tipo_producao_id"] = dados["tipo_producao"].pk
    if dados.get("unidade"):
        filtros["unidade_id"] = dados["unidade"].pk
    return filtros


class RelatorioListView(RequerLoginMixin, TemplateView):
    template_name = "relatorio_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relatorios"] = RELATORIOS_DISPONIVEIS
        return context


class RelatorioProducaoView(RequerLoginMixin, View):
    template_name = "relatorio_producao.html"

    def _render(self, request, form, linhas=None, total=None):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "linhas": linhas,
                "total": total,
                "exibir_resultados": linhas is not None,
            },
        )

    def get(self, request):
        return self._render(request, RelatorioProducaoForm())

    def post(self, request):
        form = RelatorioProducaoForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)

        queryset = relatorio_producao_por_servidor(_filtros_relatorio_producao(form))
        acao = request.POST.get("action", "visualizar")

        if acao == "exportar":
            return exportar_producao_excel(queryset)

        linhas = linhas_relatorio_producao(queryset)
        return self._render(request, form, linhas=linhas, total=len(linhas))


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
        context["filtro_aguarda_retorno"] = self.request.GET.get("aguarda_retorno", "")
        context["filtro_prazo"] = self.request.GET.get("prazo", "")
        context["filtro_unidade"] = self.request.GET.get("unidade", "")
        context["naturezas"] = Natureza.objects.filter(ativa=True).order_by("descricao")
        context["status_producao_opcoes"] = Producao.STATUS_CHOICES
        context["macroetapas"] = (
            MacroetapaLog.objects.values_list("macroetapa", flat=True)
            .distinct()
            .order_by("macroetapa")
        )
        context["prioridades"] = ["NORMAL", "PRIORITARIO", "URGENTE"]
        return context


class ProducaoListView(RequerLoginMixin, ListView):
    template_name = "producao_list.html"
    context_object_name = "producoes"
    paginate_by = 20

    def get_queryset(self):
        queryset = Producao.objects.select_related(
            "os",
            "tipo_producao",
            "servidor_responsavel",
        )
        queryset = _aplicar_visibilidade_producao(queryset, self.request)
        queryset = _aplicar_filtros_producao(queryset, self.request)
        return queryset.order_by("-data_criacao")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filtro_status"] = self.request.GET.get("status", "")
        context["filtro_tipo_producao"] = self.request.GET.get("tipo_producao", "")
        context["filtro_periodo"] = self.request.GET.get("periodo", "")
        context["filtro_unidade"] = self.request.GET.get("unidade", "")
        context["filtro_responsavel"] = self.request.GET.get("responsavel", "")
        context["status_opcoes"] = Producao.STATUS_CHOICES
        context["tipos_producao"] = TipoProducao.objects.filter(ativo=True).order_by(
            "prefixo",
        )
        context["unidades"] = UnidadeInterna.objects.all().order_by("sigla")
        perfil = getattr(self.request, "perfil_acesso", None)
        context["exibir_filtro_unidade"] = perfil and perfil.visibilidade_total
        return context


class ProcessoDetailView(RequerLoginMixin, DetailView):
    model = ProcessoSei
    template_name = "processo_detail.html"
    context_object_name = "processo"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        processo = self.object

        vinculos = (
            OsProcesso.objects.filter(processo_sei=processo)
            .select_related("os")
            .order_by("-data_entrada_divisao", "os__numero_os")
        )
        os_ids = [vinculo.os_id for vinculo in vinculos]
        macroetapas = {}
        if os_ids:
            for os_obj in _queryset_os_anotado().filter(pk__in=os_ids):
                macroetapas[os_obj.pk] = os_obj.macroetapa_atual

        os_vinculadas = []
        for vinculo in vinculos:
            os_vinculadas.append(
                {
                    "os_pk": vinculo.os_id,
                    "numero_os": vinculo.os.numero_os,
                    "tipo_vinculo": vinculo.tipo_vinculo,
                    "data_entrada": vinculo.data_entrada_divisao,
                    "data_encerramento": vinculo.data_encerramento,
                    "macroetapa": macroetapas.get(vinculo.os_id),
                },
            )

        producoes = (
            Producao.objects.filter(os_id__in=os_ids)
            .select_related("tipo_producao", "autor_trabalho")
            .order_by("-data_criacao")
        ) if os_ids else Producao.objects.none()

        context["os_vinculadas"] = os_vinculadas
        context["producoes"] = producoes
        context["outras_os_mesmo_imovel"] = _obter_outras_os_mesmo_imovel(processo)
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
        imoveis_vinculados = OsImovel.objects.filter(os=os_obj).select_related(
            "imovel",
            "imovel_versao",
            "vinculado_por",
        )
        context["imoveis"] = imoveis_vinculados
        imoveis_com_coords, imoveis_sem_coordenadas = _montar_imoveis_coords_os(
            imoveis_vinculados,
        )
        context["imoveis_com_coords"] = imoveis_com_coords
        context["imoveis_sem_coordenadas"] = imoveis_sem_coordenadas
        context["imoveis_coords_json"] = json.dumps(
            imoveis_com_coords,
            ensure_ascii=False,
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

        derivar_macroetapa_os(producao.os, servidor=servidor)
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


class ImovelMapaView(RequerLoginMixin, TemplateView):
    template_name = "imovel_mapa.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total_imoveis = Imovel.objects.count()
        imoveis_com_coords = []
        imoveis_sem_coords_lista = []

        for imovel in Imovel.objects.order_by("id"):
            versao = _ultima_versao_imovel(imovel)
            lat, lng = _coords_versao(versao)
            if lat is not None and lng is not None:
                item = _imovel_para_mapa(imovel, versao)
                if item["lat"] is not None and item["lng"] is not None:
                    imoveis_com_coords.append(item)
                    continue
            if len(imoveis_sem_coords_lista) < 50:
                imoveis_sem_coords_lista.append(
                    {
                        "id": imovel.pk,
                        "inscricao_cadastral": imovel.inscricao_cadastral,
                        "codigo_isic": imovel.codigo_isic,
                        "nom_logradouro": versao.nom_logradouro if versao else None,
                        "num_endereco": versao.num_endereco if versao else None,
                        "bairro": versao.bairro if versao else None,
                    },
                )

        total_com_coords = len(imoveis_com_coords)
        total_sem_coords = total_imoveis - total_com_coords
        context["imoveis_com_coords"] = imoveis_com_coords
        context["total_imoveis"] = total_imoveis
        context["total_com_coords"] = total_com_coords
        context["total_sem_coords"] = total_sem_coords
        context["pct_com_coords"] = (
            round(total_com_coords * 100 / total_imoveis, 1)
            if total_imoveis
            else 0
        )
        context["imoveis_coords_json"] = json.dumps(
            imoveis_com_coords,
            ensure_ascii=False,
        )
        context["imoveis_sem_coords_lista"] = imoveis_sem_coords_lista
        return context


class ImovelListView(RequerLoginMixin, ListView):
    model = Imovel
    template_name = "imovel_list.html"
    context_object_name = "imoveis"
    paginate_by = 20

    def get_queryset(self):
        queryset = Imovel.objects.all()
        busca = self.request.GET.get("q", "").strip()
        if busca:
            filtros = Q(codigo_isic__icontains=busca)
            filtros |= Q(versoes__nom_logradouro__icontains=busca)
            filtros |= Q(versoes__bairro__icontains=busca)
            filtros |= Q(versoes__num_endereco__icontains=busca)
            try:
                filtros |= Q(inscricao_cadastral=int(busca))
            except ValueError:
                pass
            queryset = queryset.filter(filtros).distinct()
        return queryset.prefetch_related(
            Prefetch(
                "versoes",
                queryset=ImovelVersao.objects.order_by(
                    "-exercicio",
                    "-num_versao",
                    "-data_registro",
                    "-pk",
                ),
            ),
        ).order_by("-id")

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
        context["versao_atual"] = _ultima_versao_imovel(imovel)
        context["versoes"] = imovel.versoes.order_by(
            "-exercicio",
            "-num_versao",
            "-data_registro",
        )
        context["vinculos_os"] = (
            OsImovel.objects.filter(imovel=imovel)
            .select_related("os", "imovel_versao")
            .order_by("-os__data_criacao_sgbd")
        )
        context["vinculos_producao"] = (
            ProducaoImovel.objects.filter(imovel=imovel)
            .select_related("producao", "producao__tipo_producao", "producao__os", "imovel_versao")
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


def _formatar_tamanho_arquivo(tamanho):
    if tamanho >= 1024 * 1024:
        return f"{tamanho / (1024 * 1024):.1f} MB"
    if tamanho >= 1024:
        return f"{tamanho / 1024:.1f} KB"
    return f"{tamanho} bytes"


def _contexto_arquivo_siat():
    status = obter_status_arquivo_siat(SIAT_ARQUIVO_PATH)
    contexto = {
        "arquivo_existe": status.get("disponivel", False),
        "contagem_siat_orfaos": contar_imoveis_siat_orfaos(),
    }
    if not status.get("disponivel"):
        return contexto

    modificado = timezone.localtime(
        datetime.datetime.fromisoformat(status["modificado_em"]),
    )
    contexto.update(
        {
            "arquivo_nome": SIAT_ARQUIVO_PATH.name,
            "arquivo_modificado": modificado,
            "arquivo_tamanho": _formatar_tamanho_arquivo(status["tamanho_bytes"]),
            "arquivo_total_registros": status.get("total_registros", 0),
            "arquivo_data": status.get("data_arquivo"),
        },
    )
    return contexto


class SiatCarregarArquivoView(RequerAdminMixin, FormView):
    template_name = "siat_carregar.html"
    form_class = SiatUploadForm
    success_url = reverse_lazy("siat_carregar")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_contexto_arquivo_siat())
        return context

    def form_valid(self, form):
        SIAT_ARQUIVO_PATH.parent.mkdir(parents=True, exist_ok=True)
        uploaded = form.cleaned_data["arquivo"]
        with open(SIAT_ARQUIVO_PATH, "wb") as destino:
            for chunk in uploaded.chunks():
                destino.write(chunk)

        resultado = carregar_arquivo_siat(SIAT_ARQUIVO_PATH)
        if not resultado.get("valido"):
            if SIAT_ARQUIVO_PATH.exists():
                SIAT_ARQUIVO_PATH.unlink()
            messages.error(
                self.request,
                resultado.get("erro", "Formato de arquivo inválido."),
            )
            return self.form_invalid(form)

        total = resultado.get("total_registros", 0)
        messages.success(
            self.request,
            f"Arquivo disponibilizado com sucesso. "
            f"{total:,} registros disponíveis para consulta.".replace(",", "."),
        )
        return super().form_valid(form)


class SiatStatusView(RequerLoginJSONMixin, View):
    def get(self, request):
        if not getattr(request, "admin_sistema", False):
            return JsonResponse({"error": "Sem permissão."}, status=403)
        return JsonResponse(obter_status_arquivo_siat(SIAT_ARQUIVO_PATH))


class SiatLimparImoveisView(RequerAdminMixin, View):
    def dispatch(self, request, *args, **kwargs):
        logger.warning("perfil_acesso: %s", getattr(request, "perfil_acesso", None))
        logger.warning(
            "admin_sistema: %s",
            getattr(getattr(request, "perfil_acesso", None), "admin_sistema", None),
        )
        logger.warning("admin_sistema flag: %s", getattr(request, "admin_sistema", None))
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return redirect("siat_carregar")

    def post(self, request):
        total = contar_imoveis_siat_orfaos()
        if total == 0:
            messages.info(request, "Nenhum imóvel SIAT órfão para remover.")
            return redirect("siat_carregar")

        removidos = limpar_imoveis_siat_orfaos()
        messages.success(
            request,
            f"{removidos:,} imóvel(is) SIAT não vinculado(s) removido(s).".replace(
                ",",
                ".",
            ),
        )
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
    versao = _ultima_versao_imovel(imovel)
    partes = []
    if versao and versao.nom_logradouro:
        partes.append(versao.nom_logradouro)
    if versao and versao.num_endereco:
        partes.append(versao.num_endereco)
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


def _formatar_identificacao_vinculo(vinculo):
    return _identificacao_os_imovel(vinculo)


def _formatar_endereco_vinculo(vinculo):
    return _endereco_os_imovel(vinculo)


def _formatar_area_vinculo(vinculo):
    versao = _versao_vinculo(vinculo)
    if versao and versao.area_territorial is not None:
        return str(versao.area_territorial)
    return None


def _serializar_os_imovel(vinculo):
    return {
        "imovel_id": vinculo.imovel_id,
        "identificacao": _formatar_identificacao_vinculo(vinculo),
        "endereco": _formatar_endereco_vinculo(vinculo),
        "area_territorial": _formatar_area_vinculo(vinculo),
    }


def _serializar_producao_imovel(item):
    return {
        "id": item.pk,
        "imovel_id": item.imovel_id,
        "identificacao": _formatar_identificacao_vinculo(item),
        "endereco": _formatar_endereco_vinculo(item),
        "area_territorial": _formatar_area_vinculo(item),
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
        .select_related("imovel", "imovel_versao")
        .order_by("imovel__inscricao_cadastral", "imovel__codigo_isic", "imovel_id")
    ]
    imoveis_producao = [
        _serializar_producao_imovel(item)
        for item in ProducaoImovel.objects.filter(producao=producao)
        .select_related("imovel", "imovel_versao")
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
            .select_related("imovel", "imovel_versao")
            .order_by("grupo_ref", "pk")
        )

        context["os"] = producao.os
        context["imoveis"] = imoveis
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
                imovel_versao=os_imovel.imovel_versao,
            )
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

        dados_json = request.POST.get("dados_completos", "").strip()
        if not dados_json:
            messages.error(request, "Dados do imóvel não informados.")
            return redirect(reverse("os_vincular_imovel", kwargs={"pk": self.os_obj.pk}))

        try:
            dados_completos = json.loads(dados_json)
        except json.JSONDecodeError:
            messages.error(request, "Dados do imóvel inválidos.")
            return redirect(reverse("os_vincular_imovel", kwargs={"pk": self.os_obj.pk}))

        if dados_completos.get("codigo_isic"):
            imovel, versao = obter_ou_criar_versao_isic(dados_completos)
        else:
            imovel, versao, _ = obter_ou_criar_versao(dados_completos)

        if OsImovel.objects.filter(os=self.os_obj, imovel=imovel).exists():
            messages.error(request, "Este imóvel já está vinculado à OS.")
            return redirect(reverse("os_vincular_imovel", kwargs={"pk": self.os_obj.pk}))

        OsImovel.objects.create(
            os=self.os_obj,
            imovel=imovel,
            imovel_versao=versao,
            vinculado_por=servidor,
        )
        messages.success(request, "Imóvel vinculado à OS com sucesso.")
        return redirect(reverse("os_detalhe", kwargs={"pk": self.os_obj.pk}))


class BuscarImoveisAPIView(RequerLoginJSONMixin, View):
    def get(self, request):
        busca = request.GET.get("q", "").strip()
        if not busca:
            return JsonResponse([], safe=False)

        resultados = []
        vistos = set()

        try:
            inscricao = int(busca)
        except ValueError:
            inscricao = None

        if inscricao is not None:
            if SIAT_ARQUIVO_PATH.exists():
                dados = buscar_inscricao_no_arquivo(inscricao, SIAT_ARQUIVO_PATH)
                if dados:
                    resultados.append(_montar_resultado_busca(dados, "siat"))
            return JsonResponse(resultados, safe=False)

        for imovel in Imovel.objects.filter(
            tipo_identificacao="ISIC",
            codigo_isic__icontains=busca,
        ).order_by("codigo_isic")[:20]:
            versao = _ultima_versao_imovel(imovel)
            dados = _versao_para_dict(versao)
            dados["codigo_isic"] = imovel.codigo_isic
            chave = f"isic:{imovel.pk}"
            if chave not in vistos:
                vistos.add(chave)
                resultados.append(_montar_resultado_busca(dados, "isic"))

        if SIAT_ARQUIVO_PATH.exists():
            for dados in buscar_por_logradouro_no_arquivo(busca, SIAT_ARQUIVO_PATH, limite=20):
                chave = f"siat:{dados.get('inscricao_cadastral')}"
                if chave in vistos:
                    continue
                vistos.add(chave)
                resultados.append(_montar_resultado_busca(dados, "siat"))
                if len(resultados) >= 20:
                    break

        return JsonResponse(resultados[:20], safe=False)


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
