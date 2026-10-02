#!/bin/bash
# TradeVoice on this Mac, public through a Cloudflare Tunnel, until the Oracle server is ready. Guide: docs/HOSTING_MAC.md
#
#   bash deploy/mac/tradevoice.sh install                      once: everything, with a quick link (changes on restart)
#   bash deploy/mac/tradevoice.sh install app.example.com.ng   with a domain on Cloudflare: a fixed link
#   bash deploy/mac/tradevoice.sh status | link | logs | restart | update | backup | restore FILE | stop | start | uninstall
#
# After install it runs by itself: starts when you log in, restarts if it crashes, keeps the Mac awake, backs up hourly.
# Books + accounts + backups: ~/tradevoice-data (only you can open it). Keys: .env in this folder (only you).
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
DATA="$HOME/tradevoice-data"
VENV="$REPO/.venv-server"
AGENTS="$HOME/Library/LaunchAgents"
PORT=8000
LABELS="app.tradevoice.web app.tradevoice.tunnel app.tradevoice.backup app.tradevoice.awake"
HOSTFILE="$DATA/tunnel-hostname"
GUI="gui/$(id -u)"
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { echo "❌ $*"; exit 1; }

[ "$(uname)" = Darwin ] || [ -n "${TV_MAC_TEST:-}" ] || die "This script is for a Mac. On a server use deploy/server/setup.sh."
BREW=$(command -v brew >/dev/null 2>&1 && brew --prefix || echo /opt/homebrew)
CF="$BREW/bin/cloudflared"   # by full path: Homebrew may not be on the PATH of a new Terminal or of launchd

