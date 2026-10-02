# 🌍 Hosting TradeVoice live (Azure for Students + DuckDNS)

The web app, the WhatsApp and Paystack webhooks, every trader's book and the accounts run on **one small Azure server**
(free with Azure for Students, no card), at a free fixed address **https://NAME.duckdns.org**.
N-ATLaS and the speech models stay on Modal (they need a GPU; the server only calls them).

| What | Where | Cost |
|---|---|---|
| App + books + accounts | Azure VM `Standard_B2ats_v2` (2 vCPU, 1 GB), Ubuntu 24.04, 64 GB SSD, data in `/var/lib/tradevoice` | $0: 750 free hours/month = always on |
| HTTPS + fixed address | Caddy (certificate by itself) + DuckDNS | $0 |
| Backups | every hour on the server (48 h all, then 1 a day for 30 days) + a copy in Azure Blob Storage | $0 (5 GB free) |
| Public IP | static | small; paid from the $100 student credit if not in the free list |
| N-ATLaS brain + speech | Modal (`NATLAS_URL`, `NATLAS_ASR_URL`, `NATLAS_KEY`) | GPU time: Modal credit |

Why this one (checked 2 Oct 2026): Oracle's free server needs a working card; Render/Koyeb free plans sleep and lose
files on restart (WhatsApp and reminders need the server awake); Fly.io has no free plan; Cloudflare Workers allow 10 ms
of CPU per request on the free plan and have no files or ffmpeg (our books are SQLite files); Hugging Face Spaces wipe
the disk on every restart. The same scripts work on any Ubuntu 24.04 server, so moving later is easy.

## 1. Azure for Students (once)
1. **azure.microsoft.com/free/students** → sign in and verify with a **university email**. No card. You get $100 of credit
   for 12 months (renew each year while still a student) and the free services below.
2. **Which regions you may use** (every student subscription gets its own short list): portal → **Subscriptions** →
   Azure for Students → **Policies** → "Allowed resource deployment regions" → Parameters. Pick, in this order, the first
   one on your list: **South Africa North**, West Europe, North Europe, France Central, UK South, Spain Central,
   Italy North, UAE North (the closest to Nigeria first).
3. No card means Azure can never charge you: if the credit runs out or the 12 months end, the subscription is switched
   off (and the server stops) until it is renewed. Check **Cost Management** now and then; staying on the free sizes
   below keeps the credit almost untouched.

