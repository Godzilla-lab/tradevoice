#!/usr/bin/env bash
# How long each step of a voice turn takes on the live server (times only, from the event log):
#   sudo bash /opt/tradevoice/app/deploy/server/speed.sh            last 7 days
#   sudo bash /opt/tradevoice/app/deploy/server/speed.sh --days 1   last day
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0"; exit 1; }
APP=/opt/tradevoice/app
set -a; . /etc/tradevoice/paths.env; set +a
cd "$APP"
exec runuser -u tradevoice -- /opt/tradevoice/venv/bin/python scripts/speed.py "$@"
