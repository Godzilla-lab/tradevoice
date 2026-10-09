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
import hmac
import html
import os
import re
import threading
import time
from collections import OrderedDict

import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

router = APIRouter()

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


# ---------------------------------------------------------------- talking: the WhatsApp bot's replies, sent here

def as_html(text):
    """WhatsApp's *bold* / _italic_ / ~strike~ -> Telegram HTML, with everything else escaped. No emojis."""
    from plain import no_emoji
    t = html.escape(no_emoji(text or ""), quote=False)
    for mark, tag in (("*", "b"), ("_", "i"), ("~", "s")):
        m = re.escape(mark)
        t = re.sub(rf"(?<![\w{m}]){m}(?!\s)([^{m}\n]+?)(?<!\s){m}(?![\w{m}])", rf"<{tag}>\1</{tag}>", t)
    return t[:4096]


def _keys(rows):
    return {"inline_keyboard": [[{"text": t[:60], "callback_data": str(i)[:64]}] for i, t in rows]}


class Out:
    """Where whatsapp.handle's replies go while it answers a Telegram message (whatsapp.OUT points here)."""
    name = "telegram"

    def __init__(self, chat_id):
        self.chat = chat_id

    def send_text(self, to, body):
        return call("sendMessage", {"chat_id": self.chat, "text": as_html(body), "parse_mode": "HTML",
                                    "disable_web_page_preview": True})

    def send_buttons(self, to, body, buttons):
        return call("sendMessage", {"chat_id": self.chat, "text": as_html(body), "parse_mode": "HTML",
                                    "reply_markup": _keys([(i, t) for i, t in buttons[:3]])})

    def send_list(self, to, body, button, rows):
        items = [(r[0], f"{r[1]} · {r[2]}" if len(r) > 2 and r[2] else r[1]) for r in rows[:10]]
        return call("sendMessage", {"chat_id": self.chat, "text": as_html(body), "parse_mode": "HTML",
                                    "reply_markup": _keys(items)})

    def send_voice(self, to, text, lang):
        import whatsapp
        path = whatsapp.voice_file(text, lang)   # the same OGG/Opus voice note WhatsApp gets
        if not path:
            return None
        try:
            with open(path, "rb") as f:
                return call("sendVoice", {"chat_id": str(self.chat)}, files={"voice": ("reply.ogg", f, "audio/ogg")},
                            timeout=60)
        finally:
            os.remove(path)

    def mark_read(self, message_id):
        try:
            call("sendChatAction", {"chat_id": self.chat, "action": "typing"}, timeout=10)
        except Exception:  # noqa: BLE001
            pass

    def download(self, file_id, suffix):
        import tempfile

        import whatsapp
        meta = call("getFile", {"file_id": file_id})
        if int(meta.get("file_size") or 0) > whatsapp.MAX_MEDIA:
            raise whatsapp.TooBig()
        data = requests.get(f"{API}/file/bot{token()}/{meta['file_path']}", timeout=60)
        data.raise_for_status()
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data.content)
        return path


SHARE = {"keyboard": [[{"text": "Share my phone number", "request_contact": True}]], "resize_keyboard": True,
         "one_time_keyboard": True}
SAY = {
    "welcome": "Welcome to TradeVoice. To keep your book safe, tap <b>Share my phone number</b> below. Telegram sends "
               "the number on your account, the same number you use in the TradeVoice app, so it is one book.",
    "not_yours": "Please share your own number with the button below (not someone else's contact).",
    "bad_number": "That number doesn't look right. Please try the button again.",
    "linked": "Thank you. Your number is connected. To use the same book in the TradeVoice app on the web too, "
              "sign up there with this number: Telegram and the app share one book.",
    "confirmed": "Done, your number is confirmed. Go back to TradeVoice: it continues by itself.",
    "old_word": "That confirmation is old or not for this number. On the website, start again and tap Confirm on "
                "Telegram.",
}
SEEN = OrderedDict()   # update ids already handled (Telegram retries when we are slow)
PENDING = {}           # tg user -> a "LOGIN WORD" from the website, waiting for them to share their number