app_env() {   # the settings every TradeVoice process on this Mac gets, one per line (keys come from .env)
  printf '%s\n' "ACCOUNTS_DB=$DATA/accounts.db" "BOOKS_DIR=$DATA/books" "DB_PATH=$DATA/tradevoice.db" \
    "BACKUP_DIR=$DATA/backups" "PORT=$PORT" "TRADEVOICE_ADMIN=0" "TV_PUBLIC=1" "PYTHONUNBUFFERED=1" \
    "PYTHONDONTWRITEBYTECODE=1" "PATH=$BREW/bin:/usr/bin:/bin:/usr/sbin:/sbin"
}
py() { local e=(); while IFS= read -r l; do e+=("$l"); done < <(app_env); env "${e[@]}" "$VENV/bin/python" "$@"; }
local_up() { curl -sf "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1; }
wait_local() { for _ in $(seq 1 60); do local_up && return 0; sleep 1; done; return 1; }
hostname_() { [ -s "$HOSTFILE" ] && cat "$HOSTFILE" || true; }
link() {      # the public link: the fixed one, or the newest quick link in the tunnel log
  local h; h=$(hostname_)
  if [ -n "$h" ]; then echo "https://$h"; else
    grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$DATA/logs/tunnel.log" 2>/dev/null | tail -1 || true
  fi
}
start_job() {   # (re)load one job; right after a bootout macOS can need a moment
  launchctl bootout "$GUI/$1" 2>/dev/null || true
  for _ in 1 2 3 4 5; do launchctl bootstrap "$GUI" "$AGENTS/$1.plist" 2>/dev/null && return 0; sleep 1; done
  launchctl bootstrap "$GUI" "$AGENTS/$1.plist"
}
load() { for l in $LABELS; do start_job "$l"; done; }
unload() { for l in $LABELS; do launchctl bootout "$GUI/$l" 2>/dev/null || true; done; }

install() {
  local host="${1:-$(hostname_)}"
  case "$REPO" in
    "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*|*"/Library/Mobile Documents"*|*"/CloudStorage/"*)
      die "macOS doesn't let background apps open $REPO. Move the folder to your home folder (~/tradevoice) and run this again." ;;
  esac
  command -v brew >/dev/null 2>&1 || die "Homebrew is needed first. Install it from https://brew.sh (one command), then run this again."

  say "Installing Python, ffmpeg and cloudflared (Homebrew)"
  for f in python@3.12 ffmpeg cloudflared; do brew list --formula "$f" >/dev/null 2>&1 || brew install "$f"; done
  [ -x "$VENV/bin/python" ] || "$BREW/bin/python3.12" -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$REPO/requirements-server.txt"

  mkdir -p "$DATA/books" "$DATA/backups" "$DATA/logs" "$AGENTS"
  chmod 700 "$DATA" "$DATA/books" "$DATA/backups" "$DATA/logs"
  [ -f "$REPO/.env" ] || cp "$REPO/.env.example" "$REPO/.env"
  chmod 600 "$REPO/.env"

  if [ -n "$host" ]; then
    host=$(printf '%s' "$host" | sed -E 's#^https?://##; s#/.*$##' | tr 'A-Z' 'a-z')
    case "$host" in *.*) ;; *) die "That doesn't look like a web address: $host" ;; esac
    say "Fixed link: https://$host (Cloudflare Tunnel)"
    [ -f "$HOME/.cloudflared/cert.pem" ] || { echo "A browser opens: log in to Cloudflare and pick your domain."; "$CF" tunnel login; }
    "$CF" tunnel list -o json -n tradevoice 2>/dev/null | grep -q '"id"' || "$CF" tunnel create tradevoice
    local id
    id=$("$CF" tunnel list -o json -n tradevoice | "$VENV/bin/python" -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
    "$CF" tunnel route dns --overwrite-dns tradevoice "$host"
    cat > "$DATA/cloudflared.yml" <<EOF
tunnel: $id
credentials-file: $HOME/.cloudflared/$id.json
ingress:
  - hostname: $host
    service: http://127.0.0.1:$PORT
  - service: http_status:404
EOF
    echo "$host" > "$HOSTFILE"
  else
    rm -f "$HOSTFILE"
  fi
  "$VENV/bin/python" - "$REPO/.env" "${host:+https://$host}" <<'EOF'
import re, sys
path, url = sys.argv[1], sys.argv[2]
s = open(path, encoding="utf-8").read()
s = re.sub(r"(?m)^\s*AUTH_DEMO\s*=", "# AUTH_DEMO (never on a public link) =", s)   # anyone could open any book
s = re.sub(r"(?m)^NVIDIA_API_KEY=nvapi-your-key-here$", "# NVIDIA_API_KEY=", s)        # the example's placeholder
line = f"PUBLIC_URL={url}" if url else "# PUBLIC_URL=   (quick link: it changes, so the app uses the address it is opened with)"
s, n = re.subn(r"(?m)^\s*#?\s*PUBLIC_URL=.*$", line, s)
s = s if n else s.rstrip("\n") + "\n" + line + "\n"
open(path, "w", encoding="utf-8").write(s)
EOF

  say "Starting (and setting it to start by itself when you log in)"
  : > "$DATA/logs/tunnel.log"
  "$VENV/bin/python" - "$AGENTS" "$REPO" "$VENV" "$DATA" "$BREW" "$PORT" "$host" "$(app_env)" <<'EOF'
import plistlib, sys
agents, repo, venv, data, brew, port, host, env = sys.argv[1:9]
env = dict(kv.split("=", 1) for kv in env.splitlines() if kv)
logs = f"{data}/logs"
tunnel = ([f"{brew}/bin/cloudflared", "tunnel", "--no-autoupdate", "--config", f"{data}/cloudflared.yml", "run"] if host
          else [f"{brew}/bin/cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"])
jobs = {
    # the app: one process (every book is a SQLite file: one writer), only reachable through the tunnel
    "web": dict(ProgramArguments=[f"{venv}/bin/uvicorn", "web:app", "--app-dir", "src", "--host", "127.0.0.1",
                                  "--port", port, "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"],
                KeepAlive=True, log="app"),
    "tunnel": dict(ProgramArguments=tunnel, KeepAlive=True, log="tunnel"),
    # every hour: backup (+ the copy off the Mac), and keep the logs small
    "backup": dict(ProgramArguments=["/bin/bash", f"{repo}/deploy/mac/tradevoice.sh", "_hourly"], StartInterval=3600,
                   log="backup"),
    # no idle sleep while TradeVoice is installed (closing the lid still sleeps a MacBook)
    "awake": dict(ProgramArguments=["/usr/bin/caffeinate", "-i", "-s"], KeepAlive=True, log="awake"),
}
for name, j in jobs.items():
    log = j.pop("log")
    p = dict(Label=f"app.tradevoice.{name}", WorkingDirectory=repo, EnvironmentVariables=env, RunAtLoad=True,
             ThrottleInterval=5, Umask=0o077, ProcessType="Background",
             StandardOutPath=f"{logs}/{log}.log", StandardErrorPath=f"{logs}/{log}.log", **j)
    with open(f"{agents}/app.tradevoice.{name}.plist", "wb") as f:
        plistlib.dump(p, f)
EOF
  load

  echo -n "⏳ app "
  wait_local && echo "✅" || die "the app didn't start: bash deploy/mac/tradevoice.sh logs"
  echo -n "⏳ public link "
  local url=""
  for _ in $(seq 1 45); do
    url=$(link); [ -n "$url" ] && curl -sf "$url/api/status" >/dev/null 2>&1 && break; url=""; sleep 2
  done
  [ -n "$url" ] && echo "✅" || echo "❌  not yet: bash deploy/mac/tradevoice.sh status (in a minute)"
  echo
  echo "🟢 TradeVoice: ${url:-$(link)}/app"
  if [ -z "$host" ]; then
    echo "   ⚠️  Quick link: it CHANGES whenever the Mac or the tunnel restarts. See the newest: bash deploy/mac/tradevoice.sh link"
    echo "      For a fixed link: get a domain, add it to Cloudflare, run: bash deploy/mac/tradevoice.sh install app.YOURDOMAIN"
  fi
  echo "   Webhooks: <link>/whatsapp/webhook (Meta) and <link>/paystack/webhook (Paystack)"
  echo "   Keys: open .env in this folder, fill them in (never in the chat), then: bash deploy/mac/tradevoice.sh restart"
  echo "   Keep the Mac plugged in, the lid open, and you logged in. docs/HOSTING_MAC.md has the rest."
}

