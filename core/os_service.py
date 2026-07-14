from django.db.models import Case, CharField, Count, F, OuterRef, Subquery, Value, When
from django.utils import timezone

from core.models import Encaminhamento, OS, OsUnidadeStatus, Producao, TarefaInterna

CHAVE_ENTRADA_DIVISAO = "Entrada na Divisão"

STATUS_ATIVOS = [
    Producao.STATUS_NAO_DISTRIBUIDO,
    Producao.STATUS_DISTRIBUIDO,
    Producao.STATUS_REVISAR,
    Producao.STATUS_VER_AJUSTES,
    Producao.STATUS_HOMOLOGAR,
]


def _atualizar_status_unidade_encaminhamento(
    os,
    unidade_origem,
    servidor,
    manter_aberta,
    unidade_destino=None,
):
    """
    Ao encaminhar:
    - Se manter_aberta=False: conclui a OS na unidade de origem
    - Se manter_aberta=True: mantém aberta
    - Cria/atualiza OsUnidadeStatus da unidade destino como ABERTA
    """
    if unidade_origem and not manter_aberta:
        status_origem, _ = OsUnidadeStatus.objects.get_or_create(
            os=os,
            unidade=unidade_origem,
            defaults={"aberta_por": servidor},
        )
        if status_origem.status in ("ABERTA", "REABERTA"):
            status_origem.status = "CONCLUIDA"
            status_origem.data_conclusao = timezone.now()
            status_origem.concluida_por = servidor
            status_origem.manter_aberta = False
            status_origem.save()
    elif unidade_origem and manter_aberta:
        status_origem, _ = OsUnidadeStatus.objects.get_or_create(
            os=os,
            unidade=unidade_origem,
            defaults={"aberta_por": servidor, "status": "ABERTA"},
        )
        status_origem.manter_aberta = True
        if status_origem.status not in ("ABERTA", "REABERTA"):
            status_origem.status = "ABERTA"
            status_origem.data_conclusao = None
            status_origem.aberta_por = servidor
        status_origem.save()

    if unidade_destino:
        status_destino, criado = OsUnidadeStatus.objects.get_or_create(
            os=os,
            unidade=unidade_destino,
            defaults={"aberta_por": servidor, "status": "ABERTA"},
        )
        if not criado and status_destino.status != "ABERTA":
            status_destino.status = "ABERTA"
            status_destino.data_conclusao = None
            status_destino.aberta_por = servidor
            status_destino.save(
                update_fields=["status", "data_conclusao", "aberta_por"],
            )


def registrar_encaminhamento_automatico(os, tipo_macroetapa, servidor=None, observacao=None):
    """
    Registra um encaminhamento automático no lugar de MacroetapaLog.
    Usado para transições automáticas de macroetapa.
    """
    Encaminhamento.objects.create(
        os=os,
        unidade_interna_origem=None,
        servidor_origem=servidor,
        unidade_interna_destino=None,
        servidor_destino=None,
        etapa_interna="SISTEMA",
        tipo_acao=Encaminhamento.TIPO_ACAO_AUTOMATICO,
        tipo_macroetapa=tipo_macroetapa,
        data_hora=timezone.now(),
        aguarda_retorno=False,
        automatico=True,
        observacao=observacao or "",
    )


def macroetapa_atual_os(os):
    """
    Deriva a macroetapa atual da OS a partir dos encaminhamentos.
    """
    if os.encerrada:
        return "ENCERRADO"

    ultimo = Encaminhamento.objects.filter(os=os).order_by("-data_hora", "-id").first()

    if not ultimo:
        return "ENTRADA_DIVISAO"

    if ultimo.tipo_macroetapa:
        return ultimo.tipo_macroetapa

    if ultimo.unidade_externa_destino_id:
        return "ATENDIMENTO_EXTERNO"

    if ultimo.unidade_interna_destino_id:
        return "ATENDIMENTO_INTERNO"

    return "ENTRADA_DIVISAO"


