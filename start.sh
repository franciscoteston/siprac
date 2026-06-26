#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput
gunicorn siprac.wsgi --log-file - --bind 0.0.0.0:$PORT
