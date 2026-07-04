from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
import json


class Command(BaseCommand):
    help = 'Exporta hashes de senha dos usuários para um arquivo JSON'

    def add_arguments(self, parser):
        parser.add_argument('--output', default='hashes_senha.json')

    def handle(self, *args, **options):
        output = options['output']
        dados = []
        for user in User.objects.all():
            dados.append({
                'username': user.username,
                'password': user.password,  # hash, não texto puro
                'is_active': user.is_active,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
            })
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
        self.stdout.write(
            self.style.SUCCESS(f'{len(dados)} hashes exportados para {output}')
        )
