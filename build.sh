#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Limpar staticfiles para forçar atualização completa
rm -rf staticfiles/

python manage.py collectstatic --noinput
