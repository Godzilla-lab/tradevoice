#!/usr/bin/env bash
# The NAIC real-world validation page from the pilot's log (counts only, the team left out), saved in your home folder:
#   sudo bash /opt/tradevoice/app/deploy/server/validation_report.sh                         6 to 12 Oct
#   sudo bash /opt/tradevoice/app/deploy/server/validation_report.sh --start 2026-10-06 --end 2026-10-17
# Then on your Mac: scp -i KEY ubuntu@SERVER:validation.html . and open it; Print > Save as PDF.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0"; exit 1; }
APP=/opt/tradevoice/app
set -a; . /etc/tradevoice/paths.env; set +a
WORK=$(mktemp -d /var/tmp/tv-validation.XXXXXX)          # the app user writes here; you get a copy
trap 'rm -rf "$WORK"' EXIT
chown tradevoice "$WORK"
cd "$APP"
runuser -u tradevoice -- /opt/tradevoice/venv/bin/python scripts/validation_report.py --out "$WORK/validation.html" "$@"
HOME_DIR=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)
cp "$WORK/validation.html" "$HOME_DIR/validation.html" && chown "${SUDO_USER:-root}" "$HOME_DIR/validation.html"
echo "Saved: $HOME_DIR/validation.html"
