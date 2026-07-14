from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
import json, os


class Command(BaseCommand):
    help = 'Configura usuarios no Railway: cria se nao existir e aplica hashes'

    def handle(self, *args, **options):
        from core.models import Servidor, ServidorUnidade, PerfilAcesso, UnidadeInterna
        import json, os

        # 1. Carregar e aplicar hashes de senha
        if not os.path.exists('hashes_senha.json'):
            self.stdout.write(self.style.ERROR('hashes_senha.json nao encontrado'))
            return

        with open('hashes_senha.json', 'r', encoding='utf-8') as f:
            dados_users = json.load(f)

        criados = 0
        atualizados = 0

        for item in dados_users:
            user, created = User.objects.get_or_create(
                username=item['username'],
                defaults={
                    'is_active': item.get('is_active', True),
                    'is_staff': item.get('is_staff', False),
                    'is_superuser': item.get('is_superuser', False),
                }
            )
            user.password = item['password']
            user.is_active = item.get('is_active', True)
            user.is_staff = item.get('is_staff', False)
            user.is_superuser = item.get('is_superuser', False)
            user.save()
            if created:
                criados += 1
            else:
                atualizados += 1

        self.stdout.write(self.style.SUCCESS(
            f'Users: {criados} criados, {atualizados} atualizados.'
        ))

        # 2. Garantir unidade DIVISAO antes dos vinculos
        divisao, divisao_created = UnidadeInterna.objects.get_or_create(
            sigla='DIVISAO',
            defaults={
                'nome': 'Divisão de Avaliação de Imóveis',
                'tipo': 'ADMINISTRATIVA',
            },
        )
        if not divisao_created and divisao.tipo != 'ADMINISTRATIVA':
            divisao.tipo = 'ADMINISTRATIVA'
            divisao.save(update_fields=['tipo'])
        if divisao_created:
            self.stdout.write(self.style.SUCCESS('Unidade DIVISAO criada (ADMINISTRATIVA).'))
        else:
            self.stdout.write('Unidade DIVISAO ja existente.')

        UnidadeInterna.objects.exclude(sigla='DIVISAO').update(tipo='OPERACIONAL')

        # 3. Carregar dados de servidores (lista plana: 1 entrada = 1 vinculo)
        if not os.path.exists('servidores_config.json'):
            self.stdout.write(self.style.WARNING('servidores_config.json nao encontrado — pulando vinculos'))
            return

        with open('servidores_config.json', 'r', encoding='utf-8') as f:
            dados_servidores = json.load(f)

        srv_criados = 0
        srv_vinculados = 0

        for item in dados_servidores:
            try:
                user = User.objects.get(username=item['login'])
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'User nao encontrado: {item["login"]}'))
                continue

            # Criar ou atualizar Servidor
            servidor, created = Servidor.objects.get_or_create(
                login=item['login'],
                defaults={'nome': item['nome'], 'user': user}
            )
            if servidor.user != user:
                servidor.user = user
            servidor.nome = item['nome']
            servidor.save()
            if created:
                srv_criados += 1

            # Criar ServidorUnidade se nao existir (suporta multiplos vinculos por login)
            try:
                unidade = UnidadeInterna.objects.get(sigla=item['unidade'])
                perfil = PerfilAcesso.objects.get(nome=item['perfil'])
                _, vu_created = ServidorUnidade.objects.get_or_create(
                    servidor=servidor,
                    unidade=unidade,
                    data_fim=None,
                    defaults={
                        'perfil': perfil,
                        'cargo': item.get('cargo', ''),
                        'data_inicio': item.get('data_inicio', '2026-01-01'),
                    }
                )
                if vu_created:
                    srv_vinculados += 1
                    self.stdout.write(f'Vinculado: {item["login"]} -> {item["unidade"]} ({item["perfil"]})')
            except UnidadeInterna.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'Unidade nao encontrada: {item["unidade"]}'))
            except PerfilAcesso.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'Perfil nao encontrado: {item["perfil"]}'))

        self.stdout.write(self.style.SUCCESS(
            f'Servidores: {srv_criados} criados, {srv_vinculados} vinculos criados.'
        ))
