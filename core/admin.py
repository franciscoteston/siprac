from django.contrib import admin

from core.models import (
    CombinacaoValida,
    Comentario,
    Encaminhamento,
    Finalidade,
    Imovel,
    LogAuditoria,
    MacroetapaLog,
    MetaPesquisa,
    Natureza,
    OS,
    OsImovel,
    OsProcesso,
    PerfilAcesso,
    PermissaoEspecial,
    ProcessoSei,
    Producao,
    ProducaoAtributo,
    ProducaoImovel,
    RegistroPesquisa,
    Servidor,
    ServidorUnidade,
    TarefaInterna,
    TipoDemanda,
    TipoProducao,
    TipoProducaoUnidade,
    UnidadeExterna,
    UnidadeInterna,
)


# ---------------------------------------------------------------------------
# Classes base
# ---------------------------------------------------------------------------


class SomenteLeituraAdmin(admin.ModelAdmin):
    """Admin somente leitura para registros de auditoria e log."""

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Inlines (relacionamentos N:M e dependentes)
# ---------------------------------------------------------------------------


class OsProcessoInline(admin.TabularInline):
    model = OsProcesso
    extra = 0
    autocomplete_fields = ("processo_sei", "encerrado_por")
    verbose_name = "vínculo OS-processo SEI"
    verbose_name_plural = "vínculos OS-processo SEI"


class OsImovelInline(admin.TabularInline):
    model = OsImovel
    extra = 0
    autocomplete_fields = ("imovel",)
    verbose_name = "imóvel vinculado"
    verbose_name_plural = "imóveis vinculados"


class ProducaoImovelInline(admin.TabularInline):
    model = ProducaoImovel
    extra = 0
    autocomplete_fields = ("os_imovel",)
    verbose_name = "imóvel na produção"
    verbose_name_plural = "imóveis na produção"


# ---------------------------------------------------------------------------
# Estrutura e segurança
# ---------------------------------------------------------------------------


@admin.register(Servidor)
class ServidorAdmin(admin.ModelAdmin):
    """Servidores do SGBD."""

    list_display = ("nome", "login", "bloqueado")
    list_filter = ("bloqueado",)
    search_fields = ("nome", "login")
    ordering = ("nome",)
    exclude = ("senha_hash", "salt")
    readonly_fields = (
        "data_ultimo_acesso",
        "tentativas_falhas",
        "token_reset_senha",
    )


@admin.register(UnidadeInterna)
class UnidadeInternaAdmin(admin.ModelAdmin):
    """Unidades internas da DAI."""

    list_display = ("sigla", "nome")
    search_fields = ("sigla", "nome")
    ordering = ("sigla",)


@admin.register(ServidorUnidade)
class ServidorUnidadeAdmin(admin.ModelAdmin):
    """Vínculos de lotação servidor-unidade."""

    list_display = [
        "servidor",
        "unidade",
        "perfil",
        "cargo",
        "data_inicio",
        "data_fim",
    ]
    list_filter = ["unidade", "perfil", "data_fim"]
    search_fields = [
        "servidor__nome",
        "servidor__login",
    ]
    ordering = ["servidor__nome", "unidade__sigla"]
    raw_id_fields = ["servidor"]
    autocomplete_fields = ("unidade", "perfil")
    date_hierarchy = "data_inicio"


@admin.register(PerfilAcesso)
class PerfilAcessoAdmin(admin.ModelAdmin):
    """Perfis de acesso e permissões."""

    list_display = [
        "nome",
        "visibilidade",
        "pode_criar_os",
        "pode_encerrar_os",
        "pode_homologar",
        "admin_sistema",
    ]
    list_editable = [
        "visibilidade",
        "pode_criar_os",
        "pode_encerrar_os",
        "pode_homologar",
        "admin_sistema",
    ]
    fieldsets = [
        ("Identificação", {
            "fields": ["nome"],
        }),
        ("Visibilidade", {
            "fields": ["visibilidade"],
            "description": (
                "UNIDADE: só vê OSs da própria unidade. "
                "DEPARTAMENTO: vê todas (consulta e entrada). "
                "TOTAL: acesso completo a todas as OSs."
            ),
        }),
        ("Permissões operacionais", {
            "fields": [
                "pode_criar_os",
                "pode_encerrar_os",
                "pode_homologar",
                "pode_criar_os_interna",
                "visibilidade_total",
                "admin_sistema",
            ],
        }),
    ]
    search_fields = ("nome",)
    ordering = ("nome",)


