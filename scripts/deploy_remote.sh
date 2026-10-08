#!/usr/bin/env bash
# Executed on the server from /opt/lms-system; IMAGE_NAME is supplied by CI.
set -Eeuo pipefail
umask 077

: "${IMAGE_NAME:?CI must set IMAGE_NAME}"
[[ -s .env ]] || { echo 'Missing /opt/lms-system/.env' >&2; exit 1; }

# Keep the exact successfully published SHA tag in a separate, non-secret file.
# The production credentials remain exclusively in .env on the server.
printf 'IMAGE_NAME=%s\n' "$IMAGE_NAME" > .image.env
compose=(docker compose --env-file .env --env-file .image.env -f docker-compose.prod.yml)

"${compose[@]}" pull
"${compose[@]}" up -d --wait db redis
"${compose[@]}" run --rm backend python manage.py migrate --noinput
"${compose[@]}" run --rm backend python manage.py collectstatic --noinput
# Recreate Nginx after the backend so its upstream uses the current container IP.
"${compose[@]}" up -d --remove-orphans --wait backend celery celery_beat
"${compose[@]}" up -d --force-recreate --no-deps --wait nginx
"${compose[@]}" ps
