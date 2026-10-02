#!/usr/bin/env bash
# TradeVoice on one small Ubuntu 24.04 server (Azure for Students; any cloud works), with a free DuckDNS address and
# real HTTPS. The whole guide (Azure portal clicks, DuckDNS, moving the data from Modal): docs/HOSTING.md
#
#   sudo git clone https://github.com/Godzilla-lab/tradevoice /opt/tradevoice/app
#   sudo bash /opt/tradevoice/app/deploy/server/setup.sh
#
# Safe to run again (after an update that changed this file, or to change the DuckDNS name).
# What it sets up:
#   - the app as a service: starts when the server boots, restarts by itself if it crashes (systemd)
#   - Caddy in front: HTTPS certificate by itself, for https://<name>.duckdns.org
#   - DuckDNS kept pointing at this server (every 5 minutes)
#   - a backup of every book + the accounts every hour (scripts/backup.py), kept 30 days
#   - the firewall opened for web traffic (80, 443) only
# Code: /opt/tradevoice/app (root, read-only for the app)   Data: /var/lib/tradevoice (the app's user only)
# Keys: /opt/tradevoice/app/.env (root + the app only). Never in the repo or the chat.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0"; exit 1; }

APP=/opt/tradevoice/app
VENV=/opt/tradevoice/venv
DATA=/var/lib/tradevoice
ETC=/etc/tradevoice
PORT=8000
[ -f "$APP/src/web.py" ] || { echo "The code must be at $APP first: sudo git clone https://github.com/Godzilla-lab/tradevoice $APP"; exit 1; }
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# ------------------------------------------------------------------ DuckDNS name + token (asked once)
mkdir -p "$ETC" && chmod 755 "$ETC"
if [ ! -f "$ETC/duckdns.env" ] || [ "${1:-}" = "--duckdns" ]; then
  say "DuckDNS (duckdns.org): your free address"
  read -rp "Your DuckDNS name, the part before .duckdns.org (e.g. tradevoice): " SUB
  SUB=$(printf '%s' "$SUB" | tr 'A-Z' 'a-z' | sed 's/\.duckdns\.org$//; s/[^a-z0-9-]//g')
  [ -n "$SUB" ] || { echo "The name is needed."; exit 1; }
  for try in 1 2 3; do   # check the token with DuckDNS now, not at the end (it never shows on screen)
    read -rsp "Your DuckDNS token (top of duckdns.org; it won't show as you paste): " TOKEN; echo
    TOKEN=$(printf '%s' "$TOKEN" | tr -d '[:space:]')
    if [ "${#TOKEN}" -ne 36 ]; then echo "   That's ${#TOKEN} characters; a DuckDNS token has 36 (like a1b2c3d4-…). Copy it again."; continue; fi
    if curl -fsS --max-time 30 "https://www.duckdns.org/update?domains=$SUB&token=$TOKEN&ip=" 2>/dev/null | grep -q OK; then
      echo "   DuckDNS accepted it ✅"; break
    fi
    echo "   DuckDNS said no: check the name ($SUB) and that the token is from the same DuckDNS account."
    [ "$try" = 3 ] && exit 1
  done
  [ "${#TOKEN}" -eq 36 ] || exit 1
  umask 077
  printf 'DUCKDNS_SUB=%s\nDUCKDNS_TOKEN=%s\n' "$SUB" "$TOKEN" > "$ETC/duckdns.env"
  umask 022
fi
chmod 600 "$ETC/duckdns.env"
SUB=$(grep '^DUCKDNS_SUB=' "$ETC/duckdns.env" | cut -d= -f2)
DOMAIN="$SUB.duckdns.org"

# ------------------------------------------------------------------ packages
say "Installing packages (a few minutes the first time)"
export DEBIAN_FRONTEND=noninteractive
if pgrep -x unattended-upgr >/dev/null 2>&1 || pgrep -f '^/usr/bin/python3 /usr/bin/unattended-upgrade' >/dev/null 2>&1; then
  echo "   A new server first installs Ubuntu's own security updates: waiting for them (often 5-15 minutes)."
  echo "   Nothing is frozen. Don't close this window."
