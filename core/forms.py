from django import forms
from django.core.exceptions import ValidationError

from core.models import (
    CombinacaoValida,
    Finalidade,
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
