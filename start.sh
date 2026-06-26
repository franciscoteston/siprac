#!/usr/bin/env bash
set -o errexit

/opt/venv/bin/python manage.py migrate --noinput
exec /opt/venv/bin/gunicorn siprac.wsgi --log-file - --bind 0.0.0.0:$PORT
