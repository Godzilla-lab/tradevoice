"""Sign-up and log-in codes by a phone call or SMS, for traders without WhatsApp or Telegram.

Termii (termii.com, Lagos). The account is free; each code is paid from the Termii wallet (fund it on the dashboard;
the rates are on the dashboard). The app makes its own 6-digit code and checks it itself (src/v2.py): Termii only
delivers it.
- voice (what the live server uses: no TERMII_SENDER_ID set): a phone call, and a voice reads the code out (Termii's
  voice call API). No sender ID to get approved, no DND problem: it works as soon as the wallet has money.
- dnd (when TERMII_SENDER_ID is set): a text message from that sender ID on Termii's transactional route. It reaches
  numbers on DND and arrives at any hour. Needs a sender ID approved by Termii (Termii's team reviews it and may ask
  for business papers) and the DND route switched on for the account by Termii support.
TERMII_CHANNEL (voice | dnd | generic) overrides that choice.
- generic: Termii's promotional route. Not for codes (Termii's own rule): it skips numbers on DND, MTN blocks it from
  8pm to 8am, and sender IDs that send codes on it get blocked. Only for a quick test.
When a code can't go (wallet empty, sender ID not approved yet), sign-up carries on with number + password and the
reason shows on /team (src/v2.py; SIGNUP_CODE=required stops that). TERMII_CALL_BACKUP=1: a text that can't go
becomes a call.

Settings (keys.sh): TERMII_API_KEY (secret), TERMII_BASE_URL (the account's own link, on the dashboard; default
https://v4.api.termii.com), TERMII_SENDER_ID (only for texts), SMS_DAILY_MAX (default 50 a day: a cap on what the
wallet can spend; past it, no more codes that day). On top of that, src/v2.py allows 5 codes an hour per number and 20
per connection. The phone number and the code are never logged.
"""
import datetime as dt
import os
import threading

import requests

STATS = {"sent": 0, "failed": 0, "last_error": None}
_lock = threading.Lock()
CHANNELS = ("dnd", "voice", "generic")


def base():
    url = (os.getenv("TERMII_BASE_URL") or "https://v4.api.termii.com").strip().rstrip("/")
    return url if url.startswith("http") else "https://" + url


def channel():
    """voice (a phone call) unless a sender ID is set for texts; TERMII_CHANNEL overrides."""
    c = (os.getenv("TERMII_CHANNEL") or ("dnd" if sender() else "voice")).strip().lower()
    return c if c in CHANNELS else "voice"


def sender():
    return (os.getenv("TERMII_SENDER_ID") or "").strip()


def provider():
    return "termii" if os.getenv("TERMII_API_KEY") and (sender() or channel() == "voice") else ""


def by_call():
    return ready() and channel() == "voice"


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
    """Count one text or call against today's cap. False when the day's are used up."""
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
        events.log(kind, None, "sms", engine=engine, ok=ok)   # no phone, no code: only that a code went or failed
    except Exception:  # noqa: BLE001
        pass


def _fail(why):
    STATS["failed"] += 1
    STATS["last_error"] = why
    _event("sms_failed", False, why)
    print(f"code not sent by SMS: {why}")
    return ""


def _why(status, body):
    """Termii's answer in plain words (never the key, never the number)."""
    said = str((body or {}).get("message") or (body or {}).get("error") or "").lower() if isinstance(body, dict) else ""
    if "sender" in said:
        return "the sender ID is not approved yet (or is misspelt)"
    if "balance" in said:
        return "the Termii wallet is empty"
    if "route" in said:
        return "this route is not switched on for the account (ask Termii support)"
    if "not active" in said:
        return "the Termii account is not active"
    return {401: "the Termii key was refused (or TERMII_BASE_URL is not this account's link)",
            403: "the Termii key may not do this", 404: "TERMII_BASE_URL is wrong",
            429: "too many requests to Termii"}.get(status, f"Termii said {status}")


def _post(path, body):
    """-> (ok, why)."""
    try:
        r = requests.post(base() + path, json={"api_key": os.environ["TERMII_API_KEY"], **body}, timeout=20)
    except requests.RequestException as e:
        return False, f"Termii not reachable ({type(e).__name__})"
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        return False, _why(r.status_code, data)
    if isinstance(data, dict) and str(data.get("code", "ok")).lower() not in ("ok", "200"):
        return False, _why(r.status_code, data)
    return True, ""


def send_code(phone, code):
    """The code to `phone` (234...): a text, or a call when that is the channel or the text can't go.
    Returns how it went ("sms" or "call"), or "" when nothing went."""
    if not ready():
        return ""
    import accounts
    to = phone.lstrip("+")
    if channel() != "voice":
        if not _take_one():
            return _fail("daily limit reached")
        ok, why = _post("/api/sms/send", {
            "to": to, "from": sender(), "type": "plain", "channel": channel(),
            "sms": f"TradeVoice code: {code}. It expires in {accounts.CODE_MINUTES} minutes. Don't share it with anyone."})
        if ok:
            STATS["sent"] += 1
            _event("sms_sent", True, "termii:" + channel())
            return "sms"
        _fail(why)
        if os.getenv("TERMII_CALL_BACKUP", "0") != "1" or why.startswith(("Termii not reachable", "the Termii key",
                                                                          "the Termii wallet", "TERMII_BASE_URL")):
            return ""   # a call would fail the same way
    if not _take_one():
        return _fail("daily limit reached")
    ok, why = _post("/api/sms/otp/call", {"phone_number": to, "code": int(code) if code[:1] != "0" else code})
    if ok:
        STATS["sent"] += 1
        _event("sms_sent", True, "termii:call")
        return "call"
    return _fail(why)


def check():
    """For the pilot check: (ok, words); ok None = works, but not as meant yet (sender ID waiting for approval).
    The wallet and, for texts, whether the sender ID is approved. Never the key."""
    if not ready():
        return False, "not set up"
    key = os.environ["TERMII_API_KEY"]
    try:
        r = requests.get(base() + "/api/get-balance", params={"api_key": key}, timeout=15)
    except requests.RequestException as e:
        return False, f"Termii not reachable ({type(e).__name__})"
    if r.status_code >= 400:
        return False, _why(r.status_code, {})
    try:
        b = r.json()
        money = float(b.get("balance") or 0)
        wallet = f"wallet {b.get('currency') or 'NGN'} {money:,.2f}"
    except (ValueError, TypeError, AttributeError):
        money, wallet = 0.0, "wallet unknown"
    used = f"{sent_today()} of {daily_max()} codes used today"
    if money <= 0:
        return False, f"{wallet}: fund the Termii wallet, no code can go out; {used}"
    if channel() == "voice":
        return True, f"codes go by phone call (no sender ID needed); {wallet}; {used}"
    try:
        s = requests.get(base() + "/api/sender-id", params={"api_key": key, "name": sender()}, timeout=15)
        rows = s.json().get("content") or [] if s.status_code < 400 else []
    except (requests.RequestException, ValueError, AttributeError):
        rows = []
    state = next((str(x.get("status", "")).lower() for x in rows if str(x.get("sender_id", "")).lower()
                  == sender().lower()), "not found")
    calls = os.getenv("TERMII_CALL_BACKUP", "0") == "1"
    if state == "active":
        return True, f"texts from {sender()} on the {channel()} route; {wallet}; {used}"
    note = f"sender ID {sender()} is {state}"
    if calls:
        return None, f"{note}: codes go by phone call until Termii approves it; {wallet}; {used}"
    return None, (f"{note}: no text can go out yet, so sign-up goes on with number + password until Termii approves "
                  f"it; {wallet}")