hourly() {    # run by launchd every hour
  for f in "$DATA"/logs/*.log; do   # keep each log under ~20 MB (same file, so launchd keeps writing to it)
    if [ -f "$f" ] && [ "$(wc -c < "$f")" -gt 20000000 ]; then tail -n 20000 "$f" > "$f.tmp"; cat "$f.tmp" > "$f"; rm -f "$f.tmp"; fi
  done
  echo "--- $(date '+%Y-%m-%d %H:%M')"
  cd "$REPO" && py scripts/backup.py
}

status() {
  for l in $LABELS; do
    s=$(launchctl print "$GUI/$l" 2>/dev/null | awk -F'= ' '/^\tstate =/ {print $2; exit}' || true)
    printf '%-24s %s\n' "$l" "${s:-not installed}"
  done
  local_up && echo "app answers on this Mac ✅" || echo "app not answering ❌  (bash deploy/mac/tradevoice.sh logs)"
  local u; u=$(link)
  if [ -n "$u" ] && curl -sf "$u/api/status" >/dev/null 2>&1; then echo "public link ✅ $u"; else echo "public link ❌ ${u:-none yet}"; fi
  local b="" f; for f in "$DATA"/backups/tradevoice-*.tar.gz; do [ -e "$f" ] && b=$(basename "$f"); done   # names sort by time
  echo "last backup: ${b:-none yet}   (tail $DATA/logs/backup.log)"
}

update() {
  cd "$REPO"
  [ "$(git rev-parse --abbrev-ref HEAD)" = main ] || die "This folder isn't on the main branch: git checkout main"
  [ -z "$(git status --porcelain --untracked-files=no)" ] || die "Files here were edited by hand (git status). Not updating."
  local old new
  old=$(git rev-parse HEAD); git fetch -q origin main; new=$(git rev-parse origin/main)
  [ "$old" != "$new" ] || { echo "Already up to date."; return 0; }
  py scripts/backup.py >/dev/null && echo "backup before the update ✅"
  if git merge -q --ff-only origin/main && "$VENV/bin/pip" install -q -r requirements-server.txt \
     && launchctl kickstart -k "$GUI/app.tradevoice.web" && sleep 2 && wait_local; then
    echo "✅ live: $(git log -1 --format='%h %s' | cut -c1-100)"
  else
    echo "❌ The new code didn't start. Going back to $(git rev-parse --short "$old")…"
    tail -n 30 "$DATA/logs/app.log" || true
    git reset -q --hard "$old"; "$VENV/bin/pip" install -q -r requirements-server.txt
    launchctl kickstart -k "$GUI/app.tradevoice.web"; sleep 2
    wait_local && echo "↩️  back on the old code, the app is up." || echo "❌ still down: bash deploy/mac/tradevoice.sh logs"
    return 1
  fi
}

restore() {
  [ -e "${1:-}" ] || die "Usage: bash deploy/mac/tradevoice.sh restore FILE_OR_FOLDER"
  launchctl bootout "$GUI/app.tradevoice.web" 2>/dev/null || true
  sleep 1
  local ok=0
  (cd "$REPO" && py scripts/backup.py --restore "$1") && ok=1
  start_job app.tradevoice.web
  wait_local && echo "app up ✅" || echo "❌ app not up: bash deploy/mac/tradevoice.sh logs"
  [ "$ok" = 1 ]
}

cmd="${1:-status}"; shift || true
case "$cmd" in
  install)   install "${1:-}" ;;
  status)    status ;;
  link)      link ;;
  logs)      tail -n 40 -f "$DATA/logs/app.log" "$DATA/logs/tunnel.log" ;;
  restart)   launchctl kickstart -k "$GUI/app.tradevoice.web"; launchctl kickstart -k "$GUI/app.tradevoice.tunnel"
             wait_local && echo "restarted ✅  link: $(sleep 5; link)" ;;
  update)    update ;;
  backup)    cd "$REPO" && py scripts/backup.py ;;
  restore)   restore "${1:-}" ;;
  stop)      unload; echo "Stopped. It starts again when you log in next, or now with: bash deploy/mac/tradevoice.sh start" ;;
  start)     load; wait_local && echo "started ✅  link: $(sleep 5; link)" ;;
  uninstall) unload; for l in $LABELS; do rm -f "$AGENTS/$l.plist"; done
             echo "Removed. Your books, accounts and backups are still in $DATA (delete that folder yourself only when sure)." ;;
  _hourly)   hourly ;;
  *)         sed -n '2,9p' "$0"; exit 1 ;;
esac
