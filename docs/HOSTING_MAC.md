# 💻 TradeVoice live from a Mac (until the Oracle server is ready)

The app, the WhatsApp and Paystack webhooks, every trader's book and the accounts run on **your Mac**, reachable from
anywhere through a free **Cloudflare Tunnel** (no open ports, no card). N-ATLaS and the speech models stay on Modal.
When Oracle (or AWS/Azure) is ready, the books move over with one backup and one restore: [`HOSTING.md`](HOSTING.md).

**It runs by itself:** starts when you log in, restarts if it crashes, keeps the Mac from idle-sleeping, backs up every
hour (and copies each backup off the Mac). **When the Mac is off** the link doesn't answer; nothing saved is lost, and
WhatsApp keeps re-sending the messages it couldn't deliver for up to 7 days, so they arrive when the Mac is back.

## 1. The Mac (once)
- **Plugged in, lid open, logged in.** A closed MacBook lid sleeps no matter what.
- System Settings → **Battery** → Options (or **Energy**): *Prevent automatic sleeping on power adapter when the display
  is off* → on. Desktop Macs: *Start up automatically after a power failure* → on.
- System Settings → General → Software Update → Automatic updates: turn off *Install macOS updates* during the pilot
  (an overnight restart waits for your password).
- Keep **FileVault on** (Privacy & Security): a stolen laptop then doesn't hand over traders' books. The price: after a
  restart someone types the password once, then everything starts by itself.
- Power: if the router has no backup power, a power cut takes the link down even while the MacBook runs on battery.

## 2. Install (one command)
1. **Homebrew** (skip if `brew` already works in Terminal): the one-line command on **brew.sh**, then the two lines it
   prints at the end ("Next steps") so Terminal finds it.
2. Terminal:
   ```bash
   git clone https://github.com/Godzilla-lab/tradevoice ~/tradevoice
   cd ~/tradevoice && bash deploy/mac/tradevoice.sh install
   ```
   Keep the folder at `~/tradevoice` (not Desktop/Documents/Downloads: macOS blocks background apps there).
   It installs Python, ffmpeg and cloudflared, starts everything and prints the link.

Without a domain you get a **quick link** (`https://….trycloudflare.com`): fine for testing, but it **changes whenever the
Mac or the tunnel restarts** (`bash deploy/mac/tradevoice.sh link` shows the current one), and the WhatsApp/Paystack
webhooks must then be entered again. For the pilot, use a fixed link (step 4).

## 3. Keys
```bash
cd ~/tradevoice && nano .env          # fill in; save: Ctrl+O, Enter, Ctrl+X   (not TextEdit: it changes quotes)
bash deploy/mac/tradevoice.sh restart
```
`NATLAS_URL`, `NATLAS_ASR_URL`, `NATLAS_KEY`, `ADMIN_TOKEN`, `TEAM_WHATSAPP`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`,
`WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_BOT_NUMBER`, `INTRON_API_KEY`, `PAYSTACK_SECRET_KEY`,
`PAYSTACK_EMAIL`, and the backup copy (step 5). Keys go only in `.env` (only you can open it): never in the repo, the
chat, or a screenshot.

**Sign-up needs WhatsApp**: on a public link codes are never shown on screen (`AUTH_DEMO` is forced off: with it, anyone
could open any trader's book). Until Meta verification is done, the WhatsApp test number sends codes to up to 5 numbers
registered in the Meta dashboard: the team and the 2 beta testers.

## 4. A fixed link (recommended: about ₦3,000–6,250 a year, paid in Naira)
1. Buy a `.com.ng` (or any) domain from a Nigerian registrar (Whogohost, MokoHost, …) with your Naira card.
2. **dash.cloudflare.com** (free account, no card) → **Add a domain** → Free plan. Cloudflare shows 2 nameservers: put
   them in the registrar's "nameservers" page. Wait until Cloudflare says the domain is **Active** (minutes to hours).
3. ```bash
   cd ~/tradevoice && bash deploy/mac/tradevoice.sh install app.YOURDOMAIN.com.ng
   ```
   A browser opens once: log in to Cloudflare and pick the domain. The link is now `https://app.YOURDOMAIN.com.ng` for
   good, and the same domain moves with you to Oracle later (traders keep the same link).