@admin.register(PermissaoEspecial)
class PermissaoEspecialAdmin(admin.ModelAdmin):
    """Permissões especiais temporárias."""

    list_display = (
        "servidor",
        "tipo_permissao",
        "data_inicio",
        "data_fim",
        "concedida_por",
    )
    list_filter = ("tipo_permissao",)
    search_fields = ("servidor__nome", "tipo_permissao")
    autocomplete_fields = ("servidor", "concedida_por")
    ordering = ("-data_inicio",)
    date_hierarchy = "data_inicio"


# ---------------------------------------------------------------------------
# Externo
# ---------------------------------------------------------------------------


@admin.register(UnidadeExterna)
class UnidadeExternaAdmin(admin.ModelAdmin):
    """Unidades externas para encaminhamentos."""

    list_display = ("sigla", "nome", "espera_retorno_padrao", "ativa")
    list_filter = ("ativa", "espera_retorno_padrao")
    search_fields = ("sigla", "nome")
    ordering = ("nome",)


# ---------------------------------------------------------------------------
# Classificação (domínio)
# ---------------------------------------------------------------------------


@admin.register(Natureza)
class NaturezaAdmin(admin.ModelAdmin):
    """Naturezas de classificação da OS."""

    list_display = ("descricao", "ativa")
    list_filter = ("ativa",)
    search_fields = ("descricao",)
    ordering = ("descricao",)


@admin.register(TipoDemanda)
class TipoDemandaAdmin(admin.ModelAdmin):
    """Requerimentos da OS."""

    list_display = ("descricao", "ativa")
    list_filter = ("ativa",)
    search_fields = ("descricao",)
    ordering = ("descricao",)


@admin.register(Finalidade)
class FinalidadeAdmin(admin.ModelAdmin):
    """Finalidades de classificação da OS."""

    list_display = ("descricao", "ativa")
    list_filter = ("ativa",)
    search_fields = ("descricao",)
    ordering = ("descricao",)


@admin.register(CombinacaoValida)
class CombinacaoValidaAdmin(admin.ModelAdmin):
    """Combinações válidas natureza / tipo / finalidade."""

    list_display = ("natureza", "tipo_demanda", "finalidade")
    list_filter = ("natureza", "tipo_demanda", "finalidade")
    search_fields = (
        "natureza__descricao",
        "tipo_demanda__descricao",
        "finalidade__descricao",
    )
    autocomplete_fields = ("natureza", "tipo_demanda", "finalidade")
    ordering = ("natureza", "tipo_demanda", "finalidade")


# ---------------------------------------------------------------------------
# Imóveis
# ---------------------------------------------------------------------------


@admin.register(Imovel)
class ImovelAdmin(admin.ModelAdmin):
    """Identidade do imóvel (inscrição cadastral ou ISIC)."""

    list_display = (
        "tipo_identificacao",
        "inscricao_cadastral",
        "codigo_isic",
    )
    list_filter = ("tipo_identificacao",)
    search_fields = (
        "inscricao_cadastral",
        "codigo_isic",
    )
    ordering = ("inscricao_cadastral", "codigo_isic")


@admin.register(OsImovel)
class OsImovelAdmin(admin.ModelAdmin):
    """Vínculos OS-imóvel com dados cadastrais."""

    list_display = (
        "os",
        "imovel",
        "nom_logradouro",
        "bairro",
        "exercicio_referencia",
        "origem_dados",
    )
    list_filter = ("origem_dados",)
    search_fields = (
        "os__numero_os",
        "imovel__inscricao_cadastral",
        "imovel__codigo_isic",
        "nom_logradouro",
        "bairro",
    )
    autocomplete_fields = ("os", "imovel", "vinculado_por")
    ordering = ("os", "imovel")


@admin.register(ProducaoImovel)
class ProducaoImovelAdmin(admin.ModelAdmin):
    """Imóveis abrangidos por uma produção."""

    list_display = ("producao", "os_imovel", "grupo_ref")
    list_filter = ("grupo_ref",)
    search_fields = (
        "producao__numero_producao",
        "os_imovel__imovel__inscricao_cadastral",
        "os_imovel__imovel__codigo_isic",
        "grupo_ref",
    )
    autocomplete_fields = ("producao", "os_imovel")
    ordering = ("producao", "os_imovel")


