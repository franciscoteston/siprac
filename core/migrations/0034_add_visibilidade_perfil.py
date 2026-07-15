from django.db import migrations, models


def popular_visibilidade(apps, schema_editor):
    PerfilAcesso = apps.get_model('core', 'PerfilAcesso')
    mapa = {
        'Administrador': 'TOTAL',
        'Diretor': 'TOTAL',
        'Aux. Téc. Direção': 'TOTAL',
        'Coordenador': 'UNIDADE',
        'Aux. Téc. Coord.': 'UNIDADE',
        'Técnico': 'UNIDADE',
        'Aux. Adm. Gestão': 'DEPARTAMENTO',
        'Aux. Adm. Pesquisa': 'UNIDADE',
    }
    for nome, visibilidade in mapa.items():
        PerfilAcesso.objects.filter(nome=nome).update(
            visibilidade=visibilidade
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0033_renomear_divisao_departamento'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfilacesso',
            name='visibilidade',
            field=models.CharField(
                choices=[
                    ('UNIDADE', 'Apenas sua unidade'),
                    ('DEPARTAMENTO', 'Todas as OSs (consulta e entrada)'),
                    ('TOTAL', 'Total (edição completa)'),
                ],
                default='UNIDADE',
                max_length=15,
                verbose_name='Visibilidade',
            ),
        ),
        migrations.RunPython(popular_visibilidade, noop_reverse),
    ]