## 2. The server
Portal → **Virtual machines** → **Create** → Azure virtual machine.
- **Basics**: Subscription *Azure for Students*; Resource group: **Create new** `tradevoice`; Name `tradevoice`;
  Region: from step 1.2; Availability: *No infrastructure redundancy required*; Image: **Ubuntu Server 24.04 LTS - x64
  Gen2**; Size: **Standard_B2ats_v2** (marked "free services eligible"; if it isn't offered in your region: Standard_B1s);
  Authentication: **SSH public key**, username `azureuser`, *Generate new key pair*, key name `tradevoice-key`;
  Public inbound ports: **Allow selected ports → HTTP (80), HTTPS (443), SSH (22)**.
- **Disks**: OS disk size **64 GiB (P6)**, type **Premium SSD** (the free disk is a 64 GiB P6; a different size is billed).
- **Management**: make sure **Auto-shutdown is off** (if it's on, the app goes offline every night).
- **Review + create** → Create → **Download private key and create resource**. The `.pem` file is offered only this
  once: keep it safe and private (it opens the server).
- When it's done: **Go to resource** → copy the **Public IP address**.

## 3. DuckDNS (free address)
**duckdns.org** → sign in (Google or GitHub) → type a name (e.g. `tradevoice`) → **add domain**. Copy the **token** at
the top of the page. You don't need to type the IP: the server sets it, and checks it every 5 minutes.

## 4. Install (one command on the server)
On the Mac (Terminal):
```bash
chmod 400 ~/Downloads/tradevoice-key.pem
ssh -i ~/Downloads/tradevoice-key.pem azureuser@PUBLIC_IP
```
On the server:
```bash
sudo git clone https://github.com/Godzilla-lab/tradevoice /opt/tradevoice/app
sudo bash /opt/tradevoice/app/deploy/server/setup.sh
```
It asks for the DuckDNS name and token (the token doesn't show while you paste it), installs everything, starts the app
and prints the links. "https … ✅" means the certificate is in place. A ❌ there: check that the VM allows ports 80 and
443 (VM → **Networking** → inbound port rules), wait 5 minutes for DuckDNS, then run the same command again.

## 5. Keys
```bash
sudo nano /opt/tradevoice/app/.env      # fill in, save with Ctrl+O, Enter, Ctrl+X
sudo systemctl restart tradevoice
```
Fill in: `NATLAS_URL`, `NATLAS_ASR_URL`, `NATLAS_KEY`, `ADMIN_TOKEN`, `TEAM_WHATSAPP`, `WHATSAPP_TOKEN`,
`WHATSAPP_PHONE_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_BOT_NUMBER`, `INTRON_API_KEY`,
`PAYSTACK_SECRET_KEY`, `PAYSTACK_EMAIL`, `BACKUP_UPLOAD_URL` (step 6). `PUBLIC_URL` is set by the setup.
Keys go only in this file: never in the repo, the chat, or a screenshot.

**Sign-up needs WhatsApp.** The live server never shows codes on screen (`AUTH_DEMO` is forced off there: with it,
anyone could open any trader's book). Until Meta verification is done, the WhatsApp test number sends codes to up to
5 numbers registered in the Meta dashboard: the team and the 2 beta testers.

## 6. Backups off the server
Portal → **Storage accounts** → **Create**: resource group `tradevoice`, a unique lowercase name (e.g.
`tradevoicebackups`), the same region, Performance **Standard**, Redundancy **LRS** → Review + create. Then, in it:
1. **Data storage → Containers → + Container** `backups` (access: Private).
2. Open `backups` → **Settings → Shared access tokens**: permissions **Create** and **Write** only, expiry in 1 year,
   allowed protocols HTTPS only → **Generate SAS token and URL** → copy the **Blob SAS URL** into `.env` as
   `BACKUP_UPLOAD_URL=`. Treat it like a password. (It stops working on the expiry date: make a new one before then.)
3. Storage account → **Data management → Lifecycle management → Add a rule**: base blobs, "Last modified more than
   30 days ago" → **Delete the blob**.

Check: `sudo systemctl start tradevoice-backup && sudo journalctl -u tradevoice-backup -n 5` → "uploaded off the server ✅".
Backups hold traders' personal data: the container stays private, and a backup is never emailed or shared.

## 7. Move the books from Modal (once, after steps 1–6 work)
On the Mac (where `modal` is set up):
```bash
modal app stop tradevoice-web            # stop it first, so nothing is written during the copy
mkdir modal-data && cd modal-data
modal volume get tradevoice-data accounts.db .
modal volume get tradevoice-data books .
modal volume get tradevoice-data tradevoice.db .     # may not exist: fine
cd .. && scp -i ~/Downloads/tradevoice-key.pem -r modal-data azureuser@PUBLIC_IP:/tmp/
```
On the server:
```bash
sudo bash /opt/tradevoice/app/deploy/server/restore.sh /tmp/modal-data && rm -rf /tmp/modal-data
```
Then delete `modal-data` on the Mac (personal data). Traders log in again once (new address).
The old `natlas` secret in the paused Modal workspace still holds the Hugging Face token: delete it.

## 8. Webhooks (the new address)
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
| A backup onto the Mac | `ssh -i KEY azureuser@PUBLIC_IP "sudo cat /var/lib/tradevoice/backups/FILE" > FILE` |
| Change the DuckDNS name | `sudo bash /opt/tradevoice/app/deploy/server/setup.sh --duckdns` |

What runs by itself: the app restarts if it crashes and starts when the server boots; a backup every hour; DuckDNS every
5 minutes; Ubuntu security updates; the HTTPS certificate renews; accounts deleted 7+ days ago are erased (hourly).

## Data
- The books and accounts are stored in the Azure region picked in step 1.2 (e.g. South Africa or the Netherlands).
  Nigeria's data protection law allows storage abroad with safeguards; say where the data is kept in the privacy
  notice, and have someone who knows the law confirm it.
- On the server: code in `/opt/tradevoice/app` (read-only for the app), data in `/var/lib/tradevoice` (only the app's
  user can open it), keys in `.env` (root + the app only), only ports 80/443 (and SSH) open; the app itself listens
  only inside the server.
- A deleted account is erased 7 days later (book, sessions, profile). Hourly backups made before that roll off within
  30 days.
- The student subscription can lapse (credit used up, 12 months, or the student leaves): keep the off-server backup
  working, and download a backup to a team computer every week.

## Tested
`deploy/server/setup.sh` was run end to end on Ubuntu 24.04 with systemd (2 Oct), with an open firewall (like Azure)
and with Oracle's default REJECT rules: app ✅, run twice (safe), HTTPS through Caddy (with a test certificate), webhook
check, 12 MB upload, port 8000 closed from outside, hourly backup, restore from a backup and from a Modal-style folder,
`update.sh` with a good update and with a broken one (rolled back by itself). Backup uploads tested against both an
Azure-style (SAS) and an Oracle-style link. Not testable off a real server: the DuckDNS update and the Let's Encrypt
certificate (step 4 shows ✅ or ❌ for both).
