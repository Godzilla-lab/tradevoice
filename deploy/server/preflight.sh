#!/usr/bin/env bash
# Is the live server ready for traders? PASS / WARN / FAIL per thing the pilot needs (never prints a key):
#   sudo bash /opt/tradevoice/app/deploy/server/preflight.sh
#   sudo bash /opt/tradevoice/app/deploy/server/preflight.sh --only "Backups,Disk space"
# Run it the evening before and each morning of the pilot. Safe to paste the output to anyone helping.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0"; exit 1; }
APP=/opt/tradevoice/app
set -a; . /etc/tradevoice/paths.env; set +a
cd "$APP"
exec runuser -u tradevoice -- /opt/tradevoice/venv/bin/python scripts/preflight.py "$@"