## 5. Backups off the Mac (pick one, both free, no card)
- **Supabase Storage** (works even while you're away from the Mac): supabase.com → New project `tradevoice-backups`
  (only for backups) → **Storage → New bucket** `backups`, private → **Project Settings → API Keys**: copy the project
  URL and the **secret** key into `.env`:
  ```
  BACKUP_SUPABASE_URL=https://PROJECT.supabase.co
  BACKUP_SUPABASE_KEY=...        # the secret key: treat it like a password
  ```
  Hourly uploads keep the free project from pausing. Old copies there are pruned like the ones on the Mac.
- **Google Drive** (Google Drive for desktop installed): `BACKUP_COPY_DIR=/Users/YOU/Library/CloudStorage/GoogleDrive-…/My Drive/TradeVoice backups`.
  macOS may ask once whether Python may open Google Drive: allow.

Check: `bash deploy/mac/tradevoice.sh backup` → "copied to Supabase ✅" (or "copied to the backup folder ✅").
Backups hold traders' personal data: keep the bucket private and never share a backup.

## 6. Move the books from Modal (once)
```bash
modal app stop tradevoice-web            # stop it first, so nothing is written during the copy
mkdir ~/modal-data && cd ~/modal-data
modal volume get tradevoice-data accounts.db .
modal volume get tradevoice-data books .
modal volume get tradevoice-data tradevoice.db .     # may not exist: fine
cd ~/tradevoice && bash deploy/mac/tradevoice.sh restore ~/modal-data && rm -rf ~/modal-data
```
Traders log in again once (new address). Also delete the old `natlas` secret in the paused Modal workspace (it holds the
Hugging Face token).

## 7. Webhooks
- **Meta** → WhatsApp → Configuration → Callback URL `https://LINK/whatsapp/webhook`, Verify token = your
  `WHATSAPP_VERIFY_TOKEN` → Verify and save → subscribe to `messages`.
- **Paystack** → Settings → API Keys & Webhooks → `https://LINK/paystack/webhook`.

## Every day (in Terminal, `cd ~/tradevoice` first)
| Task | Command |
|---|---|
| Is it up? Which link? | `bash deploy/mac/tradevoice.sh status` |
| Logs (live) | `bash deploy/mac/tradevoice.sh logs` (Ctrl+C to leave) |
| After editing `.env` | `bash deploy/mac/tradevoice.sh restart` |
| Put new code live | `bash deploy/mac/tradevoice.sh update` (backs up, restarts, goes back by itself if the new code doesn't start) |
| Backup now | `bash deploy/mac/tradevoice.sh backup` (backups: `~/tradevoice-data/backups`) |
| Restore | `bash deploy/mac/tradevoice.sh restore ~/tradevoice-data/backups/tradevoice-….tar.gz` (replaced files kept in `before-restore-…`) |
| Pause / resume | `bash deploy/mac/tradevoice.sh stop` / `start` |
| Remove (keeps the data) | `bash deploy/mac/tradevoice.sh uninstall` |

## Moving to Oracle (or AWS/Azure) later
1. Set up the server ([`HOSTING.md`](HOSTING.md)), with the keys in its `.env`.
2. On the Mac: `bash deploy/mac/tradevoice.sh stop && bash deploy/mac/tradevoice.sh backup`, then copy the newest
   `~/tradevoice-data/backups/tradevoice-….tar.gz` to the server and run `sudo bash /opt/tradevoice/app/deploy/server/restore.sh FILE`.
3. Point the domain at the server (Cloudflare DNS: an `A` record with the server's IP instead of the tunnel), re-enter
   the webhooks if the link changed, then `bash deploy/mac/tradevoice.sh uninstall` on the Mac.

## Tested (2 Oct)
`deploy/mac/tradevoice.sh` was run end to end with stand-ins for macOS's launchd, Homebrew and cloudflared that really
start each job from its generated plist: install (quick link and fixed link; reinstall keeps the fixed link), status,
link, backup, restart, update (a good one, and a broken one rolled back by itself), restore, stop/start, the hourly job
(backup + log trimming), uninstall (data kept). The tunnel config was checked by the real cloudflared (`ingress
validate`). Not testable off a real Mac: macOS itself (launchd, caffeinate, Homebrew) and the real tunnel; the install
prints ✅ or ❌ for each step.
