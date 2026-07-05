from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Bloco A — Estrutura organizacional e segurança
# ---------------------------------------------------------------------------


class Servidor(models.Model):
    """Servidor público com credenciais e controle de acesso ao SGBD."""

    nome = models.CharField(max_length=255)
    login = models.CharField(max_length=255, unique=True)
    senha_hash = models.CharField(max_length=255)
    salt = models.CharField(max_length=255)
    data_ultimo_acesso = models.DateField(null=True, blank=True)
    tentativas_falhas = models.IntegerField(default=0)
    bloqueado = models.BooleanField(default=False)
    token_reset_senha = models.CharField(max_length=255, null=True, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="servidor",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "SERVIDOR"
        verbose_name = "servidor"
        verbose_name_plural = "servidores"

    def __str__(self):
        return self.nome


class PerfilAcesso(models.Model):
    """Perfil de permissões vinculado ao cargo do servidor na unidade."""

    nome = models.CharField(max_length=255)
    pode_criar_os = models.BooleanField(default=False)
    pode_encerrar_os = models.BooleanField(default=False)
    pode_criar_os_interna = models.BooleanField(default=False)
    pode_homologar = models.BooleanField(default=False)
    visibilidade_total = models.BooleanField(default=False)
    admin_sistema = models.BooleanField(default=False)

    class Meta:
        db_table = "PERFIL_ACESSO"
        verbose_name = "perfil de acesso"
        verbose_name_plural = "perfis de acesso"

    def __str__(self):
        return self.nome


class UnidadeInterna(models.Model):
    """Unidade interna da DAI (DAI, EAV, ESJL, EPGV)."""

    sigla = models.CharField(max_length=50)
    nome = models.CharField(max_length=255)

    class Meta:
        db_table = "UNIDADE_INTERNA"
        verbose_name = "unidade interna"
        verbose_name_plural = "unidades internas"

    def __str__(self):
        return self.sigla


class UnidadeExterna(models.Model):
    """Unidade externa à DAI para encaminhamentos com ou sem retorno."""

    sigla = models.CharField(max_length=50, null=True, blank=True)
    nome = models.CharField(max_length=255)
    espera_retorno_padrao = models.BooleanField(default=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "UNIDADE_EXTERNA"
        verbose_name = "unidade externa"
        verbose_name_plural = "unidades externas"

    def __str__(self):
        return self.nome


class ServidorUnidade(models.Model):
    """Vínculo de lotação do servidor em uma unidade, com perfil e vigência."""

    servidor = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="vinculos_unidade",
    )
    unidade = models.ForeignKey(
        UnidadeInterna,
        on_delete=models.PROTECT,
        related_name="vinculos_servidor",
    )
    perfil = models.ForeignKey(
        PerfilAcesso,
        on_delete=models.PROTECT,
        related_name="vinculos_servidor",
    )
    cargo = models.CharField(max_length=255)
    substituto = models.BooleanField(default=False)
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "SERVIDOR_UNIDADE"
        verbose_name = "vínculo servidor-unidade"
        verbose_name_plural = "vínculos servidor-unidade"

    def __str__(self):
        return f"{self.servidor} — {self.unidade}"


class PermissaoEspecial(models.Model):
    """Permissão temporária concedida a um servidor (ex.: visibilidade cross-unidade)."""

    servidor = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="permissoes_especiais",
    )
    tipo_permissao = models.CharField(max_length=255)
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)
    concedida_por = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="permissoes_concedidas",
    )

    class Meta:
        db_table = "PERMISSAO_ESPECIAL"
        verbose_name = "permissão especial"
        verbose_name_plural = "permissões especiais"

    def __str__(self):
        return f"{self.servidor} — {self.tipo_permissao}"


# ---------------------------------------------------------------------------
# Classificação da OS
# ---------------------------------------------------------------------------


