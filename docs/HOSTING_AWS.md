# ☁️ TradeVoice live on AWS (free plan credits + DuckDNS)

One small AWS server runs the app, the WhatsApp and Paystack webhooks, every trader's book and the accounts, at a free
fixed address **https://NAME.duckdns.org**. N-ATLaS and the speech models stay on Modal. Same scripts as the Oracle
guide ([`HOSTING.md`](HOSTING.md)); only the console steps differ.

**What it costs:** new AWS accounts (since 15 Jul 2025) on the **Free plan** get $100 of credit (up to $100 more for
AWS's getting-started tasks) for **6 months**. This server uses about $13–14 a month of it (t3.micro ≈ $8, public IPv4
≈ $3.65, 20 GB disk ≈ $1.80): the credit covers the 6 months. Before they end: upgrade to the paid plan (then it's
about $14 a month) or move the books to Oracle (one backup + one restore).

## 1. Account safety (5 minutes, once)
- Check **Billing → Credits** shows the free-plan credit.
- **Billing → Budgets → Create budget → Use a template → Zero spend budget**, alert to the team email: you hear at once if
  anything is ever charged beyond the credit.
- Top right → Security credentials → turn on **MFA** for the root user (the phone authenticator app).

## 2. The server
Console → choose the region at the top right: **Europe (Ireland) eu-west-1** (or London eu-west-2; both are close to
Nigeria and fully available). Then **EC2 → Launch instance**:
- Name `tradevoice`. Image: **Ubuntu Server 24.04 LTS**, 64-bit (x86).
- Instance type: **t3.micro** (marked "Free tier eligible").
- Key pair: **Create new key pair** → name `tradevoice-key`, type RSA, format `.pem` → it downloads. Keep it safe and
  private (it opens the server).
- Network settings → Edit: **Allow SSH from My IP**, **Allow HTTPS from the internet**, **Allow HTTP from the
  internet** (HTTP is needed once for the certificate, then it redirects to HTTPS).
- Storage: **20 GiB gp3**.
- **Launch instance** → open it → copy the **Public IPv4 address**.

## 3. DuckDNS (free address)
**duckdns.org** → sign in (Google or GitHub) → type a name (e.g. `tradevoice`) → **add domain**. Copy the **token**. The
server sets the IP itself (also after a stop/start, when AWS gives it a new one) and checks every 5 minutes.

## 4. Install (one command on the server)
On the Mac (Terminal):
```bash
chmod 400 ~/Downloads/tradevoice-key.pem
ssh -i ~/Downloads/tradevoice-key.pem ubuntu@PUBLIC_IP
```
On the server:
```bash
sudo git clone https://github.com/Godzilla-lab/tradevoice /opt/tradevoice/app
sudo bash /opt/tradevoice/app/deploy/server/setup.sh
```
It asks for the DuckDNS name and token (the token doesn't show while you paste it), installs everything, starts the app
and prints the links. "https … ✅" = the certificate is in place. A ❌ there: check the instance's security group allows
80 and 443 from anywhere (EC2 → the instance → Security), wait 5 minutes, run the same command again.

## 5. Keys, backups, books, webhooks
Same as the Oracle guide: **keys** ([`HOSTING.md`](HOSTING.md) step 6), **moving the books** from Modal or the Mac
(step 8), **webhooks** (step 9), and the **every day** commands.
For the **copy off the server**, use Supabase Storage (free, no card, a different company from AWS):
[`HOSTING_MAC.md`](HOSTING_MAC.md) step 5 (the same two lines go in the server's `.env`), then
`sudo systemctl start tradevoice-backup && sudo journalctl -u tradevoice-backup -n 5` → "copied to Supabase ✅".

## Notes
- Data location: the region you picked (Ireland or London). Say so in the privacy notice.
- Don't **stop** the instance to "save money": a stopped server is offline, and the credit is there to keep it on.
- If the account ever closes (6 months, no upgrade), AWS keeps the data only for a short time: keep the Supabase copy
  working and download a backup to a team computer every week.
