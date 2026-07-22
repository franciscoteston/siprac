from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from core.models import Producao


STATUS_LEGADOS = [
    Producao.STATUS_NAO_DISTRIBUIDO,
    Producao.STATUS_DISTRIBUIDO,
    Producao.STATUS_REVISAR,
    Producao.STATUS_REVISADO,
    Producao.STATUS_VER_AJUSTES,
    Producao.STATUS_ENTREGA_AJUSTES,
    Producao.STATUS_AJUSTES_OK,
    Producao.STATUS_HOMOLOGAR,
]


class Command(BaseCommand):
    help = (
        "Normaliza produções com status intermediário legado para ENVIADO, "
        "preenchendo data_enviado a partir de data_criacao."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Apenas lista o que seria alterado, sem gravar.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        queryset = Producao.objects.filter(status__in=STATUS_LEGADOS).order_by("pk")
        total = queryset.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nenhuma produção com status legado."))
            self._imprimir_contagem()
            return

        self.stdout.write(f"Produções a normalizar: {total}")
        atualizadas = 0
        hoje = timezone.localdate()

        for producao in queryset:
            if producao.data_criacao:
                data_enviado = timezone.localtime(producao.data_criacao).date()
            else:
                data_enviado = hoje

            self.stdout.write(
                f"  #{producao.pk} {producao.status} -> ENVIADO "
                f"(data_enviado={data_enviado})"
            )

            if not dry_run:
                producao.status = Producao.STATUS_ENVIADO
                producao.data_enviado = data_enviado
                producao.save(update_fields=["status", "data_enviado"])
                atualizadas += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run: nenhuma alteração gravada."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Atualizadas: {atualizadas} produção(ões).")
            )

        self._imprimir_contagem()

    def _imprimir_contagem(self):
        self.stdout.write("Contagem por status:")
        linhas = (
            Producao.objects.values("status")
            .annotate(total=Count("id"))
            .order_by("status")
        )
        for linha in linhas:
            self.stdout.write(f"  {linha['status']}: {linha['total']}")
        if not linhas:
            self.stdout.write("  (nenhuma produção)")