class Natureza(models.Model):
    """Primeira dimensão de classificação da OS (ex.: Tributário – IPTU)."""

    descricao = models.CharField(max_length=255)
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "NATUREZA"
        verbose_name = "natureza"
        verbose_name_plural = "naturezas"

    def __str__(self):
        return self.descricao


class TipoDemanda(models.Model):
    """Segunda dimensão de classificação da OS (ex.: Requerimento IPTU)."""

    descricao = models.CharField(max_length=255)
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "TIPO_DEMANDA"
        verbose_name = "Requerimento"
        verbose_name_plural = "Requerimentos"

    def __str__(self):
        return self.descricao


class Finalidade(models.Model):
    """Terceira dimensão de classificação da OS (ex.: Desapropriação Parcial)."""

    descricao = models.CharField(max_length=255)
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "FINALIDADE"
        verbose_name = "finalidade"
        verbose_name_plural = "finalidades"

    def __str__(self):
        return self.descricao


class CombinacaoValida(models.Model):
    """Combinação permitida entre natureza, tipo de demanda e finalidade."""

    natureza = models.ForeignKey(
        Natureza,
        on_delete=models.PROTECT,
        related_name="combinacoes_validas",
    )
    tipo_demanda = models.ForeignKey(
        TipoDemanda,
        on_delete=models.PROTECT,
        related_name="combinacoes_validas",
    )
    finalidade = models.ForeignKey(
        Finalidade,
        on_delete=models.PROTECT,
        related_name="combinacoes_validas",
    )

    class Meta:
        db_table = "COMBINACAO_VALIDA"
        verbose_name = "combinação válida"
        verbose_name_plural = "combinações válidas"
        constraints = [
            models.UniqueConstraint(
                fields=["natureza", "tipo_demanda", "finalidade"],
                name="combinacao_valida_unica",
            ),
        ]

    def __str__(self):
        return f"{self.natureza} / {self.tipo_demanda} / {self.finalidade}"


# ---------------------------------------------------------------------------
# Imóveis e tipos de produção
# ---------------------------------------------------------------------------


class Imovel(models.Model):
    """Identidade do imóvel (inscrição cadastral ou código ISIC)."""

    TIPO_IDENTIFICACAO = [
        ("CADASTRAL", "Cadastral"),
        ("ISIC", "ISIC"),
    ]

    tipo_identificacao = models.CharField(max_length=10, choices=TIPO_IDENTIFICACAO)
    inscricao_cadastral = models.IntegerField(null=True, blank=True, unique=True)
    codigo_isic = models.CharField(max_length=20, null=True, blank=True, unique=True)
    observacao_interna = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "imovel"
        verbose_name = "Imóvel"
        verbose_name_plural = "Imóveis"
        indexes = [
            models.Index(fields=["inscricao_cadastral"]),
            models.Index(fields=["codigo_isic"]),
        ]

    def __str__(self):
        if self.inscricao_cadastral:
            return str(self.inscricao_cadastral)
        return self.codigo_isic or "Imóvel sem identificação"


class TipoProducao(models.Model):
    """Tipo de produção técnica (LA, PT, PF, despacho, etc.)."""

    prefixo = models.CharField(max_length=50)
    descricao = models.CharField(max_length=255)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "TIPO_PRODUCAO"
        verbose_name = "tipo de produção"
        verbose_name_plural = "tipos de produção"

    def __str__(self):
        return f"{self.prefixo} — {self.descricao}"


class TipoProducaoUnidade(models.Model):
    """Competência de uma unidade interna para elaborar determinado tipo de produção."""

    tipo_producao = models.ForeignKey(
        TipoProducao,
        on_delete=models.PROTECT,
        related_name="unidades_competentes",
    )
    unidade_interna = models.ForeignKey(
        UnidadeInterna,
        on_delete=models.PROTECT,
        related_name="tipos_producao",
    )

    class Meta:
        db_table = "tipo_producao_unidade"
        verbose_name = "Competência por unidade"
        verbose_name_plural = "Competências por unidade"
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_producao", "unidade_interna"],
                name="tipo_producao_unidade_unico",
            ),
        ]

    def __str__(self):
        return f"{self.tipo_producao.prefixo} — {self.unidade_interna.sigla}"