def _icone_macroetapa(tipo):
    return {
        "ENTRADA_DIVISAO": "bi-box-arrow-in-right",
        "ATENDIMENTO_INTERNO": "bi-arrow-right-circle",
        "ATENDIMENTO_EXTERNO": "bi-send",
        "RETORNO_EXTERNO": "bi-arrow-return-left",
        "INCLUSAO_PROCESSO": "bi-plus-circle",
        "INCLUSAO_PROCESSO_RELACIONADO": "bi-plus-circle",
        "ENCERRADO": "bi-check-circle",
        "ENCERRAMENTO": "bi-check-circle",
    }.get(tipo, "bi-circle")


def _cor_macroetapa(tipo):
    return {
        "ENTRADA_DIVISAO": "secondary",
        "ATENDIMENTO_INTERNO": "primary",
        "ATENDIMENTO_EXTERNO": "warning",
        "RETORNO_EXTERNO": "info",
        "INCLUSAO_PROCESSO": "success",
        "INCLUSAO_PROCESSO_RELACIONADO": "success",
        "ENCERRADO": "success",
        "ENCERRAMENTO": "success",
    }.get(tipo, "secondary")


def timeline_os(os):
    """
    Retorna timeline unificada da OS: encaminhamentos + encerramento.
    Substitui MacroetapaLog + Encaminhamento separados.
    """
    eventos = []

    eventos.append({
        "tipo": "ENTRADA_DIVISAO",
        "label": "Entrada na Divisão",
        "data_hora": os.data_criacao_sgbd,
        "servidor": os.criado_por,
        "automatico": True,
        "observacao": "",
        "icone": "bi-box-arrow-in-right",
        "cor": "secondary",
        "encaminhamento": None,
    })

    encaminhamentos = Encaminhamento.objects.filter(os=os).select_related(
        "unidade_interna_origem",
        "unidade_interna_destino",
        "unidade_externa_destino",
        "servidor_origem",
        "servidor_destino",
    ).order_by("data_hora")

    label_map = {
        "ENTRADA_DIVISAO": "Entrada na Divisão",
        "ATENDIMENTO_INTERNO": "Atendimento Interno",
        "ATENDIMENTO_EXTERNO": "Atendimento Externo",
        "RETORNO_EXTERNO": "Retorno de encaminhamento externo",
        "INCLUSAO_PROCESSO": "Inclusão de processo relacionado",
        "INCLUSAO_PROCESSO_RELACIONADO": "Inclusão de processo relacionado",
        "ENCERRAMENTO": "Encerrado na Divisão",
    }

    for enc in encaminhamentos:
        if enc.tipo_macroetapa:
            tipo = enc.tipo_macroetapa
        elif enc.unidade_externa_destino_id:
            tipo = "ATENDIMENTO_EXTERNO"
        else:
            tipo = "ATENDIMENTO_INTERNO"

        if tipo == "ATENDIMENTO_INTERNO" and enc.unidade_interna_destino:
            label = f"Encaminhado para {enc.unidade_interna_destino.sigla}"
        elif tipo == "ATENDIMENTO_EXTERNO" and enc.unidade_externa_destino:
            label = f"Encaminhado para {enc.unidade_externa_destino.nome}"
        else:
            label = label_map.get(tipo, tipo)

        eventos.append({
            "tipo": tipo,
            "label": label,
            "data_hora": enc.data_hora,
            "servidor": enc.servidor_origem,
            "automatico": enc.automatico,
            "observacao": enc.observacao or "",
            "icone": _icone_macroetapa(tipo),
            "cor": _cor_macroetapa(tipo),
            "encaminhamento": enc,
            "etapa_interna": (
                "" if enc.automatico
                else ETAPAS_INTERNAS_LABELS.get(enc.etapa_interna or "", enc.etapa_interna or "")
            ),
            "tipo_acao": enc.tipo_acao,
            "tipo_acao_label": TIPO_ACAO_LABELS.get(enc.tipo_acao, enc.tipo_acao),
            "servidor_destino": enc.servidor_destino,
            "aguarda_retorno": enc.aguarda_retorno,
            "data_retorno_prevista": enc.data_retorno_prevista,
            "unidade_externa_origem": getattr(enc, "unidade_externa_origem", None),
        })

    if os.encerrada and os.data_encerramento:
        eventos.append({
            "tipo": "ENCERRADO",
            "label": "Encerrado na Divisão",
            "data_hora": os.data_encerramento,
            "servidor": None,
            "automatico": False,
            "observacao": "",
            "icone": "bi-check-circle",
            "cor": "success",
            "encaminhamento": None,
        })

    return sorted(eventos, key=lambda x: x["data_hora"], reverse=True)


