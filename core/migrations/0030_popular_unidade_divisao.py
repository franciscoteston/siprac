from django.db import migrations


def popular_dados(apps, schema_editor):
    UnidadeInterna = apps.get_model('core', 'UnidadeInterna')

    # Criar unidade DIVISÃO se não existir
    # (UnidadeInterna não possui campo 'ativa')
    divisao, created = UnidadeInterna.objects.get_or_create(
        sigla='DIVISAO',
        defaults={
            'nome': 'Divisão de Avaliação de Imóveis',
            'tipo': 'ADMINISTRATIVA',
        },
    )
    if not created and divisao.tipo != 'ADMINISTRATIVA':
        divisao.tipo = 'ADMINISTRATIVA'
        divisao.save(update_fields=['tipo'])
    if created:
        print('Unidade DIVISÃO criada.')

    # Garantir que demais unidades são OPERACIONAL
    UnidadeInterna.objects.exclude(
        sigla='DIVISAO'
    ).update(tipo='OPERACIONAL')

    # Migrar tipo_vinculo existentes
    OsProcesso = apps.get_model('core', 'OsProcesso')
    OsProcesso.objects.filter(
        tipo_vinculo__isnull=True
    ).update(tipo_vinculo='PRINCIPAL')
    OsProcesso.objects.filter(
        tipo_vinculo=''
    ).update(tipo_vinculo='PRINCIPAL')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0029_unidade_divisao_etapa_interna'),
    ]

    operations = [
        migrations.RunPython(popular_dados, noop_reverse),
    ]
