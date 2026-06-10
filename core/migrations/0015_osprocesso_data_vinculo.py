import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_remove_processosei_situacao_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="osprocesso",
            name="data_vinculo",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name="Data de registro no SIPRAC",
            ),
            preserve_default=False,
        ),
    ]
