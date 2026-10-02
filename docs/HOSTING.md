# 🌍 Hosting TradeVoice live (Oracle Cloud Always Free + DuckDNS)

The web app, the WhatsApp and Paystack webhooks, every trader's book and the accounts run on **one free Oracle Cloud
server** in Johannesburg (the closest Oracle region to Nigeria), at a free fixed address **https://NAME.duckdns.org**.
N-ATLaS and the speech models stay on Modal (they need a GPU; the server only calls them).
Live now on AWS (free-plan credits): [`HOSTING_AWS.md`](HOSTING_AWS.md). This guide is for moving to Oracle's free server
later (it needs a card that pays abroad); the same scripts work on any Ubuntu 24.04 server.

| What | Where | Cost |
|---|---|---|
| App + books + accounts | Oracle Always Free VM (Ubuntu 24.04), `/var/lib/tradevoice` | $0 |
| HTTPS + fixed address | Caddy (certificate by itself) + DuckDNS | $0 |
| Backups | every hour on the server (48 h all, then 1 a day for 30 days) + a copy in Oracle Object Storage | $0 (20 GB free) |
| N-ATLaS brain + speech | Modal (`NATLAS_URL`, `NATLAS_ASR_URL`, `NATLAS_KEY`) | GPU time: set a Modal spending limit |

Why not the others (checked 2 Oct 2026): Render/Koyeb free plans sleep and lose files on restart (WhatsApp messages and
reminders need the server awake); Fly.io has no free plan; Cloudflare Workers allow 10 ms of CPU per request on the free
plan and have no files or ffmpeg (our books are SQLite files), and Cloudflare Containers need the $5 plan; Modal's
$30/month free credit is shared with the N-ATLaS GPU (about $10 a day).

## 1. Oracle account (once)
1. Sign up at **oracle.com/cloud/free**. Pick **South Africa Central (Johannesburg)** as the home region: it can't be
   changed later. A card is checked but not charged.
2. **Upgrade to Pay As You Go** (Billing → Upgrade). Still $0 while you stay in the Always Free limits, and Oracle then
   won't reclaim the server for being "idle" (free-only accounts lose VMs that stay under 20% use for 7 days).
   Straight after: **Billing → Budgets → Create budget**, $1, alert to the team email, so any charge is seen at once.

## 2. The server
Compute → Instances → **Create instance**:
- Image: **Canonical Ubuntu 24.04**. Shape: **Ampere VM.Standard.A1.Flex, 2 OCPU, 12 GB** (Always Free).
  "Out of capacity"? Try another availability domain, or later, or use **VM.Standard.E2.1.Micro** (also free, 1 GB:
  enough, the setup adds swap).
- Networking: keep "Assign a public IPv4 address".
- SSH keys: **Generate a key pair for me → Save private key**. Keep that file safe and private (it opens the server).
- Create. Copy the **Public IP address**.

