#!/usr/bin/env bash
set -o errexit

source /opt/venv/bin/activate

python manage.py migrate --noinput
exec gunicorn siprac.wsgi --log-file - --bind 0.0.0.0:$PORT
