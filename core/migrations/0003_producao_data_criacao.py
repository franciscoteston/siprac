import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_servidor_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="producao",
            name="data_criacao",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name="Data de criação",
            ),
            preserve_default=False,
        ),
    ]