class ProcessoSei(models.Model):
    """Processo registrado no SEI — apenas dados imutáveis de identificação."""

    numero_processo = models.CharField(max_length=255, unique=True)
    data_abertura_sei = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data de criação no SEI",
    )

    class Meta:
        db_table = "PROCESSO_SEI"
        verbose_name = "processo SEI"
        verbose_name_plural = "processos SEI"

    def __str__(self):
        return self.numero_processo


# ---------------------------------------------------------------------------
# OS e ciclo de vida
# ---------------------------------------------------------------------------


class OS(models.Model):
    """Ordem de Serviço — entidade central do ciclo de vida da demanda na DAI."""

    PRAZO_TIPO_CHOICES = [
        ("SEM_PRIORIDADE", "Sem prioridade"),
        ("PRIORIDADE_GS", "Prioridade - GS"),
        ("PRIORIDADE_GP", "Prioridade - GP"),
        ("PRIORIDADE_IDOSO", "Prioridade - Idoso"),
        ("OUVIDORIA", "Ouvidoria"),
        ("PRIORIDADE_PGM", "Prioridade - PGM"),
        ("JUDICIAL_COM_PRAZO", "Judicial com prazo"),
        ("PRAZO_LEGAL", "Prazo legal"),
        ("PRAZO_CONTRATUAL", "Prazo contratual"),
    ]

    numero_os = models.CharField(max_length=255, unique=True)
    data_criacao_sgbd = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Data de criação no SIPRAC",
    )
    data_entrada_divisao = models.DateField(null=True, blank=True)
    os_interna = models.BooleanField(default=False)
    pendente_confirmacao = models.BooleanField(default=False)
    prioridade = models.CharField(max_length=255, default="NORMAL")
    natureza = models.ForeignKey(
        Natureza,
        on_delete=models.PROTECT,
        related_name="ordens_servico",
    )
    tipo_demanda = models.ForeignKey(
        TipoDemanda,
        on_delete=models.PROTECT,
        related_name="ordens_servico",
        verbose_name="Requerimento",
    )
    finalidade = models.ForeignKey(
        Finalidade,
        on_delete=models.PROTECT,
        related_name="ordens_servico",
    )
    criado_por = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="ordens_servico_criadas",
    )
    observacao = models.TextField(null=True, blank=True)
    apelido = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Apelido",
    )
    prazo_tipo = models.CharField(
        max_length=30,
        choices=PRAZO_TIPO_CHOICES,
        default="SEM_PRIORIDADE",
    )
    prazo_data = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data do prazo",
    )

    class Meta:
        db_table = "OS"
        verbose_name = "ordem de serviço"
        verbose_name_plural = "ordens de serviço"
        ordering = ["-data_criacao_sgbd"]

    def __str__(self):
        return self.numero_os


class Comentario(models.Model):
    """Comentário vinculado à OS ou a uma produção."""

    ORIGEM = [
        ("OS", "OS"),
        ("PRODUCAO", "Produção"),
    ]

    os = models.ForeignKey(
        OS,
        on_delete=models.PROTECT,
        related_name="comentarios",
    )
    producao = models.ForeignKey(
        "Producao",
        on_delete=models.PROTECT,
        related_name="comentarios",
        null=True,
        blank=True,
    )
    origem = models.CharField(max_length=10, choices=ORIGEM)
    texto = models.TextField()
    servidor = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="comentarios",
    )
    data_hora = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "comentario"
        verbose_name = "Comentário"
        verbose_name_plural = "Comentários"
        ordering = ["-data_hora"]

    def __str__(self):
        return f"{self.servidor} — {self.data_hora:%d/%m/%Y %H:%M}"


