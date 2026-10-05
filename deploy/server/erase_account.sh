#!/usr/bin/env bash
# Erase an account now, when its owner asks for it sooner than the 90 days (their right under the NDPA):
#   sudo bash /opt/tradevoice/app/deploy/server/erase_account.sh 08031234567          shows what would be erased
#   sudo bash /opt/tradevoice/app/deploy/server/erase_account.sh 08031234567 --yes    erases it for good
# Only for a request from the owner of that number.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0 PHONE [--yes]"; exit 1; }
[ $# -ge 1 ] || { sed -n '2,5p' "$0"; exit 1; }
APP=/opt/tradevoice/app
set -a; . /etc/tradevoice/paths.env; set +a
cd "$APP"
exec runuser -u tradevoice -- /opt/tradevoice/venv/bin/python scripts/erase_account.py "$@"
