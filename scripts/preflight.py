"""Is the live server ready for traders? One line per thing the pilot needs: PASS, WARN (look at it) or FAIL (fix it
first). Run it the evening before and each morning of the pilot.

    python scripts/preflight.py
On the live server: sudo bash /opt/tradevoice/app/deploy/server/preflight.sh

It talks to every service the app uses, with the smallest possible request (one short AI answer, one word of voice,
one hearing session opened and closed). It never prints a key or a token: only whether it is set and whether it
works, and any error text has the keys masked. Safe to paste the output to anyone helping.
"""
import argparse
import asyncio
import concurrent.futures as cf
import datetime as dt
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import settings  # noqa: E402,F401  (loads .env)

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
SECRET_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def scrub(text):
    """Error text with every key and token masked (a library error can quote a header or a URL)."""
    text = str(text or "")
    for name, value in os.environ.items():
        if value and len(value) >= 6 and any(w in name.upper() for w in SECRET_WORDS):
            text = text.replace(value, "***")
    return text[:160]


def plain(text):
    """A library's connection error, in words."""
    t = str(text)
    if any(w in t for w in ("Connection refused", "Connect call failed", "Max retries exceeded", "Name or service not known",
                            "Temporary failure in name resolution", "Connection error")):
        return "can't connect: nothing answers at that address (is it running, is the link right, is there internet?)"
    if "timed out" in t.lower() or "Timeout" in t:
        return "no answer in time"
    return t


def _secs(t0):
    return f"{time.perf_counter() - t0:.1f} s"


# ---------------------------------------------------------------- the checks (each returns (status, detail))

def app_local():
    import requests
    port = os.getenv("PORT", "8000")
    try:
        r = requests.get(f"http://127.0.0.1:{port}/api/status", timeout=5)
    except requests.RequestException:
        return FAIL, f"nothing answers on port {port}: sudo systemctl restart tradevoice, then sudo journalctl -u tradevoice -n 50"
    if r.status_code != 200:
        return FAIL, f"HTTP {r.status_code}: sudo systemctl restart tradevoice, then sudo journalctl -u tradevoice -n 50"
    s = r.json()
    return PASS, f"brain {s.get('brain')}, hearing {s.get('hearing')}, voice {s.get('voice')}, photos {s.get('photos')}"


def app_public():
    import requests
    url = os.getenv("PUBLIC_URL", "").rstrip("/")
    if not url:
        return WARN, "PUBLIC_URL is not set (links in WhatsApp messages need it)"
    t0 = time.perf_counter()
    r = requests.get(url + "/api/status", timeout=15)
    return (PASS, f"{url} answers in {_secs(t0)}") if r.status_code == 200 else (FAIL, f"{url}: HTTP {r.status_code}")


def natlas_brain():
    if not os.getenv("NATLAS_URL"):
        return FAIL, "NATLAS_URL is not set: N-ATLaS is the main model (keys.sh NATLAS_URL)"
    import llm
    t0 = time.perf_counter()
    text, used = llm.chat([{"role": "user", "content": "Reply with the single word OK."}], models=["natlas"],
                          max_tokens=5, timeout=240, deadline=240, long=True)
    took = time.perf_counter() - t0
    if used != "natlas" or not text:
        return FAIL, "N-ATLaS did not answer in 4 minutes: check the Modal app (modal app list) and NATLAS_KEY"
    if took > 20:
        return WARN, f"answered, but took {took:.0f} s: it was asleep. Turn NATLAS_WATCH=1 on for the pilot days"
    return PASS, f"answered in {took:.1f} s"


def natlas_hearing():
    if not os.getenv("NATLAS_ASR_URL"):
        return WARN, "NATLAS_ASR_URL is not set: voice notes are heard by the backups only"
    import requests
    t0 = time.perf_counter()
    r = requests.get(os.environ["NATLAS_ASR_URL"].rstrip("/") + "/health", timeout=240,
                     headers={"Authorization": f"Bearer {os.getenv('NATLAS_KEY', 'none')}"})
    if r.status_code != 200:
        return FAIL, f"HTTP {r.status_code}"
    return (WARN, f"up, but took {time.perf_counter() - t0:.0f} s to wake") if time.perf_counter() - t0 > 20 \
        else (PASS, f"up ({_secs(t0)})")


def nvidia():
    if not os.getenv("NVIDIA_API_KEY"):
        return FAIL, "NVIDIA_API_KEY is not set: the Ask chat's main model and photo reading need it (keys.sh)"
    import llm
    first = next((m for m in llm.LLM_MODELS if m not in ("natlas", "local")), None)
    if not first:
        return WARN, "no NVIDIA model in LLM_MODELS"
    t0 = time.perf_counter()
    text, used = llm.chat([{"role": "user", "content": "Reply with the single word OK."}], models=[first],
                          max_tokens=20, timeout=60, deadline=60)
    return (PASS, f"{used} answered in {_secs(t0)}") if text else (FAIL, f"{first} did not answer: key or credit?")