class OsProcesso(models.Model):
    """Vínculo entre uma OS e um processo SEI (principal ou relacionado)."""

    os = models.ForeignKey(
        OS,
        on_delete=models.PROTECT,
        related_name="processos_vinculados",
    )
    processo_sei = models.ForeignKey(
        ProcessoSei,
        on_delete=models.PROTECT,
        related_name="vinculos_os",
    )
    tipo_vinculo = models.CharField(max_length=255)
    data_vinculo = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Data de registro no SIPRAC",
    )
    data_entrada_divisao = models.DateField(null=True, blank=True)
    data_encerramento = models.DateField(null=True, blank=True)
    motivo_encerramento = models.TextField(null=True, blank=True)
    encerrado_por = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="processos_encerrados",
    )

    class Meta:
        db_table = "OS_PROCESSO"
        verbose_name = "vínculo OS-processo SEI"
        verbose_name_plural = "vínculos OS-processo SEI"

    def __str__(self):
        return f"{self.os} — {self.processo_sei}"


class MacroetapaLog(models.Model):
    """Histórico de transições de macroetapa da OS."""

    os = models.ForeignKey(
        OS,
        on_delete=models.PROTECT,
        related_name="macroetapas",
    )
    macroetapa = models.CharField(max_length=255)
    data_hora = models.DateTimeField(auto_now_add=True)
    servidor = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="macroetapas_registradas",
    )
    automatico = models.BooleanField(default=False)
    observacao = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "MACROETAPA_LOG"
        verbose_name = "registro de macroetapa"
        verbose_name_plural = "registros de macroetapa"
        ordering = ["-data_hora"]

    def __str__(self):
        return f"{self.os} — {self.macroetapa}"


class Encaminhamento(models.Model):
    """Tramitação da OS entre unidades, servidores ou destinos externos."""

    TIPO_ACAO_ENTRADA = "ENTRADA"
    TIPO_ACAO_DEVOLUCAO = "DEVOLUCAO"
    TIPO_ACAO_SOLICITACAO_AJUSTE = "SOLICITACAO_AJUSTE"
    TIPO_ACAO_EXTERNO = "EXTERNO"
    TIPO_ACAO_HOMOLOGACAO = "HOMOLOGACAO"
    TIPO_ACAO_CONCLUSAO = "CONCLUSAO"

    TIPO_ACAO_CHOICES = [
        (TIPO_ACAO_ENTRADA, "Entrada"),
        (TIPO_ACAO_DEVOLUCAO, "Devolução"),
        (TIPO_ACAO_SOLICITACAO_AJUSTE, "Solicitação de ajuste"),
        (TIPO_ACAO_EXTERNO, "Externo"),
        (TIPO_ACAO_HOMOLOGACAO, "Homologação"),
        (TIPO_ACAO_CONCLUSAO, "Conclusão"),
    ]

    os = models.ForeignKey(
        OS,
        on_delete=models.PROTECT,
        related_name="encaminhamentos",
    )
    unidade_interna_origem = models.ForeignKey(
        UnidadeInterna,
        on_delete=models.PROTECT,
        related_name="encaminhamentos_origem",
    )
    servidor_origem = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="encaminhamentos_enviados",
    )
    unidade_interna_destino = models.ForeignKey(
        UnidadeInterna,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="encaminhamentos_destino_interno",
    )
    servidor_destino = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="encaminhamentos_recebidos",
    )
    unidade_externa_destino = models.ForeignKey(
        UnidadeExterna,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="encaminhamentos",
    )
    etapa_interna = models.CharField(max_length=255, null=True, blank=True)
    tipo_acao = models.CharField(max_length=255, choices=TIPO_ACAO_CHOICES)
    aguarda_retorno = models.BooleanField(default=False)
    data_retorno_prevista = models.DateField(null=True, blank=True)
    data_retorno_efetiva = models.DateField(null=True, blank=True)
    data_hora = models.DateTimeField(auto_now_add=True)
    observacao = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "ENCAMINHAMENTO"
        verbose_name = "encaminhamento"
        verbose_name_plural = "encaminhamentos"
        ordering = ["-data_hora"]

    def __str__(self):
        return f"{self.os} — {self.tipo_acao} ({self.data_hora})"


