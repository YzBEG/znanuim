#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

if [[ "$DJANGO_SEED_INITIAL_DATA" == "True" || "$DJANGO_SEED_INITIAL_DATA" == "true" || "$DJANGO_SEED_INITIAL_DATA" == "1" ]]; then
  python manage.py seed_initial --password "${DJANGO_INITIAL_PASSWORD:-Znanium2026!}"
fi

if [[ "${DJANGO_PREPARE_DEFENSE_DEMO:-1}" == "True" || "${DJANGO_PREPARE_DEFENSE_DEMO:-1}" == "true" || "${DJANGO_PREPARE_DEFENSE_DEMO:-1}" == "1" ]]; then
  python manage.py prepare_defense_demo
fi
