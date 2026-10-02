#!/usr/bin/env bash
# Create a tester's account on the live server (while WhatsApp sign-up codes can't be sent yet):
#   sudo bash /opt/tradevoice/app/deploy/server/add_account.sh 08031234567 "Ada" "Ada Stores"
#   sudo bash /opt/tradevoice/app/deploy/server/add_account.sh 08031234567 --reset      (forgot the password)
# Prints a temporary password: give it to the person directly; they change it in Me → Password.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0 PHONE \"NAME\" \"BUSINESS\""; exit 1; }
[ $# -ge 1 ] || { sed -n '2,5p' "$0"; exit 1; }
APP=/opt/tradevoice/app
set -a; . /etc/tradevoice/paths.env; set +a
cd "$APP"
exec runuser -u tradevoice -- /opt/tradevoice/venv/bin/python scripts/add_account.py "$@"
