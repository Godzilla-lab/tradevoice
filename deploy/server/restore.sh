#!/usr/bin/env bash
# Put the books + accounts back on the live server, from a backup file or a folder (e.g. the files from Modal):
#   sudo bash /opt/tradevoice/app/deploy/server/restore.sh /var/lib/tradevoice/backups/tradevoice-20261006-140000.tar.gz
#   sudo bash /opt/tradevoice/app/deploy/server/restore.sh /tmp/modal-data
# Stops the app for a few seconds. The files it replaces are kept in /var/lib/tradevoice/backups/before-restore-*.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0 FILE_OR_FOLDER"; exit 1; }
[ -e "${1:-}" ] || { echo "Usage: sudo bash $0 FILE_OR_FOLDER"; exit 1; }
APP=/opt/tradevoice/app
DATA=/var/lib/tradevoice
src=$(mktemp -d "$DATA/import-XXXXXX")
trap 'rm -rf "$src"' EXIT
cp -r "$1" "$src/"                               # a private copy the app's user can read
chown -R tradevoice:tradevoice "$src"
item="$src/$(basename "$1")"

systemctl stop tradevoice
set -a; . /etc/tradevoice/paths.env; set +a
if runuser -u tradevoice -- /opt/tradevoice/venv/bin/python "$APP/scripts/backup.py" --restore "$item"; then ok=1; else ok=0; fi
systemctl start tradevoice
for _ in $(seq 1 60); do curl -sf http://127.0.0.1:8000/api/status >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8000/api/status >/dev/null && echo "app up ✅" || echo "❌ app not up: sudo journalctl -u tradevoice -n 50"
[ "$ok" = 1 ] || exit 1