# ---------------------------------------------------------------------------
# OS e ciclo de vida
# ---------------------------------------------------------------------------


@admin.register(OS)
class OSAdmin(admin.ModelAdmin):
    """Ordens de serviço."""

    list_display = (
        "numero_os",
        "prioridade",
        "natureza",
        "tipo_demanda",
        "finalidade",
        "os_interna",
        "pendente_confirmacao",
        "data_criacao_sgbd",
        "data_entrada_divisao",
        "criado_por",
    )
    list_filter = (
        "prioridade",
        "os_interna",
        "pendente_confirmacao",
        "natureza",
        "tipo_demanda",
    )
    search_fields = ("numero_os", "observacao")
    autocomplete_fields = (
        "natureza",
        "tipo_demanda",
        "finalidade",
        "criado_por",
    )
    readonly_fields = ("data_criacao_sgbd",)
    inlines = (OsProcessoInline, OsImovelInline)
    ordering = ("-data_criacao_sgbd",)
    date_hierarchy = "data_criacao_sgbd"


@admin.register(ProcessoSei)
class ProcessoSeiAdmin(admin.ModelAdmin):
    """Processos SEI."""

    list_display = ("numero_processo", "data_abertura_sei")
    search_fields = ("numero_processo",)
    ordering = ("numero_processo",)
    date_hierarchy = "data_abertura_sei"


@admin.register(OsProcesso)
class OsProcessoAdmin(admin.ModelAdmin):
    """Vínculos OS-processo SEI (também editável via inline na OS)."""

    list_display = (
        "os",
        "processo_sei",
        "tipo_vinculo",
        "data_entrada_divisao",
        "data_encerramento",
        "encerrado_por",
    )
    list_filter = ("tipo_vinculo",)
    search_fields = ("os__numero_os", "processo_sei__numero_processo")
    autocomplete_fields = ("os", "processo_sei", "encerrado_por")
    ordering = ("os", "tipo_vinculo")
    date_hierarchy = "data_entrada_divisao"


@admin.register(MacroetapaLog)
class MacroetapaLogAdmin(SomenteLeituraAdmin):
    """Histórico de macroetapas (somente consulta)."""

    list_display = (
        "os",
        "macroetapa",
        "data_hora",
        "servidor",
        "automatico",
    )
    list_filter = ("macroetapa", "automatico")
    search_fields = ("os__numero_os", "macroetapa", "servidor__nome")
    ordering = ("-data_hora",)
    date_hierarchy = "data_hora"


@admin.register(Encaminhamento)
class EncaminhamentoAdmin(admin.ModelAdmin):
    """Encaminhamentos da OS."""

    list_display = (
        "os",
        "etapa_interna",
        "tipo_macroetapa",
        "unidade_interna_origem",
        "servidor_origem",
        "unidade_interna_destino",
        "servidor_destino",
        "aguarda_retorno",
        "data_hora",
    )
    list_filter = (
        "etapa_interna",
        "tipo_macroetapa",
        "aguarda_retorno",
        "unidade_interna_origem",
    )
    search_fields = ("os__numero_os", "etapa_interna", "observacao")
    autocomplete_fields = (
        "os",
        "unidade_interna_origem",
        "servidor_origem",
        "unidade_interna_destino",
        "servidor_destino",
        "unidade_externa_destino",
    )
    readonly_fields = ("data_hora",)
    ordering = ("-data_hora",)
    date_hierarchy = "data_hora"


@admin.register(TarefaInterna)
class TarefaInternaAdmin(admin.ModelAdmin):
    """Tarefas internas das unidades."""

    list_display = (
        "os",
        "unidade",
        "servidor",
        "etapa_interna",
        "status",
        "data_inicio",
        "data_conclusao",
    )
    list_filter = ("etapa_interna", "status", "unidade")
    search_fields = ("os__numero_os", "servidor__nome", "etapa_interna")
    autocomplete_fields = ("os", "encaminhamento", "unidade", "servidor")
    ordering = ("-data_inicio",)
    date_hierarchy = "data_inicio"


