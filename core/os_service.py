import datetime

from django.db.models import Case, CharField, Count, F, OuterRef, Q, Subquery, Value, When
from django.utils import timezone

from core.models import Encaminhamento, OS, OsUnidadeStatus, Producao, TarefaInterna

CHAVE_ENTRADA_DIVISAO = "Entrada na Divisão"


def is_primeiro_encaminhamento(os):
    """
    Retorna True se a OS ainda não foi encaminhada para
    nenhuma unidade operacional (nenhum OsUnidadeStatus existe).
    """
    return not OsUnidadeStatus.objects.filter(os=os).exists()


def os_editavel_para_usuario(os, request):
    """
    Retorna True se o usuário logado pode editar a OS.

    Regras:
    - Visibilidade TOTAL ou DEPARTAMENTO: sempre pode editar
    - Visibilidade UNIDADE: só pode editar se OsUnidadeStatus
      da sua unidade for ABERTA ou REABERTA
    - Se OsUnidadeStatus for CONCLUIDA ou SOMENTE_LEITURA:
      somente leitura
    """
    visibilidade = getattr(request, "visibilidade", "UNIDADE")

    if visibilidade in ("TOTAL", "DEPARTAMENTO"):
        return True

    vinculo = getattr(request, "vinculo_ativo", None)
    if not vinculo:
        return False

    # UNIDADE — verificar OsUnidadeStatus
    try:
        status = OsUnidadeStatus.objects.get(
            os=os,
            unidade=vinculo.unidade,
        )
        return status.status in ("ABERTA", "REABERTA")
    except OsUnidadeStatus.DoesNotExist:
        return False


def _ativar_os_na_unidade(os, unidade, servidor, status="ABERTA"):
    """
    Ativa ou reativa a OS na unidade (status ABERTA ou REABERTA).

    Sempre atualiza data_inicio_ciclo e aberta_por quando o status passa
    a ABERTA/REABERTA a partir de outro estado, ou na criação do registro.
    Se já estiver no mesmo status ativo, não reinicia o ciclo.
    Limpa prazo_previsto ao iniciar novo ciclo.
    """
    if status not in ("ABERTA", "REABERTA"):
        raise ValueError("status deve ser ABERTA ou REABERTA")

    agora = timezone.now()
    status_obj, criado = OsUnidadeStatus.objects.get_or_create(
        os=os,
        unidade=unidade,
        defaults={
            "aberta_por": servidor,
            "status": status,
            "data_inicio_ciclo": agora,
            "prazo_previsto": None,
        },
    )
    if criado:
        return status_obj

    ja_ativo = status_obj.status in ("ABERTA", "REABERTA")
    mesmo_status = status_obj.status == status
    if ja_ativo and mesmo_status and status_obj.data_inicio_ciclo:
        return status_obj

    status_obj.status = status
    status_obj.data_inicio_ciclo = agora
    status_obj.data_conclusao = None
    status_obj.aberta_por = servidor
    status_obj.prazo_previsto = None
    status_obj.save(
        update_fields=[
            "status",
            "data_inicio_ciclo",
            "data_conclusao",
            "aberta_por",
            "prazo_previsto",
        ],
    )
    return status_obj


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
            defaults={
                "aberta_por": servidor,
                "data_inicio_ciclo": timezone.now(),
            },
        )
        if status_origem.status in ("ABERTA", "REABERTA"):
            status_origem.status = "CONCLUIDA"
            status_origem.data_conclusao = timezone.now()
            status_origem.concluida_por = servidor
            status_origem.manter_aberta = False
            status_origem.save()
    elif unidade_origem and manter_aberta:
        status_origem = _ativar_os_na_unidade(
            os,
            unidade_origem,
            servidor,
            status="ABERTA",
        )
        if not status_origem.manter_aberta:
            status_origem.manter_aberta = True
            status_origem.save(update_fields=["manter_aberta"])

    if unidade_destino:
        _ativar_os_na_unidade(
            os,
            unidade_destino,
            servidor,
            status="ABERTA",
        )


def inicio_ciclo_prazo_os(os):
    """
    Marco do ciclo vigente do prazo global da OS.

    Último Encaminhamento que configura Atendimento Externo; se não houver,
    usa a data de criação da OS.
    """
    ultimo_externo = (
        Encaminhamento.objects.filter(os=os)
        .filter(
            Q(tipo_macroetapa=Encaminhamento.TIPO_MACROETAPA_ATENDIMENTO_EXTERNO)
            | Q(unidade_externa_destino__isnull=False),
        )
        .order_by("-data_hora", "-id")
        .first()
    )
    if ultimo_externo:
        return ultimo_externo.data_hora
    return os.data_criacao_sgbd


def inicio_ciclo_prazo_unidade(status_unidade):
    """Início do ciclo vigente do prazo na unidade."""
    return status_unidade.data_inicio_ciclo or status_unidade.data_abertura


def _prazo_preenchido_no_ciclo(entidade, entidade_id, campo, inicio_ciclo):
    """True se já houve preenchimento (valor_novo não vazio) do campo no ciclo."""
    from core.models import LogAuditoria

    qs = LogAuditoria.objects.filter(
        entidade=entidade,
        entidade_id=entidade_id,
        campo_alterado=campo,
    ).exclude(valor_novo__isnull=True).exclude(valor_novo="")
    if inicio_ciclo is not None:
        qs = qs.filter(data_hora__gte=inicio_ciclo)
    return qs.exists()


