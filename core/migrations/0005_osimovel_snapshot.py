import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_alter_imovel_options_remove_imovel_area_referencia_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="osimovel",
            name="data_vinculo",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="osimovel",
            name="vinculado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="imoveis_vinculados",
                to="core.servidor",
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_num_bloco",
            field=models.CharField(blank=True, max_length=12, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_inscricao_cadastral",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_codigo_isic",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_cod_logradouro",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_nom_logradouro",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_num_endereco",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_num_unidade",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_bairro",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_des_finalidade",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_area_territorial",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_area_construida",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_exercicio_referencia",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_num_versao",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_rh_nome",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_rh_valor",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_idf_regiao_homogenea",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=8,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=8,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_coord_x",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=15,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_coord_y",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=15,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_origem_dados",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="snap_data_importacao",
            field=models.DateField(blank=True, null=True),
        ),
    ]
