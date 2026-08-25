#!/bin/sh

set -eu

python manage.py collectstatic --noinput

python manage.py migrate --noinput

exec gunicorn finsport.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 4 \
  --threads 2 \
  --timeout 60
