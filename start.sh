#!/usr/bin/env bash
set -o errexit

if [ -f "/opt/venv/bin/python" ]; then
    PYTHON="/opt/venv/bin/python"
else
    PYTHON="python3"
fi

echo "Usando Python: $PYTHON"
echo "PORT recebido: $PORT"

$PYTHON manage.py migrate --noinput
exec $PYTHON -m gunicorn siprac.wsgi --log-file - --bind 0.0.0.0:${PORT:-8080}