class TarefaInterna(models.Model):
    """Tarefa interna da unidade em uma etapa do fluxo (triagem até conclusão)."""

    os = models.ForeignKey(
        OS,
        on_delete=models.PROTECT,
        related_name="tarefas_internas",
    )
    encaminhamento = models.ForeignKey(
        Encaminhamento,
        on_delete=models.PROTECT,
        related_name="tarefas",
    )
    unidade = models.ForeignKey(
        UnidadeInterna,
        on_delete=models.PROTECT,
        related_name="tarefas_internas",
    )
    servidor = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="tarefas_internas",
    )
    etapa_interna = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
    data_inicio = models.DateTimeField()
    data_conclusao = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "TAREFA_INTERNA"
        verbose_name = "tarefa interna"
        verbose_name_plural = "tarefas internas"

    def __str__(self):
        return f"{self.os} — {self.etapa_interna} ({self.status})"


class OsImovel(models.Model):
    """Vínculo entre uma OS e um imóvel, com dados cadastrais do momento."""

    ORIGEM_DADOS = [
        ("SIAT", "SIAT"),
        ("MANUAL", "Manual"),
    ]

    os = models.ForeignKey(
        OS,
        on_delete=models.PROTECT,
        related_name="os_imoveis",
    )
    imovel = models.ForeignKey(
        Imovel,
        on_delete=models.PROTECT,
        related_name="os_imoveis",
    )
    data_vinculo = models.DateTimeField(auto_now_add=True)
    vinculado_por = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="imoveis_vinculados_os",
    )
    num_bloco = models.CharField(max_length=12, null=True, blank=True)
    cod_logradouro = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="CTM",
    )
    nom_logradouro = models.CharField(max_length=255, null=True, blank=True)
    num_endereco = models.CharField(max_length=20, null=True, blank=True)
    num_unidade = models.CharField(max_length=20, null=True, blank=True)
    bairro = models.CharField(max_length=100, null=True, blank=True)
    des_finalidade = models.CharField(max_length=255, null=True, blank=True)
    area_territorial = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    area_construida = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    rh_nome = models.CharField(max_length=20, null=True, blank=True)
    rh_valor = models.IntegerField(null=True, blank=True)
    idf_regiao_homogenea = models.IntegerField(null=True, blank=True)
    latitude = models.DecimalField(
        max_digits=12,
        decimal_places=8,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=12,
        decimal_places=8,
        null=True,
        blank=True,
    )
    coord_x = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
    )
    coord_y = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
    )
    exercicio_referencia = models.IntegerField(null=True, blank=True)
    origem_dados = models.CharField(
        max_length=20,
        choices=ORIGEM_DADOS,
        default="SIAT",
    )

    class Meta:
        db_table = "os_imovel"
        verbose_name = "Imóvel da OS"
        verbose_name_plural = "Imóveis da OS"
        unique_together = [["os", "imovel"]]

    def __str__(self):
        return f"{self.os} — {self.imovel}"


# ---------------------------------------------------------------------------
# Produção
# ---------------------------------------------------------------------------


