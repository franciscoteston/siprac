from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
import json, os


class Command(BaseCommand):
    help = 'Importa hashes de senha dos usuários de um arquivo JSON'

    def add_arguments(self, parser):
        parser.add_argument('--input', default='hashes_senha.json')

    def handle(self, *args, **options):
        input_file = options['input']
        if not os.path.exists(input_file):
            self.stdout.write(self.style.WARNING(f'Arquivo {input_file} não encontrado.'))
            return
        with open(input_file, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        count = 0
        for item in dados:
            try:
                user = User.objects.get(username=item['username'])
                user.password = item['password']
                user.is_active = item.get('is_active', True)
                user.is_staff = item.get('is_staff', False)
                user.is_superuser = item.get('is_superuser', False)
                user.save()
                count += 1
                self.stdout.write(f'OK: {user.username}')
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'Usuario nao encontrado: {item["username"]}')
                )
        self.stdout.write(
            self.style.SUCCESS(f'Total: {count} hashes importados.')
        )