fi
APT="-o DPkg::Lock::Timeout=1800"   # wait for Ubuntu's own updates instead of failing
# shellcheck disable=SC2086
apt-get $APT update -qq
# shellcheck disable=SC2086
apt-get $APT install -y -qq python3 python3-venv ffmpeg sqlite3 git curl gnupg debian-keyring debian-archive-keyring \
  apt-transport-https iptables-persistent unattended-upgrades >/dev/null
if ! command -v caddy >/dev/null; then   # Caddy's official package (https://caddyserver.com/docs/install)
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  # shellcheck disable=SC2086
  apt-get $APT update -qq && apt-get $APT install -y -qq caddy >/dev/null
fi
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > /etc/apt/apt.conf.d/20auto-upgrades   # security updates by themselves
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "Python 3.10+ needed: use the Ubuntu 24.04 image."; exit 1; }

# a small server (1 GB) needs swap so installs and updates don't run out of memory
if [ "$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)" -lt 2000 ] && ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ------------------------------------------------------------------ the app's user, data folder, Python
id tradevoice >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin tradevoice
install -d -o tradevoice -g tradevoice -m 700 "$DATA" "$DATA/books" "$DATA/backups"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$APP/requirements-server.txt"

# ------------------------------------------------------------------ .env (keys): made once from .env.example
if [ ! -f "$APP/.env" ]; then
  cp "$APP/.env.example" "$APP/.env"
  sed -i 's/^NVIDIA_API_KEY=nvapi-your-key-here/# NVIDIA_API_KEY=/' "$APP/.env"
fi
set_env() {   # KEY VALUE: replace the line or add it (values here are never secrets)
  if grep -qE "^\s*#?\s*$1=" "$APP/.env"; then sed -i -E "s|^\s*#?\s*$1=.*|$1=$2|" "$APP/.env"; else echo "$1=$2" >> "$APP/.env"; fi
}
set_env PUBLIC_URL "https://$DOMAIN"
# laptop-only settings never belong on the live server (demo codes, no login, local folders, old Brev links)
sed -i -E 's/^[[:space:]]*(export[[:space:]]+)?(ACCOUNTS_DB|BOOKS_DIR|DB_PATH|BACKUP_DIR|PORT|TRADEVOICE_ADMIN|TV_PUBLIC|AUTH_DEMO|AUTH_REQUIRED|AUTH_STRICT|LOCAL_LLM_URL|LOCAL_VISION_URL|ASR_ENGINE)[[:space:]]*=/# (not on the server) &/' "$APP/.env"
chown root:tradevoice "$APP/.env" && chmod 640 "$APP/.env"

# ------------------------------------------------------------------ services
cat > "$ETC/paths.env" <<EOF
ACCOUNTS_DB=$DATA/accounts.db
BOOKS_DIR=$DATA/books
DB_PATH=$DATA/tradevoice.db
BACKUP_DIR=$DATA/backups
PORT=$PORT
TRADEVOICE_ADMIN=0
TV_PUBLIC=1
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
EOF
chmod 644 "$ETC/paths.env"

cat > /etc/systemd/system/tradevoice.service <<EOF
[Unit]
Description=TradeVoice web app (WhatsApp + Paystack webhooks, /app, /team)
After=network-online.target
Wants=network-online.target

[Service]
User=tradevoice
Group=tradevoice
WorkingDirectory=$APP
EnvironmentFile=$ETC/paths.env
# one process only: every book is a SQLite file, and only one writer at a time is safe
ExecStart=$VENV/bin/uvicorn web:app --app-dir src --host 127.0.0.1 --port $PORT --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/tradevoice-backup.service <<EOF
[Unit]
Description=TradeVoice backup (books + accounts)

[Service]
Type=oneshot
User=tradevoice
Group=tradevoice
WorkingDirectory=$APP
EnvironmentFile=$ETC/paths.env
ExecStart=$VENV/bin/python scripts/backup.py
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA
EOF
cat > /etc/systemd/system/tradevoice-backup.timer <<EOF
[Unit]
Description=TradeVoice backup every hour