## 3. Open the web ports (Oracle's own firewall)
Instance → **Subnet** link → **Security Lists** → Default Security List → **Add Ingress Rules**:
source `0.0.0.0/0`, IP protocol TCP, destination port **80**. Add a second rule, the same, port **443**.
(The server's own firewall is opened by the setup script.)

## 4. DuckDNS (free address)
**duckdns.org** → sign in (Google or GitHub) → type a name (e.g. `tradevoice`) → **add domain**. Copy the **token** at
the top of the page. You don't need to type the IP: the server keeps it up to date every 5 minutes.

## 5. Install (one command on the server)
On the Mac (Terminal):
```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@PUBLIC_IP
```
On the server:
```bash
sudo git clone https://github.com/Godzilla-lab/tradevoice /opt/tradevoice/app
sudo bash /opt/tradevoice/app/deploy/server/setup.sh
```
It asks for the DuckDNS name and token (the token doesn't show while you paste it), installs everything, starts the app
and prints the links. "https … ✅" means the certificate is in place; a ❌ there is almost always step 3.

## 6. Keys
```bash
sudo bash /opt/tradevoice/app/deploy/server/keys.sh            # asks for each key by name; Enter = keep / skip
sudo bash /opt/tradevoice/app/deploy/server/keys.sh NATLAS_KEY # just one
```
It never shows what you paste, warns when a value looks wrong (a link without https://, a phone ID with spaces…),
switches off laptop-only settings, restarts the app and shows what it now uses (brain, hearing, WhatsApp).
(By hand instead: `sudo nano /opt/tradevoice/app/.env`, then `sudo systemctl restart tradevoice`.)
Fill in: `NATLAS_URL`, `NATLAS_ASR_URL`, `NATLAS_KEY`, `ADMIN_TOKEN`, `TEAM_WHATSAPP`, `WHATSAPP_TOKEN`,
`WHATSAPP_PHONE_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_BOT_NUMBER`, `INTRON_API_KEY`,
`PAYSTACK_SECRET_KEY`, `PAYSTACK_EMAIL`, `BACKUP_UPLOAD_URL` (step 7). `PUBLIC_URL` is set by the setup.
Keys go only in this file: never in the repo, the chat, or a screenshot.

**Sign-up needs WhatsApp.** The live server never shows codes on screen (`AUTH_DEMO` is forced off there: with it,
anyone could open any trader's book). Until Meta verification is done, the WhatsApp test number sends codes to up to
5 numbers registered in the Meta dashboard: the team and the 2 beta testers.
While Meta verification is pending, either skip the WhatsApp questions (no sign-up yet) or use the test number's
Phone number ID with a permanent **system user** token (the dashboard's temporary token stops working after 24 hours).
Or the team creates accounts for people it knows (no WhatsApp code needed):
```bash
sudo bash /opt/tradevoice/app/deploy/server/add_account.sh 08031234567 "Ada" "Ada Stores"   # prints a temporary password
sudo bash /opt/tradevoice/app/deploy/server/add_account.sh 08031234567 --reset              # forgot it: a new one
```
Give the password to the person directly (never in a group); they log in with phone + password, then Me → Password.

## 7. Backups off the server
Oracle console → Storage → **Buckets** → Create bucket `tradevoice-backups` (private, the default). In the bucket:
1. **Pre-Authenticated Requests → Create**: target **Bucket**, access **Permit object writes**, expiry in 1 year.
   Copy the URL (it ends in `/o/`) into `.env` as `BACKUP_UPLOAD_URL=`. Treat it like a password.
2. **Lifecycle Policy Rules → Create**: delete objects older than 30 days.

Check: `sudo systemctl start tradevoice-backup && sudo journalctl -u tradevoice-backup -n 5` → "uploaded off the server ✅".
Backups hold traders' personal data: the bucket stays private, and a backup is never emailed or shared.

## 8. Move the books from Modal (or from the AWS server)
From another TradeVoice server (AWS → Oracle): `sudo systemctl stop tradevoice && sudo systemctl start tradevoice-backup`
there, copy the newest `/var/lib/tradevoice/backups/tradevoice-….tar.gz` to the new server, then
`sudo bash /opt/tradevoice/app/deploy/server/restore.sh FILE`, and point the DuckDNS name / webhooks at the new server.

From Modal: (once, after steps 1–7 work)
On the Mac (where `modal` is set up):
```bash
modal app stop tradevoice-web            # stop it first, so nothing is written during the copy
mkdir modal-data && cd modal-data
modal volume get tradevoice-data accounts.db .
modal volume get tradevoice-data books .
modal volume get tradevoice-data tradevoice.db .     # may not exist: fine
cd .. && scp -i ~/Downloads/ssh-key-*.key -r modal-data ubuntu@PUBLIC_IP:/tmp/
```
On the server:
```bash
sudo bash /opt/tradevoice/app/deploy/server/restore.sh /tmp/modal-data && rm -rf /tmp/modal-data
```
Then delete `modal-data` on the Mac (personal data). Traders log in again once (new address).
The old `natlas` secret in the paused workspace still holds the Hugging Face token: delete it.

## 9. Webhooks (the new address)
- **Meta** → WhatsApp → Configuration → Callback URL `https://NAME.duckdns.org/whatsapp/webhook`, Verify token = your
  `WHATSAPP_VERIFY_TOKEN` → Verify and save → subscribe to `messages`.
- **Paystack** → Settings → API Keys & Webhooks → `https://NAME.duckdns.org/paystack/webhook`.

## Every day
| Task | Command (on the server) |
|---|---|
| Is it up? | `systemctl status tradevoice` · or open `https://NAME.duckdns.org/api/status` |
| Logs (live) | `sudo journalctl -u tradevoice -f` (Ctrl+C to leave) |
| Put new code live | `sudo bash /opt/tradevoice/app/deploy/server/update.sh` (backs up, restarts, rolls back by itself if the new code doesn't start) |
| Backups | `sudo ls -lh /var/lib/tradevoice/backups` |
| Restore a backup | `sudo bash /opt/tradevoice/app/deploy/server/restore.sh /var/lib/tradevoice/backups/tradevoice-….tar.gz` (the replaced files are kept in `before-restore-…`) |
| A backup onto the Mac | `ssh -i KEY ubuntu@PUBLIC_IP "sudo cat /var/lib/tradevoice/backups/FILE" > FILE` |
| Change the DuckDNS name | `sudo bash /opt/tradevoice/app/deploy/server/setup.sh --duckdns` |

What runs by itself: the app restarts if it crashes and starts when the server boots; a backup every hour; DuckDNS every
5 minutes; Ubuntu security updates; the HTTPS certificate renews; accounts deleted 7+ days ago are erased (hourly).

## Data
- The books and accounts are stored in **South Africa** (Oracle Johannesburg). Nigeria's data protection law allows
  storage abroad with safeguards; say where the data is kept in the privacy notice, and have someone who knows the law
  confirm it.
- On the server: code in `/opt/tradevoice/app` (read-only for the app), data in `/var/lib/tradevoice` (only the app's
  user can open it), keys in `.env` (root + the app only), only ports 80/443 (and SSH) open.
- A deleted account is erased 7 days later (book, sessions, profile). Hourly backups made before that roll off within
  30 days.

## Tested
`deploy/server/setup.sh` was run end to end on Ubuntu 24.04 with systemd and Oracle's default firewall rules (2 Oct):
app ✅, firewall 80/443 inserted before Oracle's REJECT rule (and with an open firewall, like AWS/Azure), run twice (safe), HTTPS through Caddy (with a test
certificate), webhook check, 12 MB upload, port 8000 closed from outside, hourly backup, restore from a backup and from a
Modal-style folder, `update.sh` with a good update and with a broken one (rolled back by itself). Not testable outside
Oracle: the real DuckDNS update and Let's Encrypt certificate (step 5 shows ✅ or ❌ for both).
