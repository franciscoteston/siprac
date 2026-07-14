from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_migrar_dados_producao_status_unidade"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="producao",
            name="data_homologacao",
        ),
    ]