def ativar_atendimento_interno_se_necessario(os, servidor=None):
    """Registra ATENDIMENTO_INTERNO quando há produção ativa e ainda não está nesse estado."""
    producoes_ativas = Producao.objects.filter(os=os, status__in=STATUS_ATIVOS)
    if not producoes_ativas.exists():
        return False
    if macroetapa_atual_os(os) == "ATENDIMENTO_INTERNO":
        return False
    if servidor is None:
        return False
    registrar_encaminhamento_automatico(
        os,
        Encaminhamento.TIPO_MACROETAPA_ATENDIMENTO_INTERNO,
        servidor=servidor,
        observacao="Derivado automaticamente: nova produção ativa registrada.",
    )
    return True


def queryset_os_com_macroetapa(queryset=None):
    """Anota queryset de OS com macroetapa_atual derivada de encaminhamentos."""
    if queryset is None:
        queryset = OS.objects.all()

    ultimo_enc = Encaminhamento.objects.filter(
        os_id=OuterRef("pk"),
    ).order_by("-data_hora", "-id")

    return queryset.annotate(
        _enc_tipo=Subquery(ultimo_enc.values("tipo_macroetapa")[:1]),
        _enc_ext=Subquery(ultimo_enc.values("unidade_externa_destino_id")[:1]),
        _enc_int=Subquery(ultimo_enc.values("unidade_interna_destino_id")[:1]),
    ).annotate(
        macroetapa_atual=Case(
            When(encerrada=True, then=Value("ENCERRADO")),
            When(_enc_tipo__isnull=False, then=F("_enc_tipo")),
            When(_enc_ext__isnull=False, then=Value("ATENDIMENTO_EXTERNO")),
            When(_enc_int__isnull=False, then=Value("ATENDIMENTO_INTERNO")),
            default=Value("ENTRADA_DIVISAO"),
            output_field=CharField(),
        ),
    )


def contar_producoes_por_status_unidades(unidades_ids):
    """Contagem de produções por status para OS das unidades informadas."""
    hoje = timezone.localdate()
    resultado = {
        "NAO_DISTRIBUIDO": 0,
        "DISTRIBUIDO": 0,
        "REVISAR": 0,
        "REVISADO": 0,
        "VER_AJUSTES": 0,
        "ENTREGA_AJUSTES": 0,
        "AJUSTES_OK": 0,
        "HOMOLOGAR": 0,
        "ENVIADO": 0,
        "HOMOLOGADO_MES": 0,
    }

    if not unidades_ids:
        return resultado

    os_ids_enc = set(
        OS.objects.filter(
            encaminhamentos__unidade_interna_destino_id__in=unidades_ids,
        ).values_list("pk", flat=True),
    )
    os_ids_tarefa = set(
        TarefaInterna.objects.filter(unidade_id__in=unidades_ids).values_list(
            "os_id",
            flat=True,
        ),
    )
    os_ids = os_ids_enc | os_ids_tarefa

    if not os_ids:
        return resultado

    queryset = Producao.objects.filter(os_id__in=os_ids).exclude(
        status=Producao.STATUS_CANCELADO,
    )

    for item in queryset.values("status").annotate(total=Count("id")):
        if item["status"] in resultado:
            resultado[item["status"]] = item["total"]

    resultado["HOMOLOGADO_MES"] = queryset.filter(
        status=Producao.STATUS_ENVIADO,
        data_enviado__year=hoje.year,
        data_enviado__month=hoje.month,
    ).count()

    return resultado


def _queryset_os_nao_encerradas():
    return OS.objects.filter(encerrada=False)


def _mapa_unidade_atual_por_os(os_ids):
    if not os_ids:
        return {}

    mapa = {}
    encaminhamentos = (
        Encaminhamento.objects.filter(
            os_id__in=os_ids,
            unidade_interna_destino__isnull=False,
        )
        .select_related("unidade_interna_destino")
        .order_by("os_id", "-data_hora", "-id")
    )
    for encaminhamento in encaminhamentos:
        if encaminhamento.os_id not in mapa:
            mapa[encaminhamento.os_id] = encaminhamento.unidade_interna_destino
    return mapa