def intron_voice():
    if not os.getenv("INTRON_API_KEY"):
        return FAIL, "INTRON_API_KEY is not set: no spoken replies (keys.sh INTRON_API_KEY)"
    import tts
    t0 = time.perf_counter()
    out = tts.speak("Hello.", "English")
    if out:
        try:
            os.remove(out["path"])
        except OSError:
            pass
    if out and out["engine"].startswith("intron"):
        return PASS, f"made a voice reply in {_secs(t0)}"
    return FAIL, scrub(plain(tts.why_not_intron() or "Intron gave no audio"))


def intron_hearing():
    import intron_live
    if not os.getenv("INTRON_API_KEY"):
        return FAIL, "INTRON_API_KEY is not set: live talk can't hear"
    ws_lib = intron_live._websockets()
    if not ws_lib:
        return FAIL, "the websockets package is missing: sudo bash .../update.sh installs it"

    async def probe():
        url = f"{intron_live.STT_WS}?sample_rate=16000&bit_rate=16&num_channels=1&use_language_asr_input=pcm"
        async with ws_lib.connect(url, additional_headers=intron_live._head(), open_timeout=10) as ws:
            return json.loads(await asyncio.wait_for(ws.recv(), 10))
    t0 = time.perf_counter()
    first = asyncio.run(probe())
    if first.get("message_type") == "SESSION_CREATED":
        credit = first.get("credit_balance", first.get("credits_balance"))
        return PASS, f"live hearing opens in {_secs(t0)}" + (f", credit left: {credit}" if credit is not None else "")
    return FAIL, scrub(first.get("message") or first.get("message_type")) + " (top up the Intron credit?)"


