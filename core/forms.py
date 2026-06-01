from django import forms
from django.core.exceptions import ValidationError

from core.models import CombinacaoValida, Finalidade, Natureza, TipoDemanda


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
