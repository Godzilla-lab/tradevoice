"""TradeVoice on WhatsApp (Meta WhatsApp Cloud API). Mounted inside web.py, so it shares the server, the link and
the book: a voice note sent on WhatsApp shows up in the web app at once.

Webhook URL for Meta:  https://<our public link>/whatsapp/webhook
.env:  WHATSAPP_TOKEN, WHATSAPP_PHONE_ID, WHATSAPP_VERIFY_TOKEN (any word you choose, also typed into Meta),
       WHATSAPP_APP_SECRET (optional: checks that messages really come from Meta), PUBLIC_URL (for "dashboard").

Flow: first message -> pick language -> "I agree" (nothing is processed before that) -> then voice notes, texts and
notebook photos go through the same brain as the web chat (converse.py / photo.py); replies come as text + a voice
note in the trader's language, with ✅/❌ buttons when something is waiting to be saved.
Demo limits: one shared book for everyone (fine for the team's test phones); Meta's test number only talks to the
phones added in "API Setup".
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import subprocess
import tempfile
import threading
from collections import OrderedDict

import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

import converse
import ledger
import photo
import tts
import ui_text
from extract import fold, parse_amount

# the older setup notes called it WHATSAPP_PHONE_NUMBER_ID: accept both names
if not os.getenv("WHATSAPP_PHONE_ID") and os.getenv("WHATSAPP_PHONE_NUMBER_ID"):
    os.environ["WHATSAPP_PHONE_ID"] = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
GRAPH = f"https://graph.facebook.com/{os.getenv('WHATSAPP_GRAPH_VERSION', 'v23.0')}"
router = APIRouter()
STATES = {}                    # phone -> conversation state (same shape as the web chat's)
SEEN = OrderedDict()           # message ids already handled (Meta sometimes sends twice)
LOCKS = {}                     # phone -> lock, so one trader's messages are answered in order
VOICE_LANGS = {"English": "English / Pidgin", "Pidgin": "English / Pidgin", "Yoruba": "Yoruba", "Hausa": "Hausa",
               "Igbo": "Igbo"}
LANG_WORDS = {"english": "English", "pidgin": "Pidgin", "yoruba": "Yoruba", "hausa": "Hausa", "igbo": "Igbo",
              "yorùbá": "Yoruba"}

SAY = {
    "pick": "👋 Welcome to *TradeVoice*: your shop book on WhatsApp.\nWhich language do you want?",
    "photo_read": {"English": "📸 I read {n} lines:", "Pidgin": "📸 I read {n} lines:",
                   "Yoruba": "📸 Mo ka ìlà {n}:", "Hausa": "📸 Na karanta layi {n}:", "Igbo": "📸 Agụrụ m ahịrị {n}:"},
    "photo_help": "Tap ✅ to save the ticked ones. To fix one, reply like *3 = 40k*. To skip one, reply *no 3*.",
    "photo_none": "I couldn't find money records in this photo. Try a flat page, good light, the whole page in view.",
    "photo_saved": "✅ Saved {n} record{s} from your photo.",
    "photo_cancel": "OK, I didn't save anything from the photo.",
    "busy": "⏳ One moment…",
    "cant_hear": "😕 I couldn't hear that voice note. Try again closer to the phone, or type it.",
    "cant_read": "😕 I couldn't read that photo right now. Try again, or type the lines.",
    "voice_off": "🔇 OK, text only. Send *voice on* to hear me again.",
    "voice_on": "🔊 OK, I'll answer with voice notes too.",
    "lang_set": "✅ {lang}. Send a voice note in {lang}, or type in any language.",
    "dashboard": "📊 Your full book (charts, debts, statement): {url}",
    "other": "Send me a *voice note* 🎤, a *photo* of your book 📸, or type what happened.",
}


# ---------------------------------------------------------------- traders (the phone number is the account)

def _db():
    c = ledger.conn()
    c.execute("CREATE TABLE IF NOT EXISTS wa_users (phone TEXT PRIMARY KEY, lang TEXT, consent_at TEXT, "
              "voice INTEGER NOT NULL DEFAULT 1)")
    return c


def user(phone):
    with _db() as c:
        r = c.execute("SELECT * FROM wa_users WHERE phone=?", (phone,)).fetchone()
        if not r:
            c.execute("INSERT INTO wa_users (phone) VALUES (?)", (phone,))
            return {"phone": phone, "lang": None, "consent_at": None, "voice": 1}
        return dict(r)


def set_user(phone, **kw):
    with _db() as c:
        for k, v in kw.items():
            c.execute(f"UPDATE wa_users SET {k}=? WHERE phone=?", (v, phone))


# ---------------------------------------------------------------- Meta Graph API

def _headers():
    return {"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"}


def graph_post(payload):
    """Send one message. Returns Meta's answer (or raises on error, with Meta's message)."""
    r = requests.post(f"{GRAPH}/{os.environ['WHATSAPP_PHONE_ID']}/messages", headers=_headers(),
                      json={"messaging_product": "whatsapp", **payload}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"WhatsApp send failed {r.status_code}: {r.text[:300]}")
    return r.json()


def send_text(to, body):
    return graph_post({"to": to, "type": "text", "text": {"body": body[:4096], "preview_url": True}})


def send_buttons(to, body, buttons):
    """buttons: [(id, title≤20)] (max 3)."""
    return graph_post({"to": to, "type": "interactive", "interactive": {
        "type": "button", "body": {"text": body[:1024]},
        "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": t[:20]}} for i, t in buttons[:3]]}}})


def send_list(to, body, button, rows):
    """rows: [(id, title≤24)] or [(id, title, description≤72)] (max 10)."""
    items = []
    for row in rows[:10]:
        item = {"id": row[0], "title": row[1][:24]}
        if len(row) > 2 and row[2]:
            item["description"] = row[2][:72]
        items.append(item)
    return graph_post({"to": to, "type": "interactive", "interactive": {
        "type": "list", "body": {"text": body[:1024]},
        "action": {"button": button[:20], "sections": [{"title": "TradeVoice", "rows": items}]}}})


def send_voice(to, text, lang):
    """Speak `text` and send it as a WhatsApp voice note. Quietly does nothing if voice is off."""
    out = tts.speak(text, lang if lang in tts.REPLY_LANGS else "Pidgin", fmt="ogg_opus")
    if not out:
        return None
    path = out["path"]
    if not path.endswith(".ogg"):  # MMS gives wav: WhatsApp voice notes must be ogg/opus
        ogg = path.rsplit(".", 1)[0] + ".ogg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-c:a", "libopus", "-ac", "1", ogg],
                       check=True)
        os.remove(path)
        path = ogg
    try:
        with open(path, "rb") as f:
            r = requests.post(f"{GRAPH}/{os.environ['WHATSAPP_PHONE_ID']}/media", headers=_headers(),
                              data={"messaging_product": "whatsapp", "type": "audio/ogg"},
                              files={"file": ("reply.ogg", f, "audio/ogg")}, timeout=60)
        r.raise_for_status()
        return graph_post({"to": to, "type": "audio", "audio": {"id": r.json()["id"]}})
    finally:
        os.remove(path)


def mark_read(message_id):
    """Blue ticks + "typing…" while we work (best effort)."""
    try:
        graph_post({"status": "read", "message_id": message_id, "typing_indicator": {"type": "text"}})
    except Exception:  # noqa: BLE001
        pass


def download(media_id, suffix):
    """Media id -> our own temp file (deleted by the caller right after it is read)."""
    meta = requests.get(f"{GRAPH}/{media_id}", headers=_headers(), timeout=30)
    meta.raise_for_status()
    data = requests.get(meta.json()["url"], headers=_headers(), timeout=60)
    data.raise_for_status()
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data.content)
    return path


# ---------------------------------------------------------------- one incoming message -> replies

def _state(phone, lang):
    st = STATES.setdefault(phone, converse.new_state())
    st.setdefault("lang", lang or "Pidgin")
    if lang:
        st["prefer"] = lang  # their chosen language: replies use it unless they clearly speak another
    return st


def _reply(phone, r, u):
    """Send a converse reply: text (+ English line), the reminder to forward, a voice note, yes/no buttons."""
    body = r["text"] + (f"\n\n_🇬🇧 {r['english']}_" if r.get("english") else "")
    st = STATES.get(phone) or {}
    if r.get("choices"):  # "Which Feranmi?": each one with balance and last activity
        rows = []
        for n, (cid, label) in enumerate(r["choices"], 1):
            head, _, rest = label.partition(" · ")
            rows.append((cid, f"{n}. {head}"[:24], rest))
        send_list(phone, body, "Choose", rows)
    elif st.get("pending"):
        lang = r["lang"] if r["lang"] in ui_text.LANGS else "English"
        send_buttons(phone, body, [("yes", ui_text.t("yes_save", lang)), ("no", ui_text.t("no", lang))])
    else:
        send_text(phone, body)
    if r.get("message"):  # the reminder itself, as its own message: long-press → Forward to the customer
        send_text(phone, "👇 Forward this to them:")
        send_text(phone, r["message"])
    if u.get("voice"):
        try:
            send_voice(phone, r["spoken"], r["lang"])
        except Exception as e:  # noqa: BLE001 - voice is a bonus
            print(f"whatsapp voice failed: {type(e).__name__}: {e}")


def _photo_command(phone, text, st):
    """While photo lines are waiting: 'yes' saves, 'no' drops, '3 = 40k' fixes, 'no 3' skips. True if handled."""
    rows = st.get("photo_rows")
    if not rows:
        return False
    t = fold(text).strip()
    if converse.YES.match(t) or t in ("save", "p_save", "save all"):
        res = photo.save(rows)
        st["photo_rows"] = None
        n = res["saved"]
        send_text(phone, SAY["photo_saved"].format(n=n, s="" if n == 1 else "s")
                  + ("\n⚠️ " + "; ".join(res["problems"]) if res["problems"] else ""))
        return True
    if converse.NO.match(t) or t in ("cancel", "p_cancel"):
        st["photo_rows"] = None
        send_text(phone, SAY["photo_cancel"])
        return True
    m = re.match(r"^(?:no|skip|remove|not)\s*(\d+)$|^(\d+)\s*(?:no|skip|remove|x)$", t)
    if m:
        i = int(m.group(1) or m.group(2)) - 1
        if 0 <= i < len(rows):
            rows[i]["save"] = False
            _send_rows(phone, rows, st["lang"])
            return True
    m = re.match(r"^(\d+)\s*(?:=|is|na|:|->)?\s*(.+)$", t)
    if m and parse_amount(m.group(2)) is not None:
        i = int(m.group(1)) - 1
        if 0 <= i < len(rows):
            rows[i]["amount"], rows[i]["save"], rows[i]["checks"] = parse_amount(m.group(2)), True, []
            _send_rows(phone, rows, st["lang"])
            return True
    return False


def _send_rows(phone, rows, lang):
    head = SAY["photo_read"].get(lang, SAY["photo_read"]["English"]).format(n=len(rows))
    send_buttons(phone, f"{head}\n\n{photo.as_text(rows)}\n\n{SAY['photo_help']}",
                 [("p_save", "✅ Save ticked"), ("p_cancel", "❌ Cancel")])


def handle(msg):
    """Answer one incoming WhatsApp message (runs in the background, after Meta got its 200)."""
    phone, kind = msg["from"], msg.get("type")
    with LOCKS.setdefault(phone, threading.Lock()):
        u = user(phone)
        mark_read(msg.get("id"))
        text = ""
        if kind == "text":
            text = msg["text"]["body"].strip()
        elif kind == "interactive":
            it = msg["interactive"]
            text = (it.get("button_reply") or it.get("list_reply") or {}).get("id", "")
        elif kind == "button":
            text = msg.get("button", {}).get("payload") or msg.get("button", {}).get("text", "")

        # 1) sign-up: language, then consent (nothing is processed before "I agree")
        if text.startswith("lang:") or (u["lang"] and fold(text) in LANG_WORDS) or re.match(
                r"^(language|change language|lang)\b", fold(text)):
            lang = text.split(":", 1)[1] if text.startswith("lang:") else LANG_WORDS.get(fold(text))
            if not lang:
                return _ask_language(phone)
            set_user(phone, lang=lang)
            _state(phone, lang)["lang"] = lang
            if not u["consent_at"]:
                return send_buttons(phone, f"{ui_text.t('consent', lang)}",
                                    [("consent:yes", ui_text.t("agree", lang)[:20])])
            return send_text(phone, SAY["lang_set"].format(lang=lang))
        if not u["lang"]:
            return _ask_language(phone)
        if not u["consent_at"]:
            if text == "consent:yes" or converse.YES.match(fold(text)):
                set_user(phone, consent_at=dt.datetime.now().isoformat(timespec="seconds"))
                return send_text(phone, ui_text.t("hello", u["lang"]))
            return send_buttons(phone, ui_text.t("consent", u["lang"]),
                                [("consent:yes", ui_text.t("agree", u["lang"])[:20])])

        st = _state(phone, u["lang"])
        t = fold(text)
        # 2) settings
        if t in ("voice off", "text only", "no voice"):
            set_user(phone, voice=0)
            return send_text(phone, SAY["voice_off"])
        if t in ("voice on", "voice"):
            set_user(phone, voice=1)
            return send_text(phone, SAY["voice_on"])
        if t in ("dashboard", "web", "app", "book", "see more"):
            url = os.getenv("PUBLIC_URL", "").rstrip("/") + ("/app" if os.getenv("PUBLIC_URL") else "")
            return send_text(phone, SAY["dashboard"].format(url=url or "(ask the team for the link)"))

        # 3) photo of the notebook
        if kind == "image":
            send_text(phone, "📸 " + ui_text.t("reading_photo", u["lang"]))
            path = download(msg["image"]["id"], ".jpg")
            try:
                res = photo.read(path)
            except Exception as e:  # noqa: BLE001
                print(f"whatsapp photo failed: {type(e).__name__}: {e}")
                return send_text(phone, SAY["cant_read"])
            finally:
                os.remove(path)  # the photo is deleted as soon as it is read
            if not res["rows"]:
                return send_text(phone, SAY["photo_none"])
            st["photo_rows"] = res["rows"]
            return _send_rows(phone, res["rows"], st.get("lang", u["lang"]))

        # 4) voice note -> text (Intron, in the trader's language)
        if kind == "audio":
            path = download(msg["audio"]["id"], ".ogg")
            try:
                from asr import transcribe_auto

                heard = transcribe_auto(path, VOICE_LANGS.get(u["lang"], "English / Pidgin"), vocab=ledger.known_words())
                text = heard["text"].strip()
                new = {"English / Pidgin": None}.get(heard.get("detected"), heard.get("detected"))
                if new and new != u["lang"]:  # they spoke another of our languages: use it from now on
                    set_user(phone, lang=new)
                    u["lang"] = new
            except Exception as e:  # noqa: BLE001
                print(f"whatsapp voice-note failed: {type(e).__name__}: {e}")
                return send_text(phone, SAY["cant_hear"])
            finally:
                os.remove(path)  # the voice note is deleted as soon as it is read
            if not text:
                return send_text(phone, SAY["cant_hear"])
            send_text(phone, f"🎙️ _“{text}”_")

        if not text:
            return send_text(phone, SAY["other"])
        if _photo_command(phone, text, st):
            return None
        # 5) everything else: the same brain as the web chat (record / yes-no / question / reminder)
        _due_once(phone, st, u["lang"])
        r = converse.reply(text, st, shop=os.getenv("SHOP_NAME", "my shop"))
        if kind == "text" and r["lang"] in ("Yoruba", "Hausa", "Igbo") and r["lang"] != u["lang"]:
            set_user(phone, lang=r["lang"])  # they wrote in another of our languages: hear voice notes in it too
        return _reply(phone, r, u)


def _ask_language(phone):
    return send_list(phone, SAY["pick"], "Choose language",
                     [("lang:Pidgin", "Pidgin"), ("lang:English", "English"), ("lang:Yoruba", "Yorùbá"),
                      ("lang:Hausa", "Hausa"), ("lang:Igbo", "Igbo")])


def _due_once(phone, st, lang):
    """Once a day, the first message also brings today's reminders ("📌 Today: collect ₦… from Mama Tunde")."""
    today = dt.date.today().isoformat()
    if st.get("due_shown") != today:
        st["due_shown"] = today
        due = converse.due_today(lang)
        if due:
            send_text(phone, "\n".join(due))