def _say(chat, text, markup=None):
    payload = {"chat_id": chat, "text": text, "parse_mode": "HTML"}
    if markup is not None:
        payload["reply_markup"] = markup
    return call("sendMessage", payload)


def _welcome(phone):
    """After the number is shared: a trader who already has the web app is welcomed back by name, and their language
    and the terms they agreed to at sign-up carry over (no second language question, no second "I agree")."""
    import html as _html

    import ledger
    import v2
    import whatsapp
    acct = v2._user(phone) if v2._has_account(phone) else None
    if not acct:
        return SAY["linked"]
    tok = ledger.use_book(phone)
    try:
        u = whatsapp.user(phone)
        if not u.get("lang"):
            whatsapp.set_user(phone, lang=acct.get("lang") or "English")
        if not u.get("consent_at"):
            whatsapp.set_user(phone, consent_at=acct.get("created_at") or "web sign-up")
    finally:
        ledger.done_with_book(tok)
    name = (acct.get("name") or "").split(" ")[0]
    shop = acct.get("shop") or ""
    return (f"Welcome back{', ' + _html.escape(name) if name else ''}. This is the same book as your TradeVoice app"
            f"{' (' + _html.escape(shop) + ')' if shop else ''}: what you save here shows there, and the other way round.")


def _confirm(chat, phone, word):
    import accounts
    ok = accounts.confirm_from_whatsapp(phone, f"LOGIN {word}")
    _say(chat, SAY["confirmed"] if ok else SAY["old_word"])


def _as_message(m, phone):
    """A Telegram message -> the WhatsApp-shaped message whatsapp.handle reads (type only decides the path)."""
    base = {"from": phone, "id": f"tg{m.get('message_id')}"}
    cap = (m.get("caption") or "").strip()
    if m.get("voice") or m.get("audio"):
        a = m.get("voice") or m.get("audio")
        return {**base, "type": "audio", "audio": {"id": a["file_id"]}}
    if m.get("photo"):
        best = max(m["photo"], key=lambda p: p.get("file_size") or p.get("width", 0))
        return {**base, "type": "image", "image": {"id": best["file_id"], "caption": cap}}
    doc = m.get("document")
    if doc and str(doc.get("mime_type", "")).startswith("image/"):
        return {**base, "type": "image", "image": {"id": doc["file_id"], "caption": cap}}
    if doc and str(doc.get("mime_type", "")).startswith("audio/"):
        return {**base, "type": "audio", "audio": {"id": doc["file_id"]}}
    if m.get("text"):
        return {**base, "type": "text", "text": {"body": m["text"]}}
    return {**base, "type": "sticker"}   # stickers, locations…: no answer (whatsapp.QUIET)


