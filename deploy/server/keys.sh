#!/usr/bin/env bash
# Put the keys into the live server's .env by answering questions. What you paste is never shown or printed.
#   sudo bash /opt/tradevoice/app/deploy/server/keys.sh              every key, one by one (Enter = keep it as it is)
#   sudo bash /opt/tradevoice/app/deploy/server/keys.sh NATLAS_KEY   just that one
# Then it restarts the app and shows what it now uses (brain, hearing, WhatsApp), never the keys.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0"; exit 1; }
APP=${TV_APP:-/opt/tradevoice/app}
ENV="$APP/.env"
PY=$(command -v python3)
[ -f "$ENV" ] || { echo "No $ENV yet: run deploy/server/setup.sh first."; exit 1; }

# name | secret? | what it is (in the order they matter)
KEYS="NATLAS_URL|no|N-ATLaS brain link from Modal (starts https://, ends /v1)
NATLAS_ASR_URL|no|N-ATLaS speech link from Modal (starts https://)
NATLAS_KEY|yes|N-ATLaS key (the same one you set on Modal)
NVIDIA_API_KEY|yes|Backup AI key from build.nvidia.com (starts nvapi-)
WHATSAPP_TOKEN|yes|WhatsApp token from Meta (long, starts EA)
WHATSAPP_PHONE_ID|no|WhatsApp Phone number ID from Meta (digits only)
WHATSAPP_APP_SECRET|yes|Meta App secret (App settings > Basic)
WHATSAPP_VERIFY_TOKEN|yes|Any word you choose; type the same word in Meta's webhook settings
WHATSAPP_BOT_NUMBER|no|The bot's WhatsApp number, digits only, e.g. 2348012345678
TEAM_WHATSAPP|no|Team numbers for alerts, digits, comma between them
ADMIN_TOKEN|yes|Password for the team dashboard (/team); press Enter on an empty one to make one for you
INTRON_API_KEY|yes|Intron key (voice replies)
PAYSTACK_SECRET_KEY|yes|Paystack secret key (starts sk_test_ or sk_live_)
PAYSTACK_EMAIL|no|Email Paystack puts on payments
BACKUP_SUPABASE_URL|no|Supabase project link for backups (https://....supabase.co)
BACKUP_SUPABASE_KEY|yes|Supabase secret key for backups"

# the .env editor: the value comes in the environment (TV_V), never on a command line, so `ps` can't show it
EDIT_PY='
import os, re, sys
path, k, v = sys.argv[1], os.environ["TV_K"], os.environ["TV_V"]
key_line = re.compile(r"^[ \t]*#?[ \t]*(export[ \t]+)?" + re.escape(k) + r"[ \t]*=")
if v != "-" and re.search(r"\s|#", v) and "\"" not in v:
    v = "\"" + v + "\""                       # .env reads "a value with spaces or #" whole
new = ("# " + k + "=") if v == "-" else (k + "=" + v)
out, done = [], False
for ln in open(path, encoding="utf-8").read().split("\n"):
    if key_line.match(ln):
        if not done:
            out.append(new)
            done = True
            continue
        if not ln.lstrip().startswith("#"):
            continue                          # another active line for this key would win: drop it
    out.append(ln)
s = "\n".join(out)
if not done:
    s = s.rstrip("\n") + "\n" + new + "\n"
open(path, "w", encoding="utf-8").write(s)
'
has() { grep -qE "^[[:space:]]*(export[[:space:]]+)?$1[[:space:]]*=[[:space:]]*[^[:space:]#]" "$ENV"; }
put() { TV_K="$1" TV_V="$2" "$PY" -c "$EDIT_PY" "$ENV"; }
check() {   # NAME VALUE -> a warning when it looks wrong (the value itself is never printed)
  case "$1" in
    NATLAS_URL|NATLAS_ASR_URL|BACKUP_SUPABASE_URL) case "$2" in https://*) ;; *) echo "   ⚠️  links start with https:// (check it)";; esac ;;
  esac
  case "$1" in
    NATLAS_URL) case "$2" in */v1|*/v1/) ;; *) echo "   ⚠️  the N-ATLaS brain link usually ends in /v1";; esac ;;
    WHATSAPP_PHONE_ID|WHATSAPP_BOT_NUMBER) case "$2" in *[!0-9]*) echo "   ⚠️  digits only (no +, spaces or dashes)";; esac ;;
    NVIDIA_API_KEY) case "$2" in nvapi-*) ;; *) echo "   ⚠️  NVIDIA keys start with nvapi-";; esac ;;
    PAYSTACK_SECRET_KEY) case "$2" in sk_test_*|sk_live_*) ;; *) echo "   ⚠️  Paystack secret keys start with sk_test_ or sk_live_";; esac ;;
  esac
}

only="${1:-}"
echo "For each key: paste the value and press Enter. Enter alone = keep it as it is. A single - = remove it."
echo "Secret keys don't show while you paste: that's normal."
while IFS='|' read -r name secret what <&3; do
  [ -z "$only" ] || [ "$only" = "$name" ] || continue
  if has "$name"; then state="set ✅"; else state="not set"; fi
  printf '\n\033[1m%s\033[0m  (%s)\n   %s\n' "$name" "$state" "$what"
  val=""
  if [ "$secret" = yes ]; then read -rsp "   > " val || true; echo; else read -rp "   > " val || true; fi
  val=$(printf '%s' "$val" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
  if [ "$name" = ADMIN_TOKEN ] && [ -z "$val" ] && ! has ADMIN_TOKEN; then
    val=$("$PY" -c 'import secrets; print(secrets.token_urlsafe(24))')
    echo "   made one. Team dashboard: https://YOUR-LINK/team?key=$val   (keep it private)"
  fi
  if [ -z "$val" ]; then echo "   kept"; continue; fi
  check "$name" "$val"
  put "$name" "$val"
  if [ "$val" = "-" ]; then echo "   removed"; else echo "   saved ✅"; fi
done 3<<< "$KEYS"

# laptop-only settings never belong on the live server (demo codes, no login, local folders, old Brev links)
sed -i -E 's/^[[:space:]]*(export[[:space:]]+)?(ACCOUNTS_DB|BOOKS_DIR|DB_PATH|BACKUP_DIR|PORT|TRADEVOICE_ADMIN|TV_PUBLIC|AUTH_DEMO|AUTH_REQUIRED|AUTH_STRICT|LOCAL_LLM_URL|LOCAL_VISION_URL|ASR_ENGINE)[[:space:]]*=/# (not on the server) &/' "$ENV"
chown root:tradevoice "$ENV" 2>/dev/null || true
chmod 640 "$ENV"

[ -z "${TV_NO_RESTART:-}" ] || exit 0
echo; echo -n "Restarting the app "
systemctl restart tradevoice
for _ in $(seq 1 60); do curl -sf http://127.0.0.1:8000/api/status >/dev/null && break; echo -n "."; sleep 1; done
STATUS_PY='
import json, sys
s = json.load(sys.stdin)
brain, hearing, voice = s.get("brain"), s.get("hearing"), s.get("voice") or "off"
mark = lambda b: "✅" if b else "❌"
print(" ✅\n")
print("  brain (AI that understands):", brain, mark(brain == "natlas"), "(natlas = N-ATLaS on Modal)")
print("  hearing (voice notes):      ", hearing, mark(hearing == "natlas"))
print("  WhatsApp:                   ", mark(s.get("whatsapp")))
print("  voice replies:              ", voice)
'
curl -sf http://127.0.0.1:8000/api/status | "$PY" -c "$STATUS_PY" || echo " ❌ the app did not come back: sudo journalctl -u tradevoice -n 30"