# ---------------------------------------------------------------- webhook

@router.get("/whatsapp/webhook")
def verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == os.getenv("WHATSAPP_VERIFY_TOKEN"):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "verify token does not match WHATSAPP_VERIFY_TOKEN")


def _safe(msg):
    try:
        handle(msg)
    except Exception as e:  # noqa: BLE001 - never crash the server on one bad message
        print(f"whatsapp message failed: {type(e).__name__}: {e}")
        try:
            send_text(msg["from"], "😕 Something went wrong on my side. Please try again.")
        except Exception:  # noqa: BLE001
            pass


@router.post("/whatsapp/webhook")
async def incoming(request: Request, tasks: BackgroundTasks):
    raw = await request.body()
    secret = os.getenv("WHATSAPP_APP_SECRET")
    if secret:
        good = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(good, request.headers.get("X-Hub-Signature-256", "")):
            raise HTTPException(401, "bad signature")
    body = json.loads(raw or b"{}")
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):  # statuses (sent/read) are ignored
                if msg.get("id") in SEEN:
                    continue
                SEEN[msg.get("id")] = True
                while len(SEEN) > 2000:
                    SEEN.popitem(last=False)
                tasks.add_task(_safe, msg)  # answer Meta at once; do the slow work after
    return {"ok": True}
