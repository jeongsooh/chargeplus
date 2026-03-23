#!/bin/bash
set -e
python manage.py makemigrations --noinput
python manage.py migrate --noinput
python manage.py seed_variables
python manage.py compilemessages --ignore=".venv" 2>/dev/null || true
exec "$@"
