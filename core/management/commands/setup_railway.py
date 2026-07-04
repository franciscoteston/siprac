from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
import json, os


class Command(BaseCommand):
    help = 'Configura usuarios no Railway: cria se nao existir e aplica hashes'

    def handle(self, *args, **options):
        # Carregar hashes
        if not os.path.exists('hashes_senha.json'):
            self.stdout.write(self.style.ERROR('hashes_senha.json nao encontrado'))
            return

        with open('hashes_senha.json', 'r', encoding='utf-8') as f:
            dados = json.load(f)

        criados = 0
        atualizados = 0

        for item in dados:
            user, created = User.objects.get_or_create(
                username=item['username'],
                defaults={
                    'is_active': item.get('is_active', True),
                    'is_staff': item.get('is_staff', False),
                    'is_superuser': item.get('is_superuser', False),
                }
            )
            # Aplica o hash diretamente (sem set_password)
            user.password = item['password']
            user.is_active = item.get('is_active', True)
            user.is_staff = item.get('is_staff', False)
            user.is_superuser = item.get('is_superuser', False)
            user.save()

            if created:
                criados += 1
                self.stdout.write(f'Criado: {user.username}')
            else:
                atualizados += 1
                self.stdout.write(f'Atualizado: {user.username}')

        self.stdout.write(self.style.SUCCESS(
            f'Total: {criados} criados, {atualizados} atualizados.'
        ))