def unidade_atual_da_os(os):
    """
    Retorna a UnidadeInterna atual da OS baseada no último encaminhamento
    interno recebido. Se não houver encaminhamento interno, retorna None
    (OS ainda não distribuída — na entrada da Divisão).
    """
    ultimo = (
        Encaminhamento.objects.filter(
            os=os,
            unidade_interna_destino__isnull=False,
        )
        .select_related("unidade_interna_destino")
        .order_by("-data_hora", "-id")
        .first()
    )
    return ultimo.unidade_interna_destino if ultimo else None


def origem_encaminhamento(os, servidor_logado=None):
    """
    Retorna a unidade de origem para o próximo encaminhamento.
    Preferencialmente a unidade do servidor com OsUnidadeStatus ABERTA/REABERTA.
    """
    ultimo = Encaminhamento.objects.filter(
        os=os,
    ).order_by("-data_hora").first()

    if not ultimo or ultimo.tipo_macroetapa in (
        "ENTRADA_DIVISAO",
        "INCLUSAO_PROCESSO",
    ):
        return None

    if servidor_logado:
        vinculos_ativos = servidor_logado.vinculos_unidade.filter(
            data_fim__isnull=True,
        ).values_list("unidade_id", flat=True)

        status_aberto = (
            OsUnidadeStatus.objects.filter(
                os=os,
                unidade_id__in=vinculos_ativos,
                status__in=("ABERTA", "REABERTA"),
            )
            .select_related("unidade")
            .first()
        )

        if status_aberto:
            return status_aberto.unidade

    return None


ETAPAS_INTERNAS_LABELS = {
    "TRIAGEM": "Triagem",
    "ANALISE": "Análise",
    "REVISAO": "Revisão",
    "HOMOLOGACAO": "Homologação",
    "CONCLUSAO": "Conclusão",
    "SISTEMA": "Sistema",
}

TIPO_ACAO_LABELS = dict(Encaminhamento.TIPO_ACAO_CHOICES)


def os_ativas_por_unidade():
    """
    Retorna distribuição de OSs ativas por unidade atual.
    OSs sem encaminhamento interno aparecem como 'Entrada na Divisão'.
    """
    hoje = timezone.localdate()
    os_ids = list(_queryset_os_nao_encerradas().values_list("pk", flat=True))
    if not os_ids:
        return []

    mapa_unidade = _mapa_unidade_atual_por_os(os_ids)
    distribuicao = {}

    for os_id in os_ids:
        unidade = mapa_unidade.get(os_id)
        if unidade:
            chave = unidade.sigla
            nome = unidade.nome
        else:
            chave = CHAVE_ENTRADA_DIVISAO
            nome = CHAVE_ENTRADA_DIVISAO

        if chave not in distribuicao:
            distribuicao[chave] = {
                "nome": nome,
                "sigla": chave,
                "total": 0,
                "em_elaboracao": 0,
                "para_revisao": 0,
                "homologadas_mes": 0,
                "_os_ids": [],
            }
        distribuicao[chave]["total"] += 1
        distribuicao[chave]["_os_ids"].append(os_id)

    resultado = []
    for dados in distribuicao.values():
        os_ids_grupo = dados.pop("_os_ids")
        producoes = Producao.objects.filter(os_id__in=os_ids_grupo)
        dados["em_elaboracao"] = producoes.filter(
            status=Producao.STATUS_DISTRIBUIDO,
        ).count()
        dados["para_revisao"] = producoes.filter(
            status=Producao.STATUS_REVISAR,
        ).count()
        dados["homologadas_mes"] = producoes.filter(
            status=Producao.STATUS_ENVIADO,
            data_enviado__year=hoje.year,
            data_enviado__month=hoje.month,
        ).count()
        resultado.append(dados)

    return sorted(resultado, key=lambda item: item["sigla"])


