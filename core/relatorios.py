from datetime import date

import openpyxl
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core.models import OsProcesso, Producao


def relatorio_producao_por_servidor(filtros):
    """
    Gera dados do relatório de produção por servidor.
    filtros: dict com servidor_id, data_inicio, data_fim,
             tipo_producao_id, unidade_id (todos opcionais)
    Retorna queryset de Producao com select_related.
    """
    qs = (
        Producao.objects.filter(status=Producao.STATUS_HOMOLOGADO)
        .select_related(
            "tipo_producao",
            "os",
            "os__natureza",
            "autor_trabalho",
            "servidor_responsavel",
            "homologado_por",
        )
        .order_by("autor_trabalho__nome", "data_homologacao")
    )

    if filtros.get("servidor_id"):
        qs = qs.filter(autor_trabalho__id=filtros["servidor_id"])
    if filtros.get("data_inicio"):
        qs = qs.filter(data_homologacao__gte=filtros["data_inicio"])
    if filtros.get("data_fim"):
        qs = qs.filter(data_homologacao__lte=filtros["data_fim"])
    if filtros.get("tipo_producao_id"):
        qs = qs.filter(tipo_producao__id=filtros["tipo_producao_id"])
    if filtros.get("unidade_id"):
        hoje = timezone.localdate()
        qs = qs.filter(
            autor_trabalho__vinculos_unidade__unidade_id=filtros["unidade_id"],
        ).filter(
            Q(autor_trabalho__vinculos_unidade__data_fim__isnull=True)
            | Q(autor_trabalho__vinculos_unidade__data_fim__gte=hoje),
        ).distinct()

    return qs


def linhas_relatorio_producao(queryset):
    """Serializa produções para exibição na prévia HTML."""
    producoes = list(queryset)
    processos_por_os = _mapa_processos_principais(producoes)
    linhas = []
    for producao in producoes:
        processo_principal = processos_por_os.get(producao.os_id)
        linhas.append(
            {
                "autor": (
                    producao.autor_trabalho.nome if producao.autor_trabalho else "—"
                ),
                "tipo": (
                    producao.tipo_producao.prefixo
                    if producao.tipo_producao
                    else "Despacho"
                ),
                "numero_producao": producao.numero_producao or "—",
                "numero_os": producao.os.numero_os,
                "natureza": (
                    producao.os.natureza.descricao if producao.os.natureza else "—"
                ),
                "processo_sei": (
                    processo_principal.processo_sei.numero_processo
                    if processo_principal and processo_principal.processo_sei
                    else "—"
                ),
                "data_homologacao": producao.data_homologacao,
                "homologado_por": (
                    producao.homologado_por.nome if producao.homologado_por else "—"
                ),
                "unidade": _sigla_unidade_autor(producao.autor_trabalho),
            },
        )
    return linhas


def _mapa_processos_principais(producoes):
    os_ids = {producao.os_id for producao in producoes}
    if not os_ids:
        return {}
    return {
        vinculo.os_id: vinculo
        for vinculo in OsProcesso.objects.filter(
            os_id__in=os_ids,
            tipo_vinculo="PRINCIPAL",
        ).select_related("processo_sei")
    }


def _sigla_unidade_autor(servidor):
    if servidor is None:
        return "—"
    hoje = timezone.localdate()
    vinculo = (
        servidor.vinculos_unidade.filter(
            Q(data_fim__isnull=True) | Q(data_fim__gte=hoje),
        )
        .select_related("unidade")
        .first()
    )
    return vinculo.unidade.sigla if vinculo else "—"


def exportar_producao_excel(queryset):
    """
    Gera arquivo Excel do relatório de produção.
    Retorna HttpResponse com o arquivo.
    """
    producoes = list(queryset)
    processos_por_os = _mapa_processos_principais(producoes)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Produção por Servidor"

    cabecalho_fill = PatternFill(
        start_color="1A3A5C",
        end_color="1A3A5C",
        fill_type="solid",
    )
    cabecalho_font = Font(color="FFFFFF", bold=True, size=11)

    colunas = [
        ("Autor do trabalho", 25),
        ("Tipo", 10),
        ("Número produção", 18),
        ("OS vinculada", 18),
        ("Natureza", 20),
        ("Processo SEI", 25),
        ("Data homologação", 18),
        ("Homologado por", 25),
        ("Unidade", 10),
    ]

    for col, (titulo, largura) in enumerate(colunas, 1):
        cell = ws.cell(row=1, column=col, value=titulo)
        cell.font = cabecalho_font
        cell.fill = cabecalho_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[get_column_letter(col)].width = largura

    for row, producao in enumerate(producoes, 2):
        processo_principal = processos_por_os.get(producao.os_id)

        ws.cell(
            row=row,
            column=1,
            value=producao.autor_trabalho.nome if producao.autor_trabalho else "—",
        )
        ws.cell(
            row=row,
            column=2,
            value=(
                producao.tipo_producao.prefixo
                if producao.tipo_producao
                else "Despacho"
            ),
        )
        ws.cell(row=row, column=3, value=producao.numero_producao or "—")
        ws.cell(row=row, column=4, value=producao.os.numero_os)
        ws.cell(
            row=row,
            column=5,
            value=producao.os.natureza.descricao if producao.os.natureza else "—",
        )
        ws.cell(
            row=row,
            column=6,
            value=(
                processo_principal.processo_sei.numero_processo
                if processo_principal and processo_principal.processo_sei
                else "—"
            ),
        )
        ws.cell(
            row=row,
            column=7,
            value=(
                producao.data_homologacao.strftime("%d/%m/%Y")
                if producao.data_homologacao
                else "—"
            ),
        )
        ws.cell(
            row=row,
            column=8,
            value=producao.homologado_por.nome if producao.homologado_por else "—",
        )
        ws.cell(
            row=row,
            column=9,
            value=_sigla_unidade_autor(producao.autor_trabalho),
        )

        if row % 2 == 0:
            fill = PatternFill(
                start_color="EEF2F7",
                end_color="EEF2F7",
                fill_type="solid",
            )
            for col in range(1, len(colunas) + 1):
                ws.cell(row=row, column=col).fill = fill

    total_row = len(producoes) + 2
    ws.cell(row=total_row, column=1, value=f"Total: {len(producoes)} produções")
    ws.cell(row=total_row, column=1).font = Font(bold=True)

    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        f'attachment; filename="producao_por_servidor_{date.today():%Y%m%d}.xlsx"'
    )
    wb.save(response)
    return response
