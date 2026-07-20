from django.db import migrations


def corrigir_e_popular_tipos(apps, schema_editor):
    TipoProducao = apps.get_model("core", "TipoProducao")
    TipoProducaoUnidade = apps.get_model("core", "TipoProducaoUnidade")
    UnidadeInterna = apps.get_model("core", "UnidadeInterna")

    correcoes = {
        "PTF": ("Parecer Técnico Fundamentado", True, True),
        "PF": ("Parecer Fiscal", True, True),
        "PFF": ("Parecer Fiscal Fundamentado", True, True),
    }
    for prefixo, (descricao, seq, manual) in correcoes.items():
        TipoProducao.objects.filter(prefixo=prefixo).update(
            descricao=descricao,
            tem_numeracao_sequencial=seq,
            numero_manual=manual,
        )

    TipoProducao.objects.filter(prefixo="IT").update(
        descricao="Informação Técnica",
        subtipo="Geral (Exceto: Equiv; E. Preliminar)",
        tem_numeracao_sequencial=True,
        numero_manual=True,
    )

    novos_tipos = [
        ("IT", "Informação Técnica", "Estudo Preliminar", True, True),
        ("IT", "Informação Técnica", "Equivalência", True, True),
        ("ITJ", "Informação Técnica Judicial", None, True, True),
        ("PIV", "Parecer Indicativo de Valor", None, True, True),
        ("LB", "Laudo de Benfeitorias", None, True, True),
        ("TPU", "Permissão de Uso", None, True, True),
        ("Nomeação e Quesitos", "Nomeação e Quesitos", None, False, True),
        ("Modelo", "Modelo", None, False, True),
        ("Estudo Especial", "Estudo Especial", None, False, True),
        ("Despacho IN 001/2021", "Despacho IN 001/2021", None, False, True),
        ("E-mail SEI", "E-mail SEI", None, False, True),
        ("Despacho - notificado", "Despacho - notificado", None, False, True),
        ("Informação Fiscal", "Informação Fiscal", None, False, True),
        ("Atribuição de preço de m²", "Atribuição de preço de m²", None, False, True),
        ("Revisão de ofício", "Revisão de ofício", None, False, True),
    ]

    for prefixo, descricao, subtipo, tem_seq, manual in novos_tipos:
        lookup = {"prefixo": prefixo, "subtipo": subtipo}
        defaults = {
            "descricao": descricao,
            "tem_numeracao_sequencial": tem_seq,
            "numero_manual": manual,
            "ativo": True,
        }
        if not TipoProducao.objects.filter(**lookup).exists():
            TipoProducao.objects.create(**lookup, **defaults)

    # Garantir flags em tipos já existentes usados nos vínculos
    for prefixo in ("LA", "PT", "PTJ", "Despacho"):
        TipoProducao.objects.filter(prefixo=prefixo, subtipo__isnull=True).update(
            tem_numeracao_sequencial=True if prefixo != "Despacho" else False,
            numero_manual=True,
        )
    TipoProducao.objects.filter(prefixo="Despacho").update(
        tem_numeracao_sequencial=False,
        numero_manual=True,
    )

    try:
        eav = UnidadeInterna.objects.get(sigla="EAV")
        esjl = UnidadeInterna.objects.get(sigla="ESJL")
        epgv = UnidadeInterna.objects.get(sigla="EPGV")
    except UnidadeInterna.DoesNotExist:
        return

    prefixos_eav = {
        "LA",
        "IT",
        "ITJ",
        "PT",
        "PTF",
        "PIV",
        "Nomeação e Quesitos",
        "Despacho",
        "LB",
        "Modelo",
        "Estudo Especial",
    }
    prefixos_esjl = {
        "LA",
        "IT",
        "ITJ",
        "PT",
        "PTF",
        "PIV",
        "PTJ",
        "Nomeação e Quesitos",
        "Despacho",
        "LB",
        "Modelo",
        "Estudo Especial",
        "Despacho IN 001/2021",
        "TPU",
        "E-mail SEI",
        "Despacho - notificado",
    }
    prefixos_epgv = {
        "PF",
        "PFF",
        "Informação Fiscal",
        "Atribuição de preço de m²",
        "Revisão de ofício",
        "Despacho",
    }

    def vincular(unidade, prefixos):
        tipos = TipoProducao.objects.filter(prefixo__in=prefixos, ativo=True)
        for tipo in tipos:
            TipoProducaoUnidade.objects.get_or_create(
                tipo_producao=tipo,
                unidade_interna=unidade,
            )

    vincular(eav, prefixos_eav)
    vincular(esjl, prefixos_esjl)
    vincular(epgv, prefixos_epgv)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_tipoproducao_notificacao_campos"),
    ]

    operations = [
        migrations.RunPython(corrigir_e_popular_tipos, noop_reverse),
    ]
