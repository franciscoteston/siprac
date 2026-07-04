from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
import os


class Command(BaseCommand):
    help = 'Redefine a senha de todos os usuários para SENHA_PADRAO'

    def handle(self, *args, **options):
        senha = os.environ.get('SENHA_PADRAO', 'Siprac2026!')
        usuarios = User.objects.all()
        count = 0
        for user in usuarios:
            user.set_password(senha)
            user.save()
            count += 1
            self.stdout.write(f'Senha redefinida: {user.username}')
        self.stdout.write(
            self.style.SUCCESS(f'Total: {count} usuários atualizados.')
        )
