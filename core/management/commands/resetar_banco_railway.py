"""
Comando para resetar o banco do Railway preservando configuração.
Uso: python manage.py resetar_banco_railway

O que faz:
1. Apaga apenas dados operacionais (OS, produções, imóveis, etc.)
2. Recarrega dados de domínio (dump_dominio.json)
3. Recria usuários e vínculos (setup_railway)

O que preserva:
- Perfis de acesso
- Unidades internas
- Naturezas, Requerimentos, Finalidades
- Tipos de produção
- Usuários, Servidores e vínculos
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Reseta dados operacionais do banco preservando configuração'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirmar',
            action='store_true',
            help='Confirma a execução do reset (obrigatório)'
        )
        parser.add_argument(
            '--incluir-usuarios',
            action='store_true',
            help='Também recria usuários e vínculos via setup_railway'
        )

    def handle(self, *args, **options):
        if not options['confirmar']:
            self.stdout.write(self.style.ERROR(
                'ATENÇÃO: Este comando apaga dados operacionais do banco.\n'
                'Use --confirmar para executar.\n'
                'Exemplo: python manage.py resetar_banco_railway --confirmar'
            ))
            return

        self.stdout.write('Iniciando reset do banco...')

        from core.models import (
            OS, OsProcesso, OsImovel, MacroetapaLog, Encaminhamento,
            TarefaInterna, Producao, ProducaoImovel,
            ProducaoStatusLog, Imovel, ProcessoSei,
            LogAuditoria, PermissaoEspecial, Comentario,
            PreferenciaGerencial,
        )

        with transaction.atomic():
            # Ordem respeitando dependências (filho antes do pai)
            modelos = [
                ('LogAuditoria', LogAuditoria),
                ('Comentario', Comentario),
                ('ProducaoStatusLog', ProducaoStatusLog),
                ('ProducaoImovel', ProducaoImovel),
                ('Producao', Producao),
                ('TarefaInterna', TarefaInterna),
                ('Encaminhamento', Encaminhamento),
                ('MacroetapaLog', MacroetapaLog),
                ('OsImovel', OsImovel),
                ('OsProcesso', OsProcesso),
                ('OS', OS),
                ('ProcessoSei', ProcessoSei),
                ('Imovel', Imovel),
                ('PermissaoEspecial', PermissaoEspecial),
                ('PreferenciaGerencial', PreferenciaGerencial),
            ]

            for nome, modelo in modelos:
                count = modelo.objects.count()
                modelo.objects.all().delete()
                self.stdout.write(f'  Removido: {nome} ({count} registros)')

        self.stdout.write(self.style.SUCCESS(
            'Dados operacionais removidos com sucesso.'
        ))
        self.stdout.write(
            'Domínio preservado: Perfis, Unidades, Naturezas, '
            'Requerimentos, Finalidades, Tipos de produção.'
        )

        if options['incluir_usuarios']:
            self.stdout.write('\nRecriando usuários via setup_railway...')
            from django.core.management import call_command
            call_command('setup_railway')
