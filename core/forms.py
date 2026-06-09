from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import (
    CombinacaoValida,
    Finalidade,
    Imovel,
    Natureza,
    Servidor,
    TipoDemanda,
    TipoProducao,
    UnidadeExterna,
    UnidadeInterna,
)


class OSForm(forms.Form):
    processo_sei_numero = forms.CharField(
        label="Número do processo SEI",
        max_length=255,
    )
    processo_sei_data_entrada = forms.DateField(
        label="Data de entrada na Divisão",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    natureza = forms.ModelChoiceField(
        label="Natureza",
        queryset=Natureza.objects.filter(ativa=True),
    )
    tipo_demanda = forms.ModelChoiceField(
        label="Tipo de demanda",
        queryset=TipoDemanda.objects.none(),
    )
    finalidade = forms.ModelChoiceField(
        label="Finalidade",
        queryset=Finalidade.objects.none(),
    )
    prioridade = forms.ChoiceField(
        label="Prioridade",
        choices=[
            ("NORMAL", "Normal"),
            ("PRIORITARIO", "Prioritário"),
            ("URGENTE", "Urgente"),
        ],
        initial="NORMAL",
    )
    observacao = forms.CharField(
        label="Observação",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "natureza" in self.data:
            try:
                natureza_id = int(self.data.get("natureza"))
            except (TypeError, ValueError):
                natureza_id = None
            if natureza_id:
                self.fields["tipo_demanda"].queryset = TipoDemanda.objects.filter(
                    combinacoes_validas__natureza_id=natureza_id,
                    ativa=True,
                ).distinct()

        if "tipo_demanda" in self.data:
            try:
                tipo_demanda_id = int(self.data.get("tipo_demanda"))
            except (TypeError, ValueError):
                tipo_demanda_id = None
            if tipo_demanda_id:
                self.fields["finalidade"].queryset = Finalidade.objects.filter(
                    combinacoes_validas__tipo_demanda_id=tipo_demanda_id,
                    ativa=True,
                ).distinct()

    def clean(self):
        cleaned_data = super().clean()
        natureza = cleaned_data.get("natureza")
        tipo_demanda = cleaned_data.get("tipo_demanda")
        finalidade = cleaned_data.get("finalidade")

        if natureza and tipo_demanda and finalidade:
            if not CombinacaoValida.objects.filter(
                natureza=natureza,
                tipo_demanda=tipo_demanda,
                finalidade=finalidade,
            ).exists():
                raise ValidationError("Combinação inválida para esta natureza.")

        return cleaned_data


class EncaminhamentoForm(forms.Form):
    tipo_destino = forms.ChoiceField(
        label="Tipo de destino",
        choices=[
            ("INTERNO", "Interno"),
            ("EXTERNO", "Externo"),
        ],
        widget=forms.RadioSelect,
        initial="INTERNO",
    )
    unidade_interna_destino = forms.ModelChoiceField(
        label="Unidade interna destino",
        queryset=UnidadeInterna.objects.all().order_by("sigla"),
        required=False,
    )
    servidor_destino = forms.ModelChoiceField(
        label="Servidor destino",
        queryset=Servidor.objects.all().order_by("nome"),
        required=False,
    )
    unidade_externa_destino = forms.ModelChoiceField(
        label="Unidade externa destino",
        queryset=UnidadeExterna.objects.filter(ativa=True).order_by("nome"),
        required=False,
    )
    etapa_interna = forms.ChoiceField(
        label="Etapa interna",
        choices=[
            ("TRIAGEM", "Triagem"),
            ("ANALISE", "Análise"),
            ("REVISAO", "Revisão"),
            ("HOMOLOGACAO", "Homologação"),
            ("CONCLUSAO", "Conclusão"),
        ],
    )
    tipo_acao = forms.ChoiceField(
        label="Tipo de ação",
        choices=[
            ("ATRIBUICAO", "Atribuição"),
            ("DEVOLUCAO", "Devolução"),
            ("SOLICITACAO_AJUSTE", "Solicitação de ajuste"),
            ("ENCAMINHAMENTO_EXTERNO", "Encaminhamento externo"),
            ("HOMOLOGACAO", "Homologação"),
            ("CONCLUSAO", "Conclusão"),
        ],
    )
    aguarda_retorno = forms.BooleanField(
        label="Aguarda retorno",
        required=False,
        initial=False,
    )
    data_retorno_prevista = forms.DateField(
        label="Data de retorno prevista",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    observacao = forms.CharField(
        label="Observação",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean(self):
        cleaned_data = super().clean()
        tipo_destino = cleaned_data.get("tipo_destino")
        unidade_interna = cleaned_data.get("unidade_interna_destino")
        unidade_externa = cleaned_data.get("unidade_externa_destino")

        if unidade_interna and unidade_externa:
            raise ValidationError(
                "Unidade interna e unidade externa são mutuamente exclusivas."
            )

        if tipo_destino == "INTERNO":
            if not unidade_interna:
                self.add_error(
                    "unidade_interna_destino",
                    "Obrigatório para encaminhamento interno.",
                )
            cleaned_data["unidade_externa_destino"] = None
        elif tipo_destino == "EXTERNO":
            if not unidade_externa:
                self.add_error(
                    "unidade_externa_destino",
                    "Obrigatório para encaminhamento externo.",
                )
            cleaned_data["unidade_interna_destino"] = None
            cleaned_data["servidor_destino"] = None

        return cleaned_data


DESPACHO_VALUE = "DESPACHO"


class ProducaoForm(forms.Form):
    tipo_producao = forms.ChoiceField(
        label="Tipo de produção",
        choices=[],
    )
    numero_sei = forms.CharField(
        label="Número SEI",
        max_length=255,
        required=False,
    )
    observacao = forms.CharField(
        label="Observação",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [
            (str(tipo.pk), f"{tipo.prefixo} — {tipo.descricao}")
            for tipo in TipoProducao.objects.filter(ativo=True)
            .exclude(prefixo="Despacho")
            .order_by("prefixo")
        ]
        choices.append((DESPACHO_VALUE, "Despacho"))
        self.fields["tipo_producao"].choices = [("", "---------")] + choices

    def clean(self):
        cleaned_data = super().clean()
        tipo_valor = cleaned_data.get("tipo_producao")
        numero_sei = cleaned_data.get("numero_sei")

        if not tipo_valor:
            return cleaned_data

        if tipo_valor == DESPACHO_VALUE:
            cleaned_data["is_despacho"] = True
            cleaned_data["tipo_producao_obj"] = None
            if not numero_sei:
                self.add_error("numero_sei", "Obrigatório para despacho.")
        else:
            cleaned_data["is_despacho"] = False
            try:
                cleaned_data["tipo_producao_obj"] = TipoProducao.objects.get(
                    pk=int(tipo_valor),
                    ativo=True,
                )
            except (TipoProducao.DoesNotExist, TypeError, ValueError):
                self.add_error("tipo_producao", "Tipo de produção inválido.")

        return cleaned_data


class OSEncerramentoForm(forms.Form):
    motivo_encerramento = forms.CharField(
        label="Motivo do encerramento",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class ImovelForm(forms.Form):
    tipo_identificacao = forms.ChoiceField(
        label="Tipo de identificação",
        choices=[
            ("CADASTRAL", "Inscrição cadastral (SIAT)"),
            ("ISIC", "Código ISIC (sem inscrição)"),
        ],
        widget=forms.RadioSelect,
        initial="CADASTRAL",
    )
    inscricao_cadastral = forms.IntegerField(
        label="Inscrição cadastral",
        required=False,
    )
    num_bloco = forms.CharField(
        label="Número do bloco",
        max_length=12,
        required=False,
    )
    cod_logradouro = forms.IntegerField(
        label="Código do logradouro",
        required=False,
    )
    nom_logradouro = forms.CharField(
        label="Logradouro",
        max_length=255,
        required=False,
    )
    num_endereco = forms.CharField(
        label="Número",
        max_length=20,
        required=False,
    )
    num_unidade = forms.CharField(
        label="Unidade",
        max_length=20,
        required=False,
    )
    bairro = forms.CharField(
        label="Bairro",
        max_length=100,
        required=False,
    )
    des_finalidade = forms.CharField(
        label="Finalidade",
        max_length=255,
        required=False,
    )
    area_territorial = forms.DecimalField(
        label="Área territorial (m²)",
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    area_construida = forms.DecimalField(
        label="Área construída (m²)",
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    exercicio_referencia = forms.IntegerField(
        label="Exercício de referência",
        required=False,
        initial=timezone.localdate().year,
    )
    num_versao = forms.IntegerField(
        label="Versão",
        required=False,
        initial=0,
    )
    rh_nome = forms.CharField(
        label="Nome da RH",
        max_length=20,
        required=False,
    )
    rh_valor = forms.IntegerField(
        label="Valor da RH",
        required=False,
    )
    idf_regiao_homogenea = forms.IntegerField(
        label="ID região homogênea",
        required=False,
    )
    latitude = forms.DecimalField(
        label="Latitude",
        max_digits=12,
        decimal_places=8,
        required=False,
    )
    longitude = forms.DecimalField(
        label="Longitude",
        max_digits=12,
        decimal_places=8,
        required=False,
    )
    coord_x = forms.DecimalField(
        label="Coordenada X",
        max_digits=15,
        decimal_places=6,
        required=False,
    )
    coord_y = forms.DecimalField(
        label="Coordenada Y",
        max_digits=15,
        decimal_places=6,
        required=False,
    )
    origem_dados = forms.ChoiceField(
        label="Origem dos dados",
        choices=[
            ("SIAT", "SIAT"),
            ("MANUAL", "Manual"),
            ("SIAT_EDITADO", "SIAT editado"),
        ],
        initial="MANUAL",
    )
    observacao_interna = forms.CharField(
        label="Observação interna",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    CAMPOS_IMOVEL = (
        "num_bloco",
        "cod_logradouro",
        "nom_logradouro",
        "num_endereco",
        "num_unidade",
        "bairro",
        "des_finalidade",
        "area_territorial",
        "area_construida",
        "exercicio_referencia",
        "num_versao",
        "rh_nome",
        "rh_valor",
        "idf_regiao_homogenea",
        "latitude",
        "longitude",
        "coord_x",
        "coord_y",
        "origem_dados",
        "observacao_interna",
    )

    def __init__(self, *args, imovel=None, **kwargs):
        self.imovel = imovel
        super().__init__(*args, **kwargs)
        if imovel and not self.data:
            from core.models import ImovelVersao

            versao = (
                imovel.versoes.order_by("-exercicio", "-num_versao", "-pk").first()
            )
            self.fields["tipo_identificacao"].initial = imovel.tipo_identificacao
            self.fields["inscricao_cadastral"].initial = imovel.inscricao_cadastral
            for campo in self.CAMPOS_IMOVEL:
                if campo == "observacao_interna":
                    valor = imovel.observacao_interna
                elif campo == "exercicio_referencia":
                    valor = versao.exercicio if versao else None
                elif campo == "origem_dados":
                    valor = versao.origem_dados if versao else "MANUAL"
                elif campo == "num_versao":
                    valor = versao.num_versao if versao else 0
                elif versao and hasattr(ImovelVersao, campo):
                    valor = getattr(versao, campo)
                else:
                    valor = None
                self.fields[campo].initial = valor

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get("tipo_identificacao")
        inscricao = cleaned_data.get("inscricao_cadastral")

        if tipo == "CADASTRAL":
            if inscricao is None:
                self.add_error(
                    "inscricao_cadastral",
                    "Obrigatório para imóvel com inscrição cadastral.",
                )
            else:
                qs = Imovel.objects.filter(inscricao_cadastral=inscricao)
                if self.imovel:
                    qs = qs.exclude(pk=self.imovel.pk)
                if qs.exists():
                    self.add_error(
                        "inscricao_cadastral",
                        "Inscrição cadastral já cadastrada.",
                    )
        elif tipo == "ISIC":
            cleaned_data["inscricao_cadastral"] = None

        return cleaned_data


class ISICForm(forms.Form):
    num_bloco = forms.CharField(
        label="Nº Lote Fiscal",
        max_length=12,
        required=False,
    )
    nom_logradouro = forms.CharField(
        label="Logradouro",
        max_length=255,
        required=False,
    )
    num_endereco = forms.CharField(
        label="Número",
        max_length=20,
        required=False,
    )
    num_unidade = forms.CharField(
        label="Unidade",
        max_length=20,
        required=False,
    )
    bairro = forms.CharField(
        label="Bairro",
        max_length=100,
        required=False,
    )
    des_finalidade = forms.CharField(
        label="Finalidade/Uso",
        max_length=255,
        required=False,
    )
    area_territorial = forms.DecimalField(
        label="Área territorial (m²)",
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    area_construida = forms.DecimalField(
        label="Área construída (m²)",
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    latitude = forms.DecimalField(
        label="Latitude",
        max_digits=12,
        decimal_places=8,
        required=False,
    )
    longitude = forms.DecimalField(
        label="Longitude",
        max_digits=12,
        decimal_places=8,
        required=False,
    )
    coord_x = forms.DecimalField(
        label="Coordenada X",
        max_digits=15,
        decimal_places=6,
        required=False,
    )
    coord_y = forms.DecimalField(
        label="Coordenada Y",
        max_digits=15,
        decimal_places=6,
        required=False,
    )
    observacao_interna = forms.CharField(
        label="Observação interna",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    CAMPOS_ISIC = (
        "num_bloco",
        "nom_logradouro",
        "num_endereco",
        "num_unidade",
        "bairro",
        "des_finalidade",
        "area_territorial",
        "area_construida",
        "latitude",
        "longitude",
        "coord_x",
        "coord_y",
        "observacao_interna",
    )


class SiatUploadForm(forms.Form):
    arquivo = forms.FileField(
        label="Arquivo SIAT (.txt)",
        required=True,
    )


class RelatorioProducaoForm(forms.Form):
    servidor = forms.ModelChoiceField(
        label="Autor do trabalho",
        queryset=Servidor.objects.all().order_by("nome"),
        required=False,
        empty_label="Todos",
    )
    data_inicio = forms.DateField(
        label="Data inicial (homologação)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    data_fim = forms.DateField(
        label="Data final (homologação)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    tipo_producao = forms.ModelChoiceField(
        label="Tipo de produção",
        queryset=TipoProducao.objects.filter(ativo=True).order_by("prefixo"),
        required=False,
        empty_label="Todos",
    )
    unidade = forms.ModelChoiceField(
        label="Unidade",
        queryset=UnidadeInterna.objects.all().order_by("sigla"),
        required=False,
        empty_label="Todas",
    )
