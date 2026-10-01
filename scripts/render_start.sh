#!/bin/sh
set -eu

python manage.py migrate --noinput

# Generated content is useful but must never make an otherwise healthy web
# process unavailable. The command itself isolates individual CSV failures;
# this guard also covers missing directories or configuration mistakes.
if ! python manage.py sync_generated_missions --create-problem-sets; then
  echo "WARNING: generated mission sync failed; starting the web server with the existing database content." >&2
fi

if [ -d generated/realtor ] && find generated/realtor -name '*.csv' -print -quit | grep -q .; then
  if ! python manage.py sync_generated_missions --subject-code realtor --create-problem-sets; then
    echo "WARNING: realtor mission sync failed; starting the web server with the existing database content." >&2
  fi
fi

exec gunicorn myproject.wsgi:application
