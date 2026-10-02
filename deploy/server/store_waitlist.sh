#!/usr/bin/env bash
# Who asked to be told when TradeVoice is in the App Store / Google Play (phone numbers: keep this to the team):
#   sudo bash /opt/tradevoice/app/deploy/server/store_waitlist.sh           everyone
#   sudo bash /opt/tradevoice/app/deploy/server/store_waitlist.sh android   only Google Play
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0"; exit 1; }
APP=/opt/tradevoice/app
set -a; . /etc/tradevoice/paths.env; set +a
cd "$APP"
exec runuser -u tradevoice -- /opt/tradevoice/venv/bin/python scripts/store_waitlist.py "$@"