# ---------------------------------------------------------------------------
# Comentários
# ---------------------------------------------------------------------------


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = ("os", "producao", "origem", "servidor", "data_hora")
    list_filter = ("origem",)
    search_fields = ("texto", "os__numero_os", "servidor__nome")
    autocomplete_fields = ("os", "producao", "servidor")
    ordering = ("-data_hora",)


# ---------------------------------------------------------------------------
# Produção
# ---------------------------------------------------------------------------


@admin.register(Producao)
class ProducaoAdmin(admin.ModelAdmin):
    """Produções geradas pelas OS."""

    list_display = (
        "numero_producao",
        "numero_sei",
        "os",
        "tipo_producao",
        "status",
        "autor_trabalho",
        "ano",
        "criado_por",
        "homologado_por",
        "data_enviado",
    )
    list_filter = ("status", "tipo_producao", "ano")
    search_fields = ("numero_producao", "numero_sei", "os__numero_os")
    autocomplete_fields = (
        "os",
        "tipo_producao",
        "criado_por",
        "homologado_por",
        "autor_trabalho",
        "unidade",
    )
    inlines = (ProducaoImovelInline,)
    ordering = ("-ano", "numero_producao")
    date_hierarchy = "data_enviado"


@admin.register(ProducaoAtributo)
class ProducaoAtributoAdmin(admin.ModelAdmin):
    """Atributos adicionais de produção."""

    list_display = ("producao", "chave", "valor")
    search_fields = ("producao__numero_producao", "chave", "valor")
    autocomplete_fields = ("producao",)
    ordering = ("producao", "chave")


@admin.register(TipoProducao)
class TipoProducaoAdmin(admin.ModelAdmin):
    """Tipos de produção técnica."""

    list_display = (
        "prefixo",
        "descricao",
        "subtipo",
        "tem_numeracao_sequencial",
        "numero_manual",
        "ativo",
    )
    list_filter = ("ativo", "tem_numeracao_sequencial", "numero_manual")
    search_fields = ("prefixo", "descricao", "subtipo")
    ordering = ("prefixo", "subtipo")


@admin.register(TipoProducaoUnidade)
class TipoProducaoUnidadeAdmin(admin.ModelAdmin):
    """Competências por unidade interna para tipos de produção."""

    list_display = ("tipo_producao", "unidade_interna")
    list_filter = ("unidade_interna",)
    autocomplete_fields = ("tipo_producao", "unidade_interna")
    ordering = ("tipo_producao__prefixo", "unidade_interna__sigla")


# ---------------------------------------------------------------------------
# Pesquisa
# ---------------------------------------------------------------------------


@admin.register(RegistroPesquisa)
class RegistroPesquisaAdmin(admin.ModelAdmin):
    """Registros de pesquisa de dados."""

    list_display = (
        "numero_registro",
        "servidor",
        "tipo_pesquisa",
        "tipo_fonte",
        "data_registro",
        "mes_referencia",
        "ano_referencia",
    )
    list_filter = ("tipo_pesquisa", "tipo_fonte", "ano_referencia")
    search_fields = ("numero_registro", "servidor__nome", "observacao")
    autocomplete_fields = ("servidor", "imovel")
    ordering = ("-data_registro",)
    date_hierarchy = "data_registro"


@admin.register(MetaPesquisa)
class MetaPesquisaAdmin(admin.ModelAdmin):
    """Metas de pesquisa (individual ou coletiva)."""

    list_display = (
        "tipo_meta",
        "servidor",
        "unidade",
        "tipo_pesquisa",
        "mes",
        "ano",
        "quantidade_meta",
        "criado_por",
    )
    list_filter = ("tipo_meta", "tipo_pesquisa", "ano")
    search_fields = ("servidor__nome", "unidade__sigla", "tipo_meta")
    autocomplete_fields = ("servidor", "unidade", "criado_por")
    ordering = ("-ano", "-mes")


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(SomenteLeituraAdmin):
    """Logs de auditoria (somente consulta)."""

    list_display = (
        "data_hora",
        "servidor",
        "entidade",
        "entidade_id",
        "operacao",
        "campo_alterado",
        "justificativa",
    )
    list_filter = ("entidade", "operacao")
    search_fields = (
        "entidade",
        "operacao",
        "campo_alterado",
        "servidor__nome",
        "justificativa",
    )
    ordering = ("-data_hora",)
    date_hierarchy = "data_hora"
