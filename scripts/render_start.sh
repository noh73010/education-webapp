#!/bin/sh
set -eu

python manage.py migrate --noinput

# Validation and content writes are atomic. An invalid upload fails this new
# deploy while Render keeps serving the last healthy release.
python manage.py sync_content_catalog
python manage.py sync_guided_concepts

exec gunicorn myproject.wsgi:application
