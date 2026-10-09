"""TradeVoice on Telegram (src/telegram.py), against a faked Telegram: the webhook's secret, sharing your own number
(never someone else's), the same bot as WhatsApp (language, consent, a record checked with buttons and saved, a voice
note heard and a voice reply sent, a notebook photo read), HTML that can't break, "Confirm on Telegram" for sign-up,
reset codes and summaries to Telegram, erasing an account unlinks it, groups ignored, the pilot check and the webhook
set up at start. Made-up names and numbers only. python eval/test_telegram.py
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "WHATSAPP_", "TERMII_", "TELEGRAM_", "SMS_", "NATLAS", "INTRON")) \
            or k in ("AUTH_DEMO", "TV_PUBLIC", "SIGNUP_CODE", "PUBLIC_URL"):
        os.environ.pop(k)
os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "shared.db"), BOOKS_DIR=tempfile.mkdtemp(),
                  ACCOUNTS_DB=os.path.join(tempfile.mkdtemp(), "a.db"), TRAIN_DIR=tempfile.mkdtemp(),
                  TRADEVOICE_ADMIN="0", AUTH_REQUIRED="1", TV_PUBLIC="1", AUTO_REMINDERS="0",
                  TELEGRAM_BOT_TOKEN="123456:TEST-token", TELEGRAM_BOT_USERNAME="TradeVoiceTestBot",
                  PUBLIC_URL="https://tradevoice.example.org")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import accounts  # noqa: E402
import asr  # noqa: E402
import events  # noqa: E402
import ledger  # noqa: E402
import photo  # noqa: E402
import telegram  # noqa: E402
import v2  # noqa: E402
import web  # noqa: E402
import whatsapp  # noqa: E402

CALLS = []


def fake_call(method, payload=None, files=None, timeout=30):
    CALLS.append((method, payload, bool(files)))
    if method == "getFile":
        return {"file_path": "voice/f1.oga", "file_size": 2048}
    if method == "getMe":
        return {"username": "TradeVoiceTestBot"}
    if method == "getWebhookInfo":
        return {"url": "https://tradevoice.example.org/telegram/webhook", "pending_update_count": 0}
    return {"message_id": len(CALLS)}


class Got:
    content = b"OggS fake voice"

    def raise_for_status(self):
        return None


telegram.call = fake_call
telegram.requests.get = lambda url, timeout=None: Got()
asr.transcribe_auto = lambda path, lang, vocab=None: {"text": "Oga Emeka bought goods on credit 25000", "detected": None}


def fake_voice(text, lang):
    fd, path = tempfile.mkstemp(suffix=".ogg")
    os.write(fd, b"OggS")
    os.close(fd)
    return path


whatsapp.voice_file = fake_voice
c = TestClient(web.app)
CHECKS = []
N = {"u": 0, "m": 0}
ME, OTHER = 7001, 7002
PHONE = "2348030000901"


def check(name, ok, got=""):
    CHECKS.append(bool(ok))
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:500]}"))


def post(update, secret=None):
    N["u"] += 1
    update = {"update_id": N["u"], **update}
    h = {"X-Telegram-Bot-Api-Secret-Token": telegram.secret() if secret is None else secret}
    return c.post("/telegram/webhook", json=update, headers=h)


def msg(frm=ME, chat_type="private", **m):
    N["m"] += 1
    return post({"message": {"message_id": N["m"], "from": {"id": frm}, "chat": {"id": frm, "type": chat_type}, **m}})


def tap(data, frm=ME):
    N["m"] += 1
    return post({"callback_query": {"id": f"q{N['m']}", "from": {"id": frm}, "data": data,
                                    "message": {"message_id": N["m"], "chat": {"id": frm}}}})


def sent(method="sendMessage", since=0):
    return [p for m, p, _ in CALLS[since:] if m == method]


def said(since=0):
    return " ".join(json.dumps(p) for p in sent(since=since))


def main():
    events.ENABLED = True
    check("no secret header: refused", post({"message": {}}, secret="").status_code == 401)
    check("a wrong secret: refused", post({"message": {}}, secret="nope").status_code == 401)

    n = len(CALLS)
    msg(text="hello")
    first = sent(since=n)[-1]
    check("someone new: asked to share their number with Telegram's own button",
          "Share my phone number" in json.dumps(first) and first["reply_markup"]["keyboard"][0][0]["request_contact"], first)
    n = len(CALLS)
    msg(contact={"phone_number": "+2348030000999", "user_id": OTHER})
    check("someone else's contact card: refused, nothing linked", "your own number" in said(n) and not telegram.phone_of(ME))
    n = len(CALLS)
    msg(contact={"phone_number": "+2348030000901", "user_id": ME})
    check("their own contact: linked to that number (one book with the app)", telegram.phone_of(ME) == PHONE
          and "one book" in said(n), said(n))
    check("…then the WhatsApp bot's own first step: choose a language (buttons)",
          any("lang:English" in json.dumps(p) for p in sent(since=n)), said(n))

    n = len(CALLS)
    tap("lang:English")
    check("a button tap: answered (spinner stops), buttons removed, then the terms with an agree button",
          any(m == "answerCallbackQuery" for m, _, _ in CALLS[n:])
          and any(m == "editMessageReplyMarkup" for m, _, _ in CALLS[n:]) and "consent:yes" in said(n), said(n))
    tap("consent:yes")
    tap("train:no")

    n = len(CALLS)
    msg(text="Iya Bisi took 2 bags of rice for 60000, she will pay Friday")
    card = sent(since=n)[-1] if sent(since=n) else {}
    check("a typed record: the check card with Yes / No buttons (inline)",
          "60,000" in card.get("text", "") and [b[0]["callback_data"] for b in card["reply_markup"]["inline_keyboard"]] == ["yes", "no"],
          card)
    tap("yes")
    tok = ledger.use_book(PHONE)
    try:
        owed = {d["customer"]: d["balance"] for d in ledger.debtors()}
    finally:
        ledger.done_with_book(tok)
    check("…Yes saves it in that trader's own book", owed.get("Iya Bisi") == 60000, owed)

    n = len(CALLS)
    msg(voice={"file_id": "v1", "duration": 4, "mime_type": "audio/ogg", "file_size": 2048})
    check("a voice note: fetched from Telegram, heard, and what was heard is shown",
          any(m == "getFile" for m, _, _ in CALLS[n:]) and "Oga Emeka" in said(n), said(n))
    check("…and the answer comes back as a voice note too (sendVoice, OGG)", any(m == "sendVoice" and f for m, _, f in CALLS[n:]))
    tap("no")

    photo.read = lambda p: {"rows": [{"type": "sale", "item": "rice", "amount": 5000}]}
    n = len(CALLS)
    msg(photo=[{"file_id": "p-small", "file_size": 100, "width": 90}, {"file_id": "p-big", "file_size": 9000, "width": 1280}])
    check("a notebook photo: the biggest size is read, lines to check with Save / Cancel",
          any(m == "getFile" and p["file_id"] == "p-big" for m, p, _ in CALLS[n:]) and "p_save" in said(n), said(n))
    tap("p_cancel")

    check("HTML can't break: < > & escaped, WhatsApp *bold* and _italic_ become tags",
          telegram.as_html("a < b & *Iya Bisi* owes _5,000_") == "a &lt; b &amp; <b>Iya Bisi</b> owes <i>5,000</i>",
          telegram.as_html("a < b & *Iya Bisi* owes _5,000_"))
    n = len(CALLS)
    msg(sticker={"file_id": "s1"})
    check("a sticker: no answer", not sent(since=n))
    n = len(CALLS)
    msg(frm=7100, chat_type="group", text="hello")
    check("a group chat: ignored (the bot is one to one)", not sent(since=n))
    n = len(CALLS)
    msg(text="/id")
    check("/id tells a team member their chat id (for TEAM_TELEGRAM alerts)", str(ME) in said(n))
    with events._db() as db:
        kinds = [dict(r) for r in db.execute("SELECT * FROM events WHERE kind='message'")]
    check("its messages are logged as Telegram (type only, no words)", kinds and all(r["channel"] == "telegram" for r in kinds)
          and "Iya Bisi" not in json.dumps(kinds), kinds[:2])

    # the website: sign-up confirmed through Telegram (codes required, no SMS): the bot asks for the number, it matches
    os.environ["SIGNUP_CODE"] = "required"
    r = c.post("/api/auth/v2/code/start", json={"phone": "08030000902", "purpose": "signup"}).json()
    check("sign-up with no SMS: 'Confirm on Telegram' offered (word + bot name), nothing sent", r["tg"] == "TradeVoiceTestBot"
          and r["word"] and not r["sent"], r)
    NEW = 7003
    n = len(CALLS)
    msg(frm=NEW, text=f"/start login-{r['word']}")
    check("…the link opens the bot: share your number first", "Share my phone number" in said(n))
    msg(frm=NEW, contact={"phone_number": "2348030000902", "user_id": NEW})
    check("…their own number matches: confirmed, the page carries on",
          c.post("/api/auth/v2/code/poll", json={"login_id": r["login_id"]}).json() == {"ok": True})
    s = c.post("/api/auth/v2/signup", json={"login_id": r["login_id"], "pw": hashlib.sha256(b"pw:Bola-pass-2026").hexdigest(),
                                           "name": "Bola Testtrader", "biz": "Bola Test Stores"})
    check("…and the account is made", s.status_code == 200, s.text)
    r = c.post("/api/auth/v2/code/start", json={"phone": "08030000903", "purpose": "signup"}).json()
    LIAR = 7004
    msg(frm=LIAR, text=f"/start login-{r['word']}")
    n = len(CALLS)
    msg(frm=LIAR, contact={"phone_number": "2348030000904", "user_id": LIAR})
    check("a Telegram account with another number can't confirm someone's sign-up",
          "old or not for this number" in said(n) and
          c.post("/api/auth/v2/code/poll", json={"login_id": r["login_id"]}).json() == {"ok": False}, said(n))
    os.environ.pop("SIGNUP_CODE")

    # one book, whichever way they came in
    r = c.post("/api/auth/v2/code/start", json={"phone": "08030000905", "purpose": "signup"}).json()
    c.post("/api/auth/v2/signup", json={"login_id": r["login_id"], "pw": hashlib.sha256(b"pw:Ngozi-pass-2026").hexdigest(),
                                        "name": "Ngozi Testtrader", "biz": "Ngozi Test Stores", "lang": "Hausa"})
    c.post("/api/auth/v2/logout")
    WEB = 7005
    msg(frm=WEB, text="/start")
    n = len(CALLS)
    msg(frm=WEB, contact={"phone_number": "2348030000905", "user_id": WEB})
    check("a trader who already uses the web app: welcomed back by name, told it's the same book",
          "Welcome back, Ngozi" in said(n) and "Ngozi Test Stores" in said(n) and "same book" in said(n), said(n))
    check("…no second language question and no second 'I agree' (their sign-up carries over)",
          "lang:" not in said(n) and "consent:yes" not in said(n), said(n))
    n = len(CALLS)
    msg(frm=WEB, text="Mama Ngozi took goods worth 4000 on credit")
    check("…and they can record straight away", "4,000" in said(n) or "4000" in said(n), said(n))

    TG_FIRST = 7006
    msg(frm=TG_FIRST, text="/start")
    n = len(CALLS)
    msg(frm=TG_FIRST, contact={"phone_number": "2348030000906", "user_id": TG_FIRST})
    check("someone new on Telegram: told Open my book shows the same book in the app, no sign-up",
          "Tap Open my book" in said(n) and "no sign-up needed" in said(n), said(n))

    # "Open my book" in Telegram: Telegram signs who opened it (initData); they are in their own book at once
    import time as _t
    import urllib.parse as _up

    def init_data(uid, first="Tolu", age=0, token="123456:TEST-token"):
        f = {"auth_date": str(int(_t.time()) - age), "query_id": "AAH-test",
             "user": json.dumps({"id": uid, "first_name": first, "last_name": "Testtrader"}, separators=(",", ":"))}
        check_str = "\n".join(f"{k}={v}" for k, v in sorted(f.items()))
        key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        f["hash"] = hmac.new(key, check_str.encode(), hashlib.sha256).hexdigest()
        return _up.urlencode(f)
    tap("lang:English", frm=TG_FIRST)
    tap("consent:yes", frm=TG_FIRST)
    msg(frm=TG_FIRST, text="Iya Bisi took 3 bags of garri 15000 on credit")
    msg(frm=TG_FIRST, text="yes")
    app = TestClient(web.app)
    r = app.post("/api/auth/telegram", json={"init_data": init_data(TG_FIRST)})
    me = app.get("/api/v2/me")
    check("Open my book (Telegram-first trader, no password): logged in to their own book at once, no sign-up",
          r.status_code == 200 and me.status_code == 200 and me.json()["phone"].endswith("8030000906")
          and me.json()["name"] == "Tolu Testtrader", (r.text, me.text))
    owed = app.get("/api/debts").json().get("owed_to_me", [])
    check("…what they saved in the Telegram chat is there in the app (one book)",
          any(x["customer"] == "Iya Bisi" and x["balance"] == 15000 for x in owed), owed)
    check("…and the website still asks a password from anyone who comes without Telegram",
          TestClient(web.app).get("/api/v2/me").status_code == 401)
    r = TestClient(web.app).post("/api/auth/telegram", json={"init_data": init_data(TG_FIRST).replace("Tolu", "Bola")})
    check("…a changed note (not signed by Telegram with our bot's token): refused", r.status_code == 401, r.text)
    r = TestClient(web.app).post("/api/auth/telegram", json={"init_data": init_data(TG_FIRST, token="999:other-bot")})
    check("…signed for another bot: refused", r.status_code == 401, r.text)
    r = TestClient(web.app).post("/api/auth/telegram", json={"init_data": init_data(TG_FIRST, age=7200)})
    check("…an old note (over an hour): refused", r.status_code == 401, r.text)
    r = TestClient(web.app).post("/api/auth/telegram", json={"init_data": init_data(7999)})
    check("…someone who hasn't shared their number with the bot: told to do that first (no book opened)",
          r.status_code == 409 and r.json() == {"link": True, "bot": "TradeVoiceTestBot"}, r.text)
    n = len(CALLS)
    n = len(CALLS)
    r = c.post("/api/auth/v2/code/start", json={"phone": "08030000906", "purpose": "signup"}).json()
    sent_code = "".join(ch for ch in said(n) if ch.isdigit())[-6:]
    check("their number on the website: sign-up needs the code sent to their Telegram (nobody else opens that book)",
          r.get("channel") == "telegram" and r["sent"] and not r.get("nocode") and len(sent_code) == 6, (r, said(n)))
    ok = c.post("/api/auth/v2/code/check", json={"login_id": r["login_id"], "code": sent_code, "purpose": "signup"})
    s2 = c.post("/api/auth/v2/signup", json={"login_id": r["login_id"], "pw": hashlib.sha256(b"pw:Tg-pass-2026").hexdigest(),
                                            "name": "Tolu Testtrader", "biz": "Tolu Test Stores"})
    check("…with that code, the account is made on the same book", ok.status_code == 200 and s2.status_code == 200,
          (ok.text, s2.text))
    c.post("/api/auth/v2/logout")

    # messages we send first, to a trader linked on Telegram (no 24-hour window there)
    n = len(CALLS)
    check("a daily summary or paid notice reaches a trader linked on Telegram",
          whatsapp.send_first(PHONE, "summary", "2 customers promised to pay today.") and "promised to pay" in said(n))
    check("…someone not on Telegram, and no WhatsApp: quietly not sent", whatsapp.send_first("2348030000999", "summary", "x")
          is False)

    accounts.delete_account(PHONE)
    check("erasing an account removes its Telegram link", telegram.phone_of(ME) is None)

    import importlib
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    preflight = importlib.import_module("preflight")
    st, detail = preflight.telegram_bot()
    check("pilot check: bot name and webhook ok, no token shown", st == "PASS" and "@TradeVoiceTestBot" in detail
          and "TEST-token" not in detail, (st, detail))
    n = len(CALLS)
    telegram.setup()
    hook = [p for m, p, _ in CALLS[n:] if m == "setWebhook"]
    check("at start the app points Telegram at /telegram/webhook with the secret header",
          hook and hook[0]["url"] == "https://tradevoice.example.org/telegram/webhook" and hook[0]["secret_token"] == telegram.secret()
          and hook[0]["allowed_updates"] == ["message", "callback_query"], hook)
    menu = [p for m, p, _ in CALLS[n:] if m == "setChatMenuButton"]
    check("…and the bot's menu button opens the app inside Telegram", menu and menu[0]["menu_button"]["web_app"]["url"]
          == "https://tradevoice.example.org/app", menu)
    page = c.get("/app").text
    check("the app page knows the bot (TV_CH.tg) for 'Connect my Telegram'", '"tg": "TradeVoiceTestBot"' in page)

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} Telegram checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
