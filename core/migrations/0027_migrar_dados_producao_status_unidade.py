from django.db import migrations


def migrar_producao(apps, schema_editor):
    Producao = apps.get_model("core", "Producao")
    ServidorUnidade = apps.get_model("core", "ServidorUnidade")

    for prod in Producao.objects.select_related("servidor_responsavel").all():
        # 1. Popular unidade a partir do servidor_responsavel
        if prod.servidor_responsavel_id:
            vinculo = (
                ServidorUnidade.objects.filter(
                    servidor_id=prod.servidor_responsavel_id,
                    data_fim__isnull=True,
                )
                .select_related("unidade")
                .first()
            )
            if vinculo:
                prod.unidade = vinculo.unidade

        # 2. Migrar data_homologacao → data_enviado
        if hasattr(prod, "data_homologacao") and prod.data_homologacao:
            prod.data_enviado = prod.data_homologacao

        # 3. Migrar status antigos → novos
        mapa_status = {
            "ENTRADA": "NAO_DISTRIBUIDO",
            "DISTRIBUIDO": "DISTRIBUIDO",
            "EM_ELABORACAO": "DISTRIBUIDO",
            "PARA_REVISAO": "REVISAR",
            "PARA_AJUSTES": "VER_AJUSTES",
            "HOMOLOGADO": "ENVIADO",
        }
        novo_status = mapa_status.get(prod.status)
        if novo_status:
            prod.status = novo_status

        prod.save()


def reverter_producao(apps, schema_editor):
    Producao = apps.get_model("core", "Producao")
    mapa_reverso = {
        "NAO_DISTRIBUIDO": "ENTRADA",
        "REVISAR": "PARA_REVISAO",
        "VER_AJUSTES": "PARA_AJUSTES",
        "ENVIADO": "HOMOLOGADO",
    }
    for prod in Producao.objects.all():
        if prod.data_enviado and hasattr(prod, "data_homologacao"):
            prod.data_homologacao = prod.data_enviado
        antigo = mapa_reverso.get(prod.status)
        if antigo:
            prod.status = antigo
        prod.save()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_producao_unidade_datas_status_schema"),
    ]

    operations = [
        migrations.RunPython(migrar_producao, reverter_producao),
    ]
