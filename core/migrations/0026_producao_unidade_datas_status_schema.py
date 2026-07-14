import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_migrar_status_em_elaboracao"),
    ]

    operations = [
        migrations.AddField(
            model_name="producao",
            name="unidade",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="producoes",
                to="core.unidadeinterna",
                verbose_name="Unidade responsável",
            ),
        ),
        migrations.AddField(
            model_name="producao",
            name="data_ajustes_ok",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Data de ajustes OK",
            ),
        ),
        migrations.AddField(
            model_name="producao",
            name="data_homologar",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Data apto à homologação",
            ),
        ),
        migrations.AddField(
            model_name="producao",
            name="data_enviado",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Data de envio ao SEI",
            ),
        ),
        migrations.AlterField(
            model_name="producao",
            name="status",
            field=models.CharField(
                choices=[
                    ("NAO_DISTRIBUIDO", "Não distribuído"),
                    ("DISTRIBUIDO", "Distribuído"),
                    ("REVISAR", "Revisar"),
                    ("REVISADO", "Revisado"),
                    ("VER_AJUSTES", "Ver ajustes"),
                    ("ENTREGA_AJUSTES", "Entrega de ajustes"),
                    ("AJUSTES_OK", "Ajustes OK"),
                    ("HOMOLOGAR", "Homologar"),
                    ("ENVIADO", "Enviado"),
                    ("CANCELADO", "Cancelado"),
                ],
                default="NAO_DISTRIBUIDO",
                max_length=20,
            ),
        ),
    ]
