#!/usr/bin/env bash
# The WhatsApp message templates (login codes, daily summary, paid notice, team alert):
#   sudo bash /opt/tradevoice/app/deploy/server/whatsapp_templates.sh --print    the exact text, to create by hand in WhatsApp Manager
#   sudo bash /opt/tradevoice/app/deploy/server/whatsapp_templates.sh --status   which ones Meta approved (--create: create them by API)
# Then put each approved name in .env with keys.sh (WHATSAPP_TPL_CODE, _SUMMARY, _PAID, _ALERT).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0 --print|--status|--create"; exit 1; }
[ $# -ge 1 ] || { sed -n '2,5p' "$0"; exit 1; }
APP=/opt/tradevoice/app
set -a; . /etc/tradevoice/paths.env; set +a
cd "$APP"
exec runuser -u tradevoice -- /opt/tradevoice/venv/bin/python scripts/whatsapp_templates.py "$@"
