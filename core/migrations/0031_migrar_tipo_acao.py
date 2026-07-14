from django.db import migrations


def migrar_tipo_acao(apps, schema_editor):
    Encaminhamento = apps.get_model('core', 'Encaminhamento')

    for enc in Encaminhamento.objects.all():
        # Só migra se etapa_interna ainda não foi definida
        if enc.etapa_interna:
            continue

        mapa = {
            'ENTRADA': 'ENTRADA',
            'DEVOLUCAO': 'DEVOLUCAO',
            'SOLICITACAO_AJUSTE': 'SOLICITACAO_AJUSTE',
            'HOMOLOGACAO': 'HOMOLOGACAO',
            'CONCLUSAO': 'CONCLUIDA',
            'AUTOMATICO': None,  # campo automatico=True já registra
            'EXTERNO': None,     # unidade_externa_destino já registra
        }

        novo_valor = mapa.get(enc.tipo_acao)
        if novo_valor:
            enc.etapa_interna = novo_valor
            enc.save(update_fields=['etapa_interna'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0030_popular_unidade_divisao'),
    ]

    operations = [
        migrations.RunPython(migrar_tipo_acao, noop_reverse),
    ]
