#!/usr/bin/env bash
# The film's voice clips, made with Spitch on the live server (the Spitch key stays on the server). Paste on the server:
#   sudo bash -c 'cd /opt/tradevoice/app && git fetch -q origin claude/tradevoice-handoff-b7942v && git show FETCH_HEAD:film/voices.sh | bash'
# and afterwards, to remove the clips again:
#   sudo bash -c 'cd /opt/tradevoice/app && git show FETCH_HEAD:film/voices.sh | bash -s -- --clean'
# Nothing is checked out and the app is not restarted: the server stays on the frozen code. The clips go to
# web/film-voices/ (untracked), which the running app serves at /static/film-voices/ so they can be downloaded.
# The key: SPITCH_API_KEY from the server's .env, or typed here (hidden). It is never printed.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo (see the top of this file)."; exit 1; }
APP=${TV_APP:-/opt/tradevoice/app}
OUT="$APP/web/film-voices"
cd "$APP"

if [ "${1:-}" = "--clean" ]; then
  rm -rf "$OUT" && echo "Film voice clips removed from the server."
  exit 0
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git show FETCH_HEAD:film/voices.py > "$TMP/voices.py"
git show FETCH_HEAD:film/lines.json > "$TMP/lines.json"

key=$(grep -E '^[[:space:]]*(export[[:space:]]+)?SPITCH_API_KEY[[:space:]]*=' .env 2>/dev/null | tail -1 \
      | cut -d= -f2- | sed -E 's/^[[:space:]"'"'"']+//; s/[[:space:]"'"'"']+$//') || true
if [ -z "$key" ]; then
  echo "Spitch API key (from spitch.app, Developers > API keys). It does not show while you paste: that's normal."
  read -rsp "   > " key </dev/tty || true; echo
  key=$(printf '%s' "$key" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
  [ -n "$key" ] || { echo "No key typed. Nothing made."; exit 1; }
  read -rp "Keep it in the server's .env for next time? (y/N) " keep </dev/tty || true
  if [ "${keep:-n}" = y ] || [ "${keep:-n}" = Y ]; then
    TV_V="$key" python3 -c 'import os; open(".env", "a", encoding="utf-8").write("\nSPITCH_API_KEY=" + os.environ["TV_V"] + "\n")'
    echo "   saved in .env"
  fi
fi

echo "Making the film's voice clips with Spitch (about a minute)..."
SPITCH_API_KEY="$key" python3 "$TMP/voices.py" "$TMP/lines.json" "$OUT"
echo
echo "Done. Tell Claude: voices are ready."
echo "(Listen here: https://tradevoice.duckdns.org/static/film-voices/index.json lists the files.)"
