#!/usr/bin/env bash
# Tool-call accuracy per language with the live N-ATLaS (E10), using the server's keys. Uses a throwaway demo book in
# /tmp: no trader's book is read or changed, and nothing is added to the /team evidence. Wakes the N-ATLaS GPU.
#   sudo bash /opt/tradevoice/app/deploy/server/tools_eval.sh            rules first, then N-ATLaS (as the app does)
#   sudo bash /opt/tradevoice/app/deploy/server/tools_eval.sh --show     ...and every miss
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0"; exit 1; }
APP=/opt/tradevoice/app
cd "$APP"
exec runuser -u tradevoice -- env -u DB_PATH -u BOOKS_DIR -u ACCOUNTS_DB \
  /opt/tradevoice/venv/bin/python eval/run_tools_eval.py --llm "$@"
