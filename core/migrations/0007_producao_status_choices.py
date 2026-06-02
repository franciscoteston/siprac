from django.db import migrations, models


def migrar_status_em_elaboracao_para_entrada(apps, schema_editor):
    Producao = apps.get_model("core", "Producao")
    Producao.objects.filter(status="EM_ELABORACAO").update(status="ENTRADA")


def reverter_status_entrada_para_em_elaboracao(apps, schema_editor):
    Producao = apps.get_model("core", "Producao")
    Producao.objects.filter(status="ENTRADA").update(status="EM_ELABORACAO")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_producaoimovel_snap_area_construida_and_more"),
    ]

    operations = [
        migrations.RunPython(
            migrar_status_em_elaboracao_para_entrada,
            reverter_status_entrada_para_em_elaboracao,
        ),
        migrations.AlterField(
            model_name="producao",
            name="status",
            field=models.CharField(
                choices=[
                    ("ENTRADA", "Entrada"),
                    ("DISTRIBUIDO", "Distribuído"),
                    ("EM_ELABORACAO", "Em elaboração"),
                    ("PARA_REVISAO", "Para revisão"),
                    ("PARA_AJUSTES", "Para ajustes"),
                    ("HOMOLOGADO", "Homologado"),
                    ("CANCELADO", "Cancelado"),
                ],
                default="ENTRADA",
                max_length=20,
            ),
        ),
    ]
