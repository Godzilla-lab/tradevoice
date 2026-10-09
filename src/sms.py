"""Sign-up and log-in codes by SMS, for traders without WhatsApp or Telegram.

TextBee (textbee.dev): a team Android phone with a team SIM sends the codes as ordinary texts. Free plan: 50 texts a
day, 300 a month; the SIM's own SMS bundle pays. No sender ID to register, so it works the day it is set up. The phone
must stay charged, on and online.

Settings (keys.sh): TEXTBEE_API_KEY (secret), TEXTBEE_DEVICE_ID, SMS_DAILY_MAX (default 50, the free plan's limit:
past it, no more codes that day, so the SIM and the plan are never overrun). On top of that, src/v2.py allows 5 codes
an hour per number and 20 per connection. The phone number and the code are never logged.
"""
import datetime as dt
import os
import threading

import requests

TEXTBEE = os.getenv("TEXTBEE_URL", "https://api.textbee.dev/api/v1")
STATS = {"sent": 0, "failed": 0, "last_error": None}
_lock = threading.Lock()


def provider():
    return "textbee" if os.getenv("TEXTBEE_API_KEY") and os.getenv("TEXTBEE_DEVICE_ID") else ""


def ready():
    return bool(provider())


def daily_max():
    try:
        return int(os.getenv("SMS_DAILY_MAX", "50"))
    except ValueError:
        return 50


def _db():
    import accounts
    c = accounts.db()
    c.execute("CREATE TABLE IF NOT EXISTS sms_days (day TEXT PRIMARY KEY, n INTEGER NOT NULL)")
    return c


def _today():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=1))).date().isoformat()   # Lagos day


def sent_today():
    with _db() as c:
        r = c.execute("SELECT n FROM sms_days WHERE day=?", (_today(),)).fetchone()
    return r[0] if r else 0


def _take_one():
    """Count one text against today's cap. False when the day's texts are used up."""
    with _lock, _db() as c:
        day = _today()
        r = c.execute("SELECT n FROM sms_days WHERE day=?", (day,)).fetchone()
        if (r[0] if r else 0) >= daily_max():
            return False
        c.execute("INSERT INTO sms_days (day, n) VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET n=n+1", (day,))
    return True


def _event(kind, ok, engine):
    try:
        import events
        events.log(kind, None, "sms", engine=engine, ok=ok)   # no phone, no code: only that a text went or failed
    except Exception:  # noqa: BLE001
        pass


def _fail(why):
    STATS["failed"] += 1
    STATS["last_error"] = why
    _event("sms_failed", False, why)
    print(f"code not sent by SMS: {why}")
    return False


def send(phone, text):
    """One text to `phone` (234...). True when the gateway took it."""
    if not ready():
        return False
    if not _take_one():
        return _fail("daily limit reached")
    try:
        r = requests.post(f"{TEXTBEE}/gateway/devices/{os.environ['TEXTBEE_DEVICE_ID']}/send-sms",
                          headers={"x-api-key": os.environ["TEXTBEE_API_KEY"]},
                          json={"recipients": ["+" + phone.lstrip("+")], "message": text}, timeout=20)
    except requests.RequestException as e:
        return _fail(f"gateway not reachable ({type(e).__name__})")
    if r.status_code >= 400:
        return _fail({401: "the TextBee key was refused", 403: "the TextBee key was refused",
                      404: "the phone (device) was not found on TextBee", 429: "TextBee's limit reached"}
                     .get(r.status_code, f"TextBee said {r.status_code}"))
    STATS["sent"] += 1
    _event("sms_sent", True, provider())
    return True


def send_code(phone, code):
    import accounts
    return send(phone, f"TradeVoice code: {code}. It expires in {accounts.CODE_MINUTES} minutes. "
                       "Don't share it with anyone.")


def check():
    """For the pilot check: (ok, words). Asks TextBee which phones are registered; never prints the key."""
    if not ready():
        return False, "not set up"
    try:
        r = requests.get(f"{TEXTBEE}/gateway/devices", headers={"x-api-key": os.environ["TEXTBEE_API_KEY"]}, timeout=15)
    except requests.RequestException as e:
        return False, f"TextBee not reachable ({type(e).__name__})"
    if r.status_code >= 400:
        return False, "TextBee refused the key" if r.status_code in (401, 403) else f"TextBee said {r.status_code}"
    try:
        devices = r.json().get("data") or []
    except ValueError:
        devices = []
    mine = [d for d in devices if str(d.get("_id") or d.get("id")) == os.environ["TEXTBEE_DEVICE_ID"]]
    if not mine:
        return False, "the phone (TEXTBEE_DEVICE_ID) is not on this TextBee account"
    on = mine[0].get("enabled", True)
    return bool(on), ("phone registered" + ("" if on else ", but switched off in the TextBee app")
                      + f"; {sent_today()} of {daily_max()} texts used today")
