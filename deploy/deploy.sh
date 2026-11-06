#!/usr/bin/env bash
# Usage: deploy/deploy.sh <git-tag>     e.g.  deploy/deploy.sh v1.0-rc1
set -euo pipefail

TAG="${1:?usage: deploy.sh <git-tag>}"
APP=/srv/cjshop/app
VENV=/srv/cjshop/venv
cd "$APP"

echo "==> Fetching $TAG"
git fetch --tags --quiet
git checkout --quiet "$TAG"

echo "==> Backing up before changing anything"
"$APP/deploy/backup.sh"

echo "==> Installing dependencies"
"$VENV/bin/pip" install --quiet -r requirements.txt

echo "==> Checking the configuration"
"$VENV/bin/python" manage.py check --deploy --fail-level WARNING

echo "==> Migrating and collecting static files"
"$VENV/bin/python" manage.py migrate --noinput
"$VENV/bin/python" manage.py collectstatic --noinput --verbosity 0

echo "==> Restarting"
sudo systemctl restart cjshop
sleep 3
DOMAIN=$(grep -E '^ALLOWED_HOSTS=' .env | cut -d= -f2- | cut -d, -f1 | tr -d '\r')
curl -fsS --unix-socket /run/cjshop/gunicorn.sock \
     -H "Host: $DOMAIN" -H "X-Forwarded-Proto: https" http://localhost/healthz/ > /dev/null
echo "==> Deployed $TAG"