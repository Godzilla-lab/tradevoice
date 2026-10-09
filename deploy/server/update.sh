#!/usr/bin/env bash
# Put the latest code from GitHub live on the server, safely:
#   sudo bash /opt/tradevoice/app/deploy/server/update.sh            (another branch: sudo BRANCH=name bash …)
# Backs up first, installs, restarts, checks the app answers; if any step fails, goes back to the code that worked.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0"; exit 1; }
APP=/opt/tradevoice/app
VENV=/opt/tradevoice/venv
BRANCH=${BRANCH:-main}
cd "$APP"

up() {
  for _ in $(seq 1 60); do curl -sf http://127.0.0.1:8000/api/status >/dev/null && return 0; sleep 1; done
  return 1
}
go_live() {   # commit: check it out, install what it needs, restart, wait for it to answer
  # daemon-reload: if setup.sh rewrote the service file, systemd uses the new one (and stops warning about it)
  git checkout -q --detach "$1" && "$VENV/bin/pip" install -q -r requirements-server.txt && systemctl daemon-reload \
    && systemctl restart tradevoice && up
}

old=$(git rev-parse HEAD)
git fetch -q origin "$BRANCH"
new=$(git rev-parse "origin/$BRANCH")
[ "$old" != "$new" ] || { echo "Already up to date ($(git log -1 --format='%h %s' | cut -c1-80))."; exit 0; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "❌ Files on the server were edited by hand (git status). Not updating."; exit 1; }

systemctl start tradevoice-backup.service && echo "backup before the update ✅"
if go_live "$new"; then
  echo "✅ live: $(git log -1 --format='%h %s' | cut -c1-100)"
  if ! git diff --quiet "$old" "$new" -- deploy/server/setup.sh; then
    echo "ℹ️  The server setup changed too: run  sudo bash $APP/deploy/server/setup.sh"
  fi
else
  echo "❌ The new code didn't start. Going back to $(git rev-parse --short "$old")…"
  journalctl -u tradevoice -n 30 --no-pager || true
  if go_live "$old"; then echo "↩️  back on the old code, the app is up."; else echo "❌ still down: sudo journalctl -u tradevoice -n 50"; fi
  exit 1
fi
