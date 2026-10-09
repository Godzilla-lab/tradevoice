"""TradeVoice on Telegram (Bot API): the same bot as WhatsApp, for traders who use Telegram. Free, no business
verification, no 24-hour window. The web app stays the main way in; most traders don't use Telegram.

- A book belongs to a phone number. The first time someone writes, the bot asks them to tap "Share my phone number"
  (Telegram's own contact button). Only their own contact is accepted (contact.user_id == the sender), so the number
  is checked by Telegram, for free. tg_link (accounts.db) remembers Telegram user -> phone; from then on their
  messages use that phone's book, the same book as the web app.
- Everything else is the WhatsApp bot's own code (whatsapp.handle): each update becomes the message shape it knows,
  and its replies come back here (whatsapp.OUT switches where they are sent).
- The webhook is checked with Telegram's secret header (made from the token); the app registers it by itself at
  start when TELEGRAM_BOT_TOKEN is set.
"""
import hashlib
import os
import threading

import requests

API = "https://api.telegram.org"
_ME = {}             # getMe, once: {"username": ...}
_lock = threading.Lock()


def token():
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def ready():
    return bool(token())


def secret():
    """The webhook's secret header: made from the token, so there is nothing else to set (A-Z a-z 0-9 _ - only)."""
    return hashlib.sha256(("tv-telegram:" + token()).encode()).hexdigest()[:48] if token() else ""


def call(method, payload=None, files=None, timeout=30):
    """One Bot API call -> its result. Raises RuntimeError with Telegram's own words when it refuses."""
    url = f"{API}/bot{token()}/{method}"
    r = requests.post(url, data=payload, files=files, timeout=timeout) if files else \
        requests.post(url, json=payload or {}, timeout=timeout)
    try:
        d = r.json()
    except ValueError:
        d = {}
    if not d.get("ok"):
        raise RuntimeError(f"Telegram {method}: {d.get('description') or r.status_code}")
    return d.get("result")


def username():
    """The bot's @name (for t.me links), from TELEGRAM_BOT_USERNAME or asked once from Telegram."""
    if not ready():
        return ""
    if os.getenv("TELEGRAM_BOT_USERNAME"):
        return os.getenv("TELEGRAM_BOT_USERNAME").lstrip("@")
    if "username" not in _ME:
        try:
            _ME["username"] = call("getMe", timeout=10).get("username", "")
        except Exception as e:  # noqa: BLE001
            print(f"telegram getMe failed: {e}")
            return ""
    return _ME["username"]


# ---------------------------------------------------------------- who is who: Telegram user <-> phone

def _db():
    import accounts
    c = accounts.db()
    c.execute("CREATE TABLE IF NOT EXISTS tg_link (tg_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, phone TEXT NOT NULL,"
              " at TEXT NOT NULL)")
    return c


def link(tg_id, chat_id, phone):
    import datetime as dt
    with _lock, _db() as c:
        c.execute("DELETE FROM tg_link WHERE phone=? AND tg_id<>?", (phone, str(tg_id)))   # one Telegram per number
        c.execute("INSERT INTO tg_link (tg_id, chat_id, phone, at) VALUES (?,?,?,?) ON CONFLICT(tg_id) DO UPDATE SET "
                  "chat_id=excluded.chat_id, phone=excluded.phone, at=excluded.at",
                  (str(tg_id), str(chat_id), phone, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))


def phone_of(tg_id):
    with _db() as c:
        r = c.execute("SELECT phone FROM tg_link WHERE tg_id=?", (str(tg_id),)).fetchone()
    return r[0] if r else None


def chat_of(phone):
    """The Telegram chat of a trader who shared their number with the bot, or None."""
    if not ready() or not phone:
        return None
    with _db() as c:
        r = c.execute("SELECT chat_id FROM tg_link WHERE phone=?", (phone,)).fetchone()
    return r[0] if r else None


def unlink(phone):
    with _lock, _db() as c:
        c.execute("DELETE FROM tg_link WHERE phone=?", (phone,))


def send_code(phone, code):
    """A log-in or password-reset code to the trader's own Telegram (only numbers they shared with the bot)."""
    chat = chat_of(phone)
    if not chat:
        return False
    try:
        call("sendMessage", {"chat_id": chat, "parse_mode": "HTML",
                             "text": f"Your TradeVoice code is <b>{code}</b>. Don't share it with anyone."})
        return True
    except Exception as e:  # noqa: BLE001
        print(f"code not sent by Telegram: {e}")
        return False
