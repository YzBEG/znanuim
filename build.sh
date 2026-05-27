#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

if [[ "$DJANGO_SEED_DEMO" == "True" || "$DJANGO_SEED_DEMO" == "true" || "$DJANGO_SEED_DEMO" == "1" ]]; then
  python manage.py seed_demo --password "${DJANGO_DEMO_PASSWORD:-Znanium2026!}"
fi