class Producao(models.Model):
    """Produto gerado pela OS (laudo, parecer, despacho, etc.)."""

    STATUS_ENTRADA = "ENTRADA"
    STATUS_DISTRIBUIDO = "DISTRIBUIDO"
    STATUS_EM_ELABORACAO = "EM_ELABORACAO"
    STATUS_PARA_REVISAO = "PARA_REVISAO"
    STATUS_PARA_AJUSTES = "PARA_AJUSTES"
    STATUS_HOMOLOGADO = "HOMOLOGADO"
    STATUS_CANCELADO = "CANCELADO"

    STATUS_CHOICES = [
        (STATUS_ENTRADA, "Entrada"),
        (STATUS_DISTRIBUIDO, "Distribuído"),
        (STATUS_EM_ELABORACAO, "Em elaboração"),
        (STATUS_PARA_REVISAO, "Para revisão"),
        (STATUS_PARA_AJUSTES, "Para ajustes"),
        (STATUS_HOMOLOGADO, "Homologado"),
        (STATUS_CANCELADO, "Cancelado"),
    ]

    os = models.ForeignKey(
        OS,
        on_delete=models.PROTECT,
        related_name="producoes",
    )
    tipo_producao = models.ForeignKey(
        TipoProducao,
        on_delete=models.PROTECT,
        related_name="producoes",
    )
    numero_producao = models.CharField(max_length=255, null=True, blank=True)
    numero_sei = models.CharField(max_length=255, null=True, blank=True)
    ano = models.IntegerField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ENTRADA,
    )
    servidor_responsavel = models.ForeignKey(
        Servidor,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="producoes_responsavel",
        verbose_name="Servidor responsável",
    )
    revisor = models.ForeignKey(
        Servidor,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="producoes_revisor",
        verbose_name="Revisor",
    )
    modelo_sugerido = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Modelo sugerido",
    )
    autor_trabalho = models.ForeignKey(
        Servidor,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="producoes_autor",
        verbose_name="Autor do trabalho",
    )
    criado_por = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="producoes_criadas",
    )
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name="Data de criação")
    homologado_por = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="producoes_homologadas",
    )
    data_homologacao = models.DateField(null=True, blank=True)
    data_entrega_avaliacao = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data de entrega da avaliação",
    )
    data_entrega_revisao = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data de entrega da revisão",
    )
    data_entrega_ajustes = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data de entrega dos ajustes",
    )
    observacao = models.TextField(null=True, blank=True)
    prazo_interno = models.DateField(
        null=True,
        blank=True,
        verbose_name="Prazo interno",
    )
    mes_cronograma = models.DateField(
        null=True,
        blank=True,
        verbose_name="Mês do cronograma",
    )

    class Meta:
        db_table = "PRODUCAO"
        verbose_name = "produção"
        verbose_name_plural = "produções"

    def __str__(self):
        if self.numero_producao:
            return self.numero_producao
        if self.numero_sei:
            return self.numero_sei
        return f"Produção #{self.pk}"


class ProducaoStatusLog(models.Model):
    """Histórico de transições de status e atribuições da produção."""

    producao = models.ForeignKey(
        Producao,
        on_delete=models.PROTECT,
        related_name="status_logs",
    )
    status_anterior = models.CharField(max_length=20, null=True, blank=True)
    status_novo = models.CharField(max_length=20)
    servidor_origem = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="status_logs_origem",
        null=True,
        blank=True,
    )
    servidor_destino = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="status_logs_destino",
        null=True,
        blank=True,
    )
    unidade_destino = models.ForeignKey(
        UnidadeInterna,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    data_hora = models.DateTimeField(auto_now_add=True)
    justificativa = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "producao_status_log"
        verbose_name = "Log de status da produção"
        verbose_name_plural = "Logs de status da produção"
        ordering = ["data_hora"]

    def __str__(self):
        return f"{self.producao} — {self.status_anterior} → {self.status_novo}"


class ProducaoImovel(models.Model):
    """Imóvel abrangido por uma produção, referenciando o vínculo na OS."""

    producao = models.ForeignKey(
        Producao,
        on_delete=models.PROTECT,
        related_name="producao_imoveis",
    )
    os_imovel = models.ForeignKey(
        OsImovel,
        on_delete=models.PROTECT,
        related_name="producao_imoveis",
    )
    grupo_ref = models.CharField(max_length=10, null=True, blank=True)
    observacao = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "producao_imovel"
        verbose_name = "Imóvel da produção"
        verbose_name_plural = "Imóveis da produção"

    def __str__(self):
        return f"{self.producao} — {self.os_imovel.imovel}"


class ProducaoAtributo(models.Model):
    """Atributo chave-valor adicional de uma produção."""

    producao = models.ForeignKey(
        Producao,
        on_delete=models.PROTECT,
        related_name="atributos",
    )
    chave = models.CharField(max_length=255)
    valor = models.CharField(max_length=255)

    class Meta:
        db_table = "PRODUCAO_ATRIBUTO"
        verbose_name = "atributo de produção"
        verbose_name_plural = "atributos de produção"

    def __str__(self):
        return f"{self.producao} — {self.chave}"


# ---------------------------------------------------------------------------
# Pesquisa de dados
# ---------------------------------------------------------------------------


class RegistroPesquisa(models.Model):
    """Registro de pesquisa de dados (ITBI, ofertas) pelo perfil de pesquisa."""

    servidor = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="registros_pesquisa",
    )
    imovel = models.ForeignKey(
        Imovel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="registros_pesquisa",
    )
    numero_registro = models.CharField(max_length=255)
    tipo_fonte = models.CharField(max_length=255)
    data_registro = models.DateField()
    data_encaminhamento = models.DateField(null=True, blank=True)
    tipo_pesquisa = models.CharField(max_length=255)
    semana_referencia = models.IntegerField(null=True, blank=True)
    mes_referencia = models.IntegerField()
    ano_referencia = models.IntegerField()
    observacao = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "REGISTRO_PESQUISA"
        verbose_name = "registro de pesquisa"
        verbose_name_plural = "registros de pesquisa"

    def __str__(self):
        return self.numero_registro