[Timer]
OnCalendar=hourly
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/duckdns.service <<EOF
[Unit]
Description=Point $DOMAIN at this server
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=$ETC/duckdns.env
ExecStart=/bin/sh -c 'curl -fsS --max-time 30 "https://www.duckdns.org/update?domains=\${DUCKDNS_SUB}&token=\${DUCKDNS_TOKEN}&ip=" | grep -q OK'
EOF
cat > /etc/systemd/system/duckdns.timer <<EOF
[Unit]
Description=Keep $DOMAIN pointing at this server

[Timer]
OnBootSec=30
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

cat > /etc/caddy/Caddyfile <<EOF
# TradeVoice (made by deploy/server/setup.sh). Caddy gets and renews the HTTPS certificate by itself.
$DOMAIN {
	encode gzip
	request_body {
		max_size 30MB
	}
	reverse_proxy 127.0.0.1:$PORT
}
EOF

# ------------------------------------------------------------------ firewall: some clouds' Ubuntu (Oracle) blocks all but SSH
for p in 80 443; do
  if ! iptables -C INPUT -p tcp --dport "$p" -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null; then
    n=$(iptables -L INPUT --line-numbers -n | awk '$2=="REJECT" {print $1; exit}')
    if [ -n "$n" ]; then iptables -I INPUT "$n" -p tcp --dport "$p" -m conntrack --ctstate NEW -j ACCEPT
    else iptables -A INPUT -p tcp --dport "$p" -m conntrack --ctstate NEW -j ACCEPT; fi
  fi
done
netfilter-persistent save >/dev/null 2>&1 || true

# ------------------------------------------------------------------ start
say "Starting"
systemctl daemon-reload
systemctl start duckdns.service || { echo "❌ DuckDNS refused the name or token. Run again with: sudo bash $0 --duckdns"; exit 1; }
systemctl enable --now duckdns.timer tradevoice-backup.timer >/dev/null 2>&1
systemctl enable tradevoice caddy >/dev/null 2>&1
systemctl restart tradevoice caddy

echo -n "⏳ app "
for _ in $(seq 1 60); do curl -sf "http://127.0.0.1:$PORT/api/status" >/dev/null && break; echo -n "."; sleep 1; done
curl -sf "http://127.0.0.1:$PORT/api/status" >/dev/null && echo " ✅" || { echo " ❌  see: sudo journalctl -u tradevoice -n 50"; exit 1; }
echo -n "⏳ https://$DOMAIN (the certificate can take a minute) "
for _ in $(seq 1 45); do curl -sf "https://$DOMAIN/api/status" >/dev/null && break; echo -n "."; sleep 2; done
if curl -sf "https://$DOMAIN/api/status" >/dev/null; then echo " ✅"; else
  echo " ❌"
  echo "   Most likely the cloud's own firewall: open ports 80 and 443 (Azure: the VM → Networking → inbound port rules;"
  echo "   docs/HOSTING.md, step 2). Or the DuckDNS name doesn't point here yet: wait 5 minutes and run this again."
  echo "   Then: sudo systemctl restart caddy   and check: sudo journalctl -u caddy -n 30"
fi
systemctl start tradevoice-backup.service && echo "first backup ✅" || echo "first backup ❌  see: sudo journalctl -u tradevoice-backup -n 20"

cat <<EOF

🟢 TradeVoice: https://$DOMAIN/app        website: https://$DOMAIN
   WhatsApp webhook (Meta):    https://$DOMAIN/whatsapp/webhook
   Paystack webhook:           https://$DOMAIN/paystack/webhook
   Team dashboard:             https://$DOMAIN/team?key=<ADMIN_TOKEN>

Next: the keys (it asks for each one; never paste them in a chat):
   sudo bash $APP/deploy/server/keys.sh
Logs:     sudo journalctl -u tradevoice -f
Backups:  sudo ls -lh $DATA/backups
Update:   sudo bash $APP/deploy/server/update.sh
EOF
