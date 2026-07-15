from django.db import migrations


def renomear_divisao(apps, schema_editor):
    UnidadeInterna = apps.get_model('core', 'UnidadeInterna')
    UnidadeInterna.objects.filter(
        sigla='DIVISAO'
    ).update(
        sigla='DEPARTAMENTO',
        nome='Departamento'
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0032_remover_tipo_acao'),
    ]

    operations = [
        migrations.RunPython(renomear_divisao, noop_reverse),
    ]