def whatsapp():
    tok, pid = os.getenv("WHATSAPP_TOKEN"), os.getenv("WHATSAPP_PHONE_ID") or os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not (tok and pid):
        return FAIL, "WHATSAPP_TOKEN or WHATSAPP_PHONE_ID is not set: the bot can't send"
    import requests

    import whatsapp as wa
    r = requests.get(f"{wa.GRAPH}/{pid}", params={"fields": "display_phone_number,verified_name,name_status,quality_rating"},
                     headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    if r.status_code == 401 or "expired" in r.text.lower():
        return FAIL, "the token has expired: make a permanent (System User) token in Meta, then keys.sh WHATSAPP_TOKEN"
    if r.status_code != 200:
        return FAIL, scrub(f"Meta said HTTP {r.status_code}: {r.text}")
    d = r.json()
    detail = (f"{d.get('display_phone_number', '?')} ({d.get('verified_name', '?')}), name {d.get('name_status', '?')}, "
              f"quality {d.get('quality_rating', '?')}")
    a, b = os.getenv("WHATSAPP_PHONE_ID"), os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if a and b and a != b:
        return FAIL, "WHATSAPP_PHONE_ID and WHATSAPP_PHONE_NUMBER_ID differ (PHONE_ID wins): remove the old one in .env"
    if not os.getenv("WHATSAPP_APP_SECRET"):
        return FAIL, detail + ("; WHATSAPP_APP_SECRET not set: anyone could post fake messages into a trader's book, "
                               "and LOGIN by message is off (keys.sh WHATSAPP_APP_SECRET, from Meta app > Basic)")
    if not os.getenv("WHATSAPP_VERIFY_TOKEN"):
        return WARN, detail + "; WHATSAPP_VERIFY_TOKEN not set (Meta can't re-check the webhook)"
    if "test" in str(d.get("verified_name", "")).lower():
        return WARN, detail + ": a Meta test number reaches only 5 phones"
    import whatsapp as wa2
    tpl = [k for k, env in wa2.TEMPLATES.items() if os.getenv(env)]
    if "code" not in tpl:
        return WARN, detail + ("; no login-code template yet: codes reach only traders who wrote in 24 h, the rest tap "
                               "'Send it on WhatsApp' (whatsapp_templates.sh --print)")
    return PASS, detail + f"; templates: {', '.join(tpl)}"


def settings_needed():
    out, need = [], {"ADMIN_TOKEN": "the team dashboard", "PRIVACY_CONTACT": "the privacy notice's contact",
                     "PUBLIC_URL": "links in messages"}
    missing = [f"{k} ({why})" for k, why in need.items() if not os.getenv(k)]
    team = [n for n in os.getenv("TEAM_PHONES", "").split(",") if n.strip()]
    if not team:
        out.append("TEAM_PHONES is empty, so the team's own testing counts as traders in the NAIC numbers")
    if missing:
        return FAIL, "not set: " + "; ".join(missing)
    if out:
        return WARN, out[0]
    return PASS, f"dashboard, privacy contact and links set; {len(team)} team phone(s) left out of the numbers"


def keep_awake():
    if os.getenv("NATLAS_WATCH", "1") != "1":
        return WARN, "NATLAS_WATCH is off: N-ATLaS sleeps after an hour and the first trader waits 1-3 minutes"
    hours = os.getenv("NATLAS_WATCH_HOURS", "7-20")
    alerts = "alerts go to TEAM_WHATSAPP" if os.getenv("TEAM_WHATSAPP") else "no TEAM_WHATSAPP for alerts"
    return (PASS if os.getenv("TEAM_WHATSAPP") else WARN), f"N-ATLaS kept awake {hours}h Lagos time; {alerts}"


def backups():
    import backup
    p = backup.paths()
    off = [n for n in ("BACKUP_SUPABASE_URL", "BACKUP_UPLOAD_URL", "BACKUP_COPY_DIR") if os.getenv(n)]
    names = sorted(f for f in (os.listdir(p["backups"]) if os.path.isdir(p["backups"]) else []) if backup.NAME_RE.match(f))
    if not names:
        return FAIL, "no backup yet: sudo systemctl start tradevoice-backup"
    newest = dt.datetime.strptime(backup.NAME_RE.match(names[-1]).group(1), "%Y%m%d-%H%M%S")
    age_h = (dt.datetime.now() - newest).total_seconds() / 3600
    where = f"also copied to {', '.join(n.replace('BACKUP_', '').replace('_URL', '').lower() for n in off)}" if off else ""
    if age_h > 2:
        return FAIL, f"the newest backup is {age_h:.0f} hours old: sudo journalctl -u tradevoice-backup -n 20"
    if not off:
        return FAIL, (f"last backup {age_h * 60:.0f} min ago, but only on this server: if it dies every book is lost. "
                      "Set BACKUP_SUPABASE_URL and BACKUP_SUPABASE_KEY (keys.sh)")
    return PASS, f"last backup {age_h * 60:.0f} min ago, {len(names)} kept, {where}"


def disk():
    import ledger
    d = os.path.dirname(os.path.abspath(ledger.BOOKS_DIR))
    free = shutil.disk_usage(d if os.path.isdir(d) else ROOT).free / 1e9
    if free < 2:
        return FAIL, f"{free:.1f} GB free: the app will stop saving. Delete old files or grow the disk"
    return (WARN if free < 5 else PASS), f"{free:.1f} GB free"


def tools():
    missing = [t for t in ("ffmpeg",) if not shutil.which(t)]
    if missing:
        return FAIL, "missing: " + ", ".join(missing) + " (sudo apt-get install -y ffmpeg): WhatsApp voice replies need it"
    import training
    d = training._dir()
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
        probe = os.path.join(d, ".write-check")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        return FAIL, f"can't write the 'help improve' folder {d}: {scrub(e)}"
    return PASS, "ffmpeg there; the 'help improve' folder is writable"


CHECKS = [("App answering", app_local), ("Public link", app_public), ("N-ATLaS brain", natlas_brain),
          ("N-ATLaS hearing", natlas_hearing), ("NVIDIA models", nvidia), ("Intron voice replies", intron_voice),
          ("Intron live hearing", intron_hearing), ("WhatsApp bot", whatsapp), ("Settings", settings_needed),
          ("Keep N-ATLaS awake", keep_awake), ("Backups", backups), ("Disk space", disk), ("Tools and folders", tools)]


def run(checks=CHECKS, timeout=300):
    """[(name, status, detail)] in the order given; the network checks run side by side."""
    def one(fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            return FAIL, scrub(plain(f"{type(e).__name__}: {e}"))
    with cf.ThreadPoolExecutor(max_workers=len(checks)) as pool:
        futures = [(name, pool.submit(one, fn)) for name, fn in checks]
        out = []
        for name, f in futures:
            try:
                status, detail = f.result(timeout=timeout)
            except cf.TimeoutError:
                status, detail = FAIL, f"no answer in {timeout} s"
            out.append((name, status, scrub(detail)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", help="comma-separated check names (e.g. 'Backups,Disk space')")
    a = ap.parse_args(argv)
    checks = [c for c in CHECKS if not a.only or c[0].lower() in {x.strip().lower() for x in a.only.split(",")}]
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=1))).strftime("%d %b %Y %H:%M")
    print(f"TradeVoice pilot check, {now} Lagos time\n")
    rows = run(checks)
    width = max(len(n) for n, _, _ in rows)
    for name, status, detail in rows:
        print(f"{status}  {name.ljust(width)}  {detail}")
    fails, warns = sum(s == FAIL for _, s, _ in rows), sum(s == WARN for _, s, _ in rows)
    print("\n" + ("Ready for traders." if not fails and not warns else
                  f"{fails} to fix first (FAIL), {warns} to look at (WARN)." if fails else
                  f"Ready, with {warns} to look at (WARN)."))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
