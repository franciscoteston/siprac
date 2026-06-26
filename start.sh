#!/usr/bin/env bash
set -o errexit

# Localiza o python correto (venv do Nixpacks ou do sistema)
if [ -f "/opt/venv/bin/python" ]; then
    PYTHON="/opt/venv/bin/python"
else
    PYTHON="python3"
fi

echo "Usando Python: $PYTHON"
$PYTHON -m pip show gunicorn || $PYTHON -m pip install gunicorn

$PYTHON manage.py migrate --noinput
exec $PYTHON -m gunicorn siprac.wsgi --log-file - --bind 0.0.0.0:$PORT
