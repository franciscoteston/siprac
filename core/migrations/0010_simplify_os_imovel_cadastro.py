# Generated manually for OsImovel cadastral simplification

import django.db.models.deletion
from django.db import migrations, models


CAMPOS_VERSAO_PARA_OS = (
    "num_bloco",
    "cod_logradouro",
    "nom_logradouro",
    "num_endereco",
    "num_unidade",
    "bairro",
    "des_finalidade",
    "area_territorial",
    "area_construida",
    "rh_nome",
    "rh_valor",
    "idf_regiao_homogenea",
    "latitude",
    "longitude",
    "coord_x",
    "coord_y",
    "origem_dados",
)


def _copiar_versao_para_os_imovel(os_imovel, versao):
    for campo in CAMPOS_VERSAO_PARA_OS:
        setattr(os_imovel, campo, getattr(versao, campo, None))
    os_imovel.exercicio_referencia = versao.exercicio
    os_imovel.save()


def migrar_versao_para_os_imovel(apps, schema_editor):
    OsImovel = apps.get_model("core", "OsImovel")
    ImovelVersao = apps.get_model("core", "ImovelVersao")

    for os_imovel in OsImovel.objects.all():
        versao = None
        if os_imovel.imovel_versao_id:
            versao = ImovelVersao.objects.filter(pk=os_imovel.imovel_versao_id).first()
        if versao is None:
            versao = (
                ImovelVersao.objects.filter(imovel_id=os_imovel.imovel_id)
                .order_by("-exercicio", "-num_versao", "-data_registro", "-pk")
                .first()
            )
        if versao:
            _copiar_versao_para_os_imovel(os_imovel, versao)


def migrar_producao_para_os_imovel(apps, schema_editor):
    OsImovel = apps.get_model("core", "OsImovel")
    ProducaoImovel = apps.get_model("core", "ProducaoImovel")

    for producao_imovel in ProducaoImovel.objects.select_related("producao").all():
        os_imovel = OsImovel.objects.filter(
            os_id=producao_imovel.producao.os_id,
            imovel_id=producao_imovel.imovel_id,
        ).first()
        if os_imovel is None:
            continue
        producao_imovel.os_imovel_id = os_imovel.pk
        producao_imovel.save(update_fields=["os_imovel_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_imovel_versao_refactor"),
    ]

    operations = [
        migrations.AddField(
            model_name="osimovel",
            name="area_construida",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="area_territorial",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=12, null=True
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="bairro",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="cod_logradouro",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="coord_x",
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=15, null=True
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="coord_y",
            field=models.DecimalField(
                blank=True, decimal_places=6, max_digits=15, null=True
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="des_finalidade",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="exercicio_referencia",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="idf_regiao_homogenea",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="latitude",
            field=models.DecimalField(
                blank=True, decimal_places=8, max_digits=12, null=True
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="longitude",
            field=models.DecimalField(
                blank=True, decimal_places=8, max_digits=12, null=True
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="nom_logradouro",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="num_bloco",
            field=models.CharField(blank=True, max_length=12, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="num_endereco",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="num_unidade",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="origem_dados",
            field=models.CharField(
                choices=[("SIAT", "SIAT"), ("MANUAL", "Manual")],
                default="SIAT",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="rh_nome",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="osimovel",
            name="rh_valor",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.RunPython(migrar_versao_para_os_imovel, migrations.RunPython.noop),
        migrations.AddField(
            model_name="producaoimovel",
            name="os_imovel",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="producao_imoveis",
                to="core.osimovel",
            ),
        ),
        migrations.RunPython(migrar_producao_para_os_imovel, migrations.RunPython.noop),
        migrations.RemoveField(model_name="producaoimovel", name="imovel"),
        migrations.RemoveField(model_name="producaoimovel", name="imovel_versao"),
        migrations.RemoveField(model_name="producaoimovel", name="papel_no_grupo"),
        migrations.AlterField(
            model_name="producaoimovel",
            name="os_imovel",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="producao_imoveis",
                to="core.osimovel",
            ),
        ),
        migrations.RemoveField(model_name="osimovel", name="imovel_versao"),
        migrations.DeleteModel(name="ImovelVersao"),
    ]