def handle_update(upd):
    """One update from Telegram: link the number if needed, then the WhatsApp bot answers, its replies sent here."""
    import accounts
    import events
    import whatsapp

    cq, m = upd.get("callback_query"), upd.get("message")
    if cq:   # a button under one of our messages
        try:
            call("answerCallbackQuery", {"callback_query_id": cq["id"]}, timeout=10)
        except Exception:  # noqa: BLE001
            pass
        chat, tg_id, msg_id = cq["message"]["chat"]["id"], cq["from"]["id"], cq["message"].get("message_id")
        try:   # the buttons go once pressed: a second tap can't save the same record twice
            call("editMessageReplyMarkup", {"chat_id": chat, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}},
                 timeout=10)
        except Exception:  # noqa: BLE001
            pass
        phone = phone_of(tg_id)
        if not phone:
            return _say(chat, SAY["welcome"], SHARE)
        msg = {"from": phone, "id": f"tgq{cq['id']}", "type": "interactive",
               "interactive": {"button_reply": {"id": cq.get("data", "")}}}
    elif m:
        chat, tg_id = m["chat"]["id"], m["from"]["id"]
        if m["chat"].get("type") != "private":
            return None   # the bot only talks one to one
        text = (m.get("text") or "").strip()
        if text == "/id":   # for the team: TEAM_TELEGRAM wants these chat ids
            return _say(chat, f"This chat's ID: <code>{chat}</code>")
        start = re.match(r"^/start(?:\s+(\S+))?$", text)
        if start and (start.group(1) or "").lower().startswith("login-"):
            PENDING[tg_id] = start.group(1)[6:].upper()   # "Confirm on Telegram" from the website
        if m.get("contact"):
            ct = m["contact"]
            if str(ct.get("user_id")) != str(tg_id):
                return _say(chat, SAY["not_yours"], SHARE)
            phone = accounts.normalize(ct.get("phone_number"))
            if not phone:
                return _say(chat, SAY["bad_number"], SHARE)
            link(tg_id, chat, phone)
            events.log("tg_linked", phone, "telegram")
            _say(chat, _welcome(phone), {"remove_keyboard": True})
            if tg_id in PENDING:
                return _confirm(chat, phone, PENDING.pop(tg_id))
            msg = {"from": phone, "id": f"tg{m.get('message_id')}", "type": "text", "text": {"body": "hi"}}
        else:
            phone = phone_of(tg_id)
            if not phone:
                return _say(chat, SAY["welcome"], SHARE)
            if tg_id in PENDING:
                return _confirm(chat, phone, PENDING.pop(tg_id))
            if start:
                m = {**m, "text": "hi"}   # /start: the bot greets them as for any first message
            msg = _as_message(m, phone)
    else:
        return None
    if whatsapp._flooding(phone):
        return None
    tok = whatsapp.OUT.set(Out(chat))
    try:
        whatsapp._safe(msg)   # the WhatsApp bot's own code: language, consent, records, voice, photos, questions
    finally:
        whatsapp.OUT.reset(tok)


def _safe_update(upd):
    try:
        handle_update(upd)
    except Exception as e:  # noqa: BLE001 - never crash the server on one bad update
        print(f"telegram update failed: {type(e).__name__}: {e}")


@router.post("/telegram/webhook")
async def incoming(request: Request, tasks: BackgroundTasks):
    if not ready() or not hmac.compare_digest(request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), secret()):
        raise HTTPException(401, "bad secret")
    upd = await request.json()
    uid = upd.get("update_id")
    if uid in SEEN:
        return {"ok": True}
    SEEN[uid] = True
    while len(SEEN) > 2000:
        SEEN.popitem(last=False)
    tasks.add_task(_safe_update, upd)   # answer Telegram at once; do the slow work after
    return {"ok": True}


def setup():
    """At start: point Telegram at our webhook (PUBLIC_URL), with the secret header; and the commands menu."""
    if not ready():
        return False
    base = os.getenv("PUBLIC_URL", "").rstrip("/")
    if not base.startswith("https://"):
        print("telegram: PUBLIC_URL must be https:// for the webhook; not set up")
        return False
    for attempt in range(3):
        try:
            call("setWebhook", {"url": f"{base}/telegram/webhook", "secret_token": secret(),
                                "allowed_updates": ["message", "callback_query"]})
            try:   # the menu button opens the TradeVoice app inside Telegram (log in once, the same book)
                call("setChatMenuButton", {"menu_button": {"type": "web_app", "text": "Open my book",
                                                           "web_app": {"url": f"{base}/app"}}})
            except Exception as e:  # noqa: BLE001
                print(f"telegram: menu button not set ({e})")
            username()
            print(f"telegram: webhook set for @{username()}")
            return True
        except Exception as e:  # noqa: BLE001
            print(f"telegram: webhook not set ({e}); trying again")
            time.sleep(5 * (attempt + 1))
    return False


def tell(phone, text):
    """A message we send first (daily summary, paid notice) to a trader linked on Telegram. True if sent."""
    chat = chat_of(phone)
    if not chat:
        return False
    try:
        Out(chat).send_text(phone, text)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"telegram message not sent: {e}")
        return False


def tell_team(text):
    """Team alerts to the chat ids in TEAM_TELEGRAM (send /id to the bot to get yours)."""
    for chat in filter(None, (c.strip() for c in os.getenv("TEAM_TELEGRAM", "").split(","))):
        try:
            Out(chat).send_text("", text)
        except Exception as e:  # noqa: BLE001
            print(f"team alert to Telegram failed: {e}")
