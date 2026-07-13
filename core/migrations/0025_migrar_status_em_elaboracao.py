from django.db import migrations


def migrar_status_em_elaboracao(apps, schema_editor):
    Producao = apps.get_model("core", "Producao")
    Producao.objects.filter(status="EM_ELABORACAO").update(status="DISTRIBUIDO")


def reverter_status_em_elaboracao(apps, schema_editor):
    # Reversão parcial: não dá para distinguir DISTRIBUIDO legado de migrado.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_encaminhamento_manter_aberta_na_unidade_and_more"),
    ]

    operations = [
        migrations.RunPython(
            migrar_status_em_elaboracao,
            reverter_status_em_elaboracao,
        ),
    ]
