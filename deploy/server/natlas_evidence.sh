#!/usr/bin/env bash
# Live evidence of the N-ATLaS integration, for the NAIC form ("Evidence artefacts"). Paste on the server:
#   sudo bash -c 'cd /opt/tradevoice/app && git fetch -q origin claude/tradevoice-handoff-b7942v && git show FETCH_HEAD:deploy/server/natlas_evidence.sh | bash'
# It takes the evidence script from that branch without checking anything out: the app keeps running the frozen
# code, nothing restarts. It calls N-ATLaS like the app does (about 2 to 5 minutes; longer if Modal is asleep) and
# saves the result as natlas_evidence.txt in your home folder. No keys, no names, no phone numbers in it.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo (see the top of this file)."; exit 1; }
APP=${TV_APP:-/opt/tradevoice/app}
cd "$APP"
set -a; . /etc/tradevoice/paths.env; set +a
WORK=$(mktemp -d /var/tmp/tv-evidence.XXXXXX)
trap 'rm -rf "$WORK"' EXIT
git show FETCH_HEAD:scripts/natlas_evidence.py > "$WORK/natlas_evidence.py"
chown -R tradevoice "$WORK"
COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
echo "Asking N-ATLaS on the live servers (a few minutes; Modal may need to wake up first)..."
runuser -u tradevoice -- env TV_APP="$APP" TV_COMMIT="$COMMIT" /opt/tradevoice/venv/bin/python \
  "$WORK/natlas_evidence.py" --out "$WORK/natlas_evidence.txt" "$@"
HOME_DIR=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)
cp "$WORK/natlas_evidence.txt" "$HOME_DIR/natlas_evidence.txt"
chown "${SUDO_USER:-root}" "$HOME_DIR/natlas_evidence.txt" 2>/dev/null || true
echo
echo "Saved: $HOME_DIR/natlas_evidence.txt. Copy everything above (from 'TradeVoice: live evidence') and paste it to Claude."