def historico_prazo_os(os):
    """Logs de OS.prazo_data no ciclo vigente (para exibição futura)."""
    from core.models import LogAuditoria

    inicio = inicio_ciclo_prazo_os(os)
    qs = LogAuditoria.objects.filter(
        entidade="OS",
        entidade_id=os.pk,
        campo_alterado="prazo_data",
    )
    if inicio is not None:
        qs = qs.filter(data_hora__gte=inicio)
    return qs.select_related("servidor").order_by("-data_hora")


def historico_prazo_unidade(status_unidade):
    """Logs de OsUnidadeStatus.prazo_previsto no ciclo vigente."""
    from core.models import LogAuditoria

    inicio = inicio_ciclo_prazo_unidade(status_unidade)
    qs = LogAuditoria.objects.filter(
        entidade="OsUnidadeStatus",
        entidade_id=status_unidade.pk,
        campo_alterado="prazo_previsto",
    )
    if inicio is not None:
        qs = qs.filter(data_hora__gte=inicio)
    return qs.select_related("servidor").order_by("-data_hora")


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
        etapa_interna="ENTRADA",
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
        "NOTIFICACAO": "bi-bell",
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
        "NOTIFICACAO": "info",
        "ENCERRADO": "success",
        "ENCERRAMENTO": "success",
    }.get(tipo, "secondary")


def timeline_os(os):
    """
    Retorna timeline unificada da OS: encaminhamentos + encerramento.
    Substitui MacroetapaLog + Encaminhamento separados.
    """
    eventos = []

    # Buscar data_entrada_divisao do processo principal
    processo_principal = os.processos_vinculados.filter(
        tipo_vinculo="PRINCIPAL"
    ).first()

    if processo_principal and processo_principal.data_entrada_divisao:
        data_entrada = datetime.datetime.combine(
            processo_principal.data_entrada_divisao,
            datetime.time.min,
            tzinfo=timezone.get_current_timezone(),
        )
    else:
        data_entrada = os.data_criacao_sgbd

    eventos.append({
        "tipo": "ENTRADA_DIVISAO",
        "label": "Entrada na Divisão",
        "data_hora": data_entrada,
        "exibir_hora": False,  # novo campo para controle
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
        "NOTIFICACAO": "Notificação",
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
            "etapa_interna_label": (
                "" if enc.automatico
                else ETAPAS_INTERNAS_LABELS.get(enc.etapa_interna or "", enc.etapa_interna or "")
            ),
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
    """Registra ATENDIMENTO_INTERNO quando há produção não cancelada e ainda não está nesse estado."""
    producoes_ativas = Producao.objects.filter(os=os).exclude(
        status=Producao.STATUS_CANCELADO,
    )
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


def registrar_em_atendimento_na_unidade(os, unidade, servidor=None):
    """
    Registra encaminhamento automático com etapa_interna=EM_ATENDIMENTO
    na unidade onde a produção foi criada.
    Só registra se a etapa atual da unidade não for já EM_ATENDIMENTO.
    """
    tarefa_atual = (
        TarefaInterna.objects.filter(
            os=os,
            unidade=unidade,
            status="PENDENTE",
        )
        .order_by("-data_inicio")
        .first()
    )

    if tarefa_atual and tarefa_atual.etapa_interna == "EM_ATENDIMENTO":
        return False

    Encaminhamento.objects.create(
        os=os,
        unidade_interna_origem=unidade,
        servidor_origem=servidor,
        unidade_interna_destino=unidade,
        servidor_destino=None,
        etapa_interna="EM_ATENDIMENTO",
        tipo_macroetapa=None,
        data_hora=timezone.now(),
        aguarda_retorno=False,
        automatico=True,
        observacao="Derivado automaticamente: produção registrada na unidade.",
        manter_aberta_na_unidade=True,
    )

    TarefaInterna.objects.filter(
        os=os,
        unidade=unidade,
        status="PENDENTE",
    ).update(etapa_interna="EM_ATENDIMENTO")

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
    "ENTRADA": "Entrada",
    "TRIAGEM": "Triagem",
    "EM_ATENDIMENTO": "Em atendimento",
    "DEVOLUCAO": "Devolução",
    "SOLICITACAO_AJUSTE": "Solicitação de ajuste",
    "HOMOLOGACAO": "Homologação",
    "CONCLUIDA": "Concluída",
    # legado
    "ANALISE": "Análise",
    "REVISAO": "Revisão",
    "CONCLUSAO": "Conclusão",
    "SISTEMA": "Sistema",
}


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
                "enviadas_mes": 0,
                "_os_ids": [],
            }
        distribuicao[chave]["total"] += 1
        distribuicao[chave]["_os_ids"].append(os_id)

    resultado = []
    for dados in distribuicao.values():
        os_ids_grupo = dados.pop("_os_ids")
        dados["enviadas_mes"] = Producao.objects.filter(
            os_id__in=os_ids_grupo,
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
    """
    from django.utils import timezone

    ultimo_login = servidor.user.last_login or timezone.now()

    vinculos_ativos = list(
        servidor.vinculos_unidade.filter(
            data_fim__isnull=True
        ).values_list("unidade_id", flat=True)
    )

    os_novas = TarefaInterna.objects.filter(
        unidade_id__in=vinculos_ativos,
        status="PENDENTE",
        data_inicio__gt=ultimo_login,
    ).count()

    return {
        "total": os_novas,
        "os_novas": os_novas,
    }