def os_da_unidade_atual(unidade_interna):
    """
    Retorna OSs cuja unidade atual (último encaminhamento interno)
    é a unidade informada.
    """
    if unidade_interna is None:
        return OS.objects.none()

    os_ids = list(_queryset_os_nao_encerradas().values_list("pk", flat=True))
    if not os_ids:
        return OS.objects.none()

    mapa_unidade = _mapa_unidade_atual_por_os(os_ids)
    filtrados = [
        os_id
        for os_id in os_ids
        if mapa_unidade.get(os_id)
        and mapa_unidade[os_id].pk == unidade_interna.pk
    ]
    return OS.objects.filter(pk__in=filtrados)


def contar_producoes_por_os_ids(os_ids):
    """Contagem de produções por status para as OS informadas."""
    hoje = timezone.localdate()
    resultado = {
        "NAO_DISTRIBUIDO": 0,
        "DISTRIBUIDO": 0,
        "REVISAR": 0,
        "REVISADO": 0,
        "VER_AJUSTES": 0,
        "ENTREGA_AJUSTES": 0,
        "AJUSTES_OK": 0,
        "HOMOLOGAR": 0,
        "ENVIADO": 0,
        "HOMOLOGADO_MES": 0,
    }

    if not os_ids:
        return resultado

    queryset = Producao.objects.filter(os_id__in=os_ids).exclude(
        status=Producao.STATUS_CANCELADO,
    )

    for item in queryset.values("status").annotate(total=Count("id")):
        if item["status"] in resultado:
            resultado[item["status"]] = item["total"]

    resultado["HOMOLOGADO_MES"] = queryset.filter(
        status=Producao.STATUS_ENVIADO,
        data_enviado__year=hoje.year,
        data_enviado__month=hoje.month,
    ).count()

    return resultado


def data_entrada_unidade(os, unidade):
    """
    Retorna a data do último encaminhamento recebido pela unidade
    para esta OS. Representa a entrada mais recente da OS na unidade.
    Retorna None se a OS nunca foi encaminhada para esta unidade.
    """
    enc = Encaminhamento.objects.filter(
        os=os,
        unidade_interna_destino=unidade,
    ).order_by("-data_hora").first()
    return enc.data_hora if enc else None


def historico_entradas_unidade(os, unidade):
    """
    Retorna todos os encaminhamentos recebidos pela unidade para
    esta OS, ordenados do mais recente para o mais antigo.
    Útil para relatório histórico de entradas e saídas.
    """
    return Encaminhamento.objects.filter(
        os=os,
        unidade_interna_destino=unidade,
    ).order_by("-data_hora")


def itens_pendentes_usuario(servidor):
    """
    Retorna contagem de itens pendentes para o servidor logado.
    - os_novas: OSs encaminhadas para a unidade do servidor após seu último login
    - producoes_pendentes: produções onde servidor_responsavel=servidor
      com status em DISTRIBUIDO, PARA_REVISAO ou PARA_AJUSTES
    - revisoes_pendentes: produções em PARA_REVISAO na unidade do servidor
      (apenas para perfis com pode_homologar=True)
    """
    from django.utils import timezone

    ultimo_login = servidor.user.last_login or timezone.now()

    vinculos_ativos = servidor.vinculos_unidade.filter(
        data_fim__isnull=True
    ).values_list("unidade_id", flat=True)

    os_novas = TarefaInterna.objects.filter(
        unidade_id__in=vinculos_ativos,
        status="PENDENTE",
        data_inicio__gt=ultimo_login,
    ).count()

    producoes_pendentes = Producao.objects.filter(
        servidor_responsavel=servidor,
        status__in=[
            Producao.STATUS_DISTRIBUIDO,
            Producao.STATUS_VER_AJUSTES,
            Producao.STATUS_REVISAR,
        ],
    ).count()

    revisoes_pendentes = 0
    perfil = servidor.vinculos_unidade.filter(
        data_fim__isnull=True
    ).select_related("perfil").first()

    if perfil and perfil.perfil.pode_homologar:
        revisoes_pendentes = Producao.objects.filter(
            os__os_imoveis__isnull=False,
            status="REVISAR",
        ).filter(
            os__encaminhamentos__unidade_interna_destino_id__in=vinculos_ativos
        ).distinct().count()

    total = os_novas + producoes_pendentes + revisoes_pendentes

    return {
        "total": total,
        "os_novas": os_novas,
        "producoes_pendentes": producoes_pendentes,
        "revisoes_pendentes": revisoes_pendentes,
    }