class MetaPesquisa(models.Model):
    """Meta de produção de pesquisa (individual ou coletiva por unidade)."""

    servidor = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="metas_pesquisa",
    )
    unidade = models.ForeignKey(
        UnidadeInterna,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="metas_pesquisa",
    )
    criado_por = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        related_name="metas_pesquisa_criadas",
    )
    tipo_meta = models.CharField(max_length=255)
    tipo_pesquisa = models.CharField(max_length=255, null=True, blank=True)
    mes = models.IntegerField()
    ano = models.IntegerField()
    quantidade_meta = models.IntegerField()

    class Meta:
        db_table = "META_PESQUISA"
        verbose_name = "meta de pesquisa"
        verbose_name_plural = "metas de pesquisa"

    def __str__(self):
        alvo = self.servidor or self.unidade
        return f"{alvo} — {self.mes}/{self.ano}: {self.quantidade_meta}"


# ---------------------------------------------------------------------------
# Preferências da visão gerencial
# ---------------------------------------------------------------------------


class PreferenciaGerencial(models.Model):
    servidor = models.OneToOneField(
        Servidor,
        on_delete=models.CASCADE,
        related_name="preferencia_gerencial",
    )
    colunas_visiveis = models.JSONField(default=list)

    class Meta:
        db_table = "preferencia_gerencial"
        verbose_name = "preferência gerencial"
        verbose_name_plural = "preferências gerenciais"

    def __str__(self):
        return f"Preferências gerenciais — {self.servidor}"


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------


class LogAuditoria(models.Model):
    """Registro imutável de alterações relevantes para auditoria."""

    servidor = models.ForeignKey(
        Servidor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="logs_auditoria",
    )
    entidade = models.CharField(max_length=255)
    entidade_id = models.IntegerField()
    operacao = models.CharField(max_length=255)
    campo_alterado = models.CharField(max_length=255, null=True, blank=True)
    valor_anterior = models.TextField(null=True, blank=True)
    valor_novo = models.TextField(null=True, blank=True)
    data_hora = models.DateTimeField(auto_now_add=True)
    justificativa = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "LOG_AUDITORIA"
        verbose_name = "log de auditoria"
        verbose_name_plural = "logs de auditoria"
        ordering = ["-data_hora"]

    def __str__(self):
        return f"{self.entidade}#{self.entidade_id} — {self.operacao}"
