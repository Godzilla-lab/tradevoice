"""Sign-up and log-in codes by Termii (src/sms.py: a text on the DND route, or a phone call that reads the code out),
against a faked Termii: the code goes by SMS when WhatsApp is off, the page is told, the code works; a sender ID not
approved yet means a call instead; the daily cap and the hourly limits hold; an empty wallet, a refused key or no
network means 503 (never a code on screen); neither the number nor the code is ever logged. Also: a number shared with
the Telegram bot gets its reset code in Telegram, free. Made-up numbers only. python eval/test_sms.py
"""
import hashlib
import json
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "WHATSAPP_", "TERMII_", "TELEGRAM_", "SMS_")) or \
            k in ("AUTH_DEMO", "TV_PUBLIC", "SIGNUP_CODE"):
        os.environ.pop(k)
os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "shared.db"), BOOKS_DIR=tempfile.mkdtemp(),
                  ACCOUNTS_DB=os.path.join(tempfile.mkdtemp(), "a.db"), TRAIN_DIR=tempfile.mkdtemp(),
                  TRADEVOICE_ADMIN="0", AUTH_REQUIRED="1", TV_PUBLIC="1",
                  TERMII_API_KEY="tm-secret-key", TERMII_BASE_URL="https://acct.api.termii.test",
                  TERMII_SENDER_ID="TradeVoice", SMS_DAILY_MAX="100")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import events  # noqa: E402
import sms  # noqa: E402
import telegram  # noqa: E402
import v2  # noqa: E402
import web  # noqa: E402

CHECKS = []
TEXTS = []       # every request to Termii: {"url", "json"}
MODE = {"text": "ok", "call": "ok"}   # ok | sender | wallet | key | down
SENDERS = {"content": [{"sender_id": "TradeVoice", "status": "active", "country": "Nigeria"}]}


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def fake_post(url, json=None, timeout=None, **kw):   # noqa: A002
    TEXTS.append({"url": url, "json": json})
    how = MODE["call" if url.endswith("/otp/call") else "text"]
    if how == "down":
        raise sms.requests.ConnectionError("no route")
    if how == "sender":
        return Resp(400, {"message": "Invalid Sender Id"})
    if how == "wallet":
        return Resp(400, {"message": "Insufficient balance"})
    if how == "key":
        return Resp(401, {"message": "Unauthorized"})
    return Resp(200, {"code": "ok", "message_id": "301754", "message": "Successfully Sent", "balance": 900.5})


def fake_get(url, params=None, timeout=None, **kw):
    if url.endswith("/api/get-balance"):
        return Resp(200, {"balance": 900.5, "currency": "NGN", "user": "Test"})
    return Resp(200, SENDERS)


sms.requests.post = fake_post
sms.requests.get = fake_get
c = TestClient(web.app)


def check(name, ok, got=""):
    CHECKS.append(bool(ok))
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def pw(p):
    return hashlib.sha256(("pw:" + p).encode()).hexdigest()


def start(phone, purpose="signup", ip="10.0.0.1"):
    return c.post("/api/auth/v2/code/start", json={"phone": phone, "purpose": purpose}, headers={"x-forwarded-for": ip})


def last_code():
    j = TEXTS[-1]["json"]
    if "code" in j:   # a phone call
        return str(j["code"])
    return "".join(ch for ch in j["sms"].split(":")[1] if ch.isdigit())[:6]


def main():
    events.ENABLED = True
    check("SMS set up, no WhatsApp: the page is told codes go by SMS (and sign-up needs one)",
          v2.channels()["codes"] == "sms" and not v2.channels()["nocode"])

    r = start("08030000801").json()
    t = TEXTS[-1]
    check("sign-up: the code goes by Termii, a text from our sender ID on the DND route (reaches DND numbers)",
          r["sent"] and r["channel"] == "sms" and not r["demo_code"]
          and t["url"] == "https://acct.api.termii.test/api/sms/send" and t["json"]["api_key"] == "tm-secret-key"
          and t["json"]["to"] == "2348030000801" and t["json"]["from"] == "TradeVoice" and t["json"]["channel"] == "dnd"
          and t["json"]["type"] == "plain", (r, t))
    check("…a short text: the code, how long it lasts, don't share it (one SMS page)",
          "TradeVoice code:" in t["json"]["sms"] and "10 minutes" in t["json"]["sms"]
          and len(t["json"]["sms"]) <= 160, t["json"]["sms"])
    bad = c.post("/api/auth/v2/code/check", json={"login_id": r["login_id"], "code": "000000", "purpose": "signup"})
    check("…a wrong code is refused", bad.status_code == 400)
    ok = c.post("/api/auth/v2/code/check", json={"login_id": r["login_id"], "code": last_code(), "purpose": "signup"})
    s = c.post("/api/auth/v2/signup", json={"login_id": r["login_id"], "pw": pw("Ade-pass-2026"), "name": "Ade Testtrader",
                                           "biz": "Ade Test Stores"})
    check("…the right code works and the account is made", ok.status_code == 200 and s.status_code == 200, (ok.text, s.text))
    c.post("/api/auth/v2/logout")

    r = start("08030000801", "reset").json()
    check("forgot password: the reset code goes by SMS too", r["sent"] and r["channel"] == "sms", r)
    tk = c.post("/api/auth/v2/code/check", json={"login_id": r["login_id"], "code": last_code(), "purpose": "signup"})
    check("…a reset code can't be turned into a sign-up ticket (the purpose is the one asked for)",
          tk.status_code == 200 and v2.CODE_TICKETS[r["login_id"]][1] == "reset", v2.CODE_TICKETS.get(r["login_id"]))

    page = c.get("/app").text
    check("the app page says codes come by SMS (TV_CH)", '"codes": "sms"' in page and '"nocode": false' in page)

    # the sender ID is still waiting for Termii's approval: no text can go, and no call either (the team chose texts)
    MODE["text"] = "sender"
    n = len(TEXTS)
    r = start("08030000807", ip="10.0.0.7").json()
    check("sender ID not approved yet: sign-up goes on with number + password (nobody is stuck), and no call is made",
          r.get("nocode") and not r["demo_code"] and len(TEXTS) == n + 1 and TEXTS[-1]["url"].endswith("/api/sms/send"), r)
    r = start("08030000801", "reset", ip="10.0.0.8")
    check("…but a password reset still needs a code: 503 (nobody takes over a book)", r.status_code == 503, r.text)
    os.environ["TERMII_CALL_BACKUP"] = "1"
    r = start("08030000805", ip="10.0.0.5").json()
    t = TEXTS[-1]
    check("TERMII_CALL_BACKUP=1 (off by default): the same code goes by a phone call instead",
          r["sent"] and r["channel"] == "call" and t["url"].endswith("/api/sms/otp/call")
          and t["json"]["phone_number"] == "2348030000805" and isinstance(t["json"]["code"], int), (r, t))
    ok = c.post("/api/auth/v2/code/check", json={"login_id": r["login_id"], "code": last_code(), "purpose": "signup"})
    check("…and the code they hear works", ok.status_code == 200, ok.text)
    os.environ.pop("TERMII_CALL_BACKUP")
    MODE["text"] = "ok"
    os.environ.pop("TERMII_SENDER_ID")
    n = len(TEXTS)
    r = start("08030000806", ip="10.0.0.6").json()
    t = TEXTS[-1]
    check("no sender ID (the live setup): the code goes by a phone call that reads it out, no sender ID needed",
          r["sent"] and r["channel"] == "call" and len(TEXTS) == n + 1 and t["url"].endswith("/api/sms/otp/call")
          and t["json"]["phone_number"] == "2348030000806" and "from" not in t["json"], (r, t))
    ok = c.post("/api/auth/v2/code/check", json={"login_id": r["login_id"], "code": last_code(), "purpose": "signup"})
    check("…the code read out works", ok.status_code == 200, ok.text)
    ch = v2.channels()
    page = c.get("/app").text
    check("…the page is told codes come by a call (it says 'call you with your code', not SMS)",
          ch["codes"] == "sms" and ch["call"] and '"call": true' in page, ch)
    os.environ["TERMII_CHANNEL"] = "dnd"
    check("TERMII_CHANNEL=dnd without a sender ID: not set up (a text needs one)", not sms.ready())
    os.environ.pop("TERMII_CHANNEL")
    os.environ["TERMII_SENDER_ID"] = "TradeVoice"
    import accounts
    check("codes never start with 0 (a call reads the code as a number)",
          all(accounts.start("2348030000899")["code"][0] != "0" for _ in range(300)))

    # Termii refuses or can't be reached: never a code on screen, the reason on /team (no number, no code); sign-up
    # goes on without a code, a reset gets 503, and SIGNUP_CODE=required makes sign-up wait instead
    MODE.update(text="wallet", call="wallet")
    r = start("08030000802")
    check("the Termii wallet is empty: sign-up goes on without a code, no code on screen", r.status_code == 200
          and r.json().get("nocode") and r.json()["demo_code"] is None, r.text)
    r = start("08030000801", "reset", ip="10.0.0.9")
    check("…a reset: 503", r.status_code == 503, r.text)
    MODE.update(text="key", call="key")
    os.environ["SIGNUP_CODE"] = "required"
    r = start("08030000804", ip="10.0.0.4")
    check("Termii refuses the key, SIGNUP_CODE=required: sign-up waits (503), never a code on screen",
          r.status_code == 503 and "demo_code" not in r.text, r.text)
    os.environ.pop("SIGNUP_CODE")
    MODE.update(text="down", call="down")
    r = start("08030000803", ip="10.0.0.2")
    check("Termii can't be reached: sign-up goes on without a code", r.status_code == 200 and r.json().get("nocode"), r.text)
    MODE.update(text="ok", call="ok")
    with events._db() as db:
        rows = [dict(x) for x in db.execute("SELECT * FROM events WHERE kind LIKE 'sms%' ORDER BY id")]
    import team
    fails = [team.describe(x)[1] for x in rows if x["kind"] == "sms_failed"]
    check("…/team shows why, in words", any("key was refused" in f for f in fails) and any("not reachable" in f for f in fails)
          and any("wallet is empty" in f for f in fails) and any("sender ID is not approved" in f for f in fails), fails)
    dump = json.dumps(rows)
    check("…and no phone number or code is ever logged", "08030000" not in dump and "2348030000" not in dump
          and all(x["who"] in ("", None) for x in rows), rows)

    # the daily cap (50 by default; 3 more than used so far here): past it, no more codes today (it caps the wallet)
    os.environ["SMS_DAILY_MAX"] = str(sms.sent_today() + 3)
    used = sms.sent_today()
    for i in range(sms.daily_max() - used):
        start(f"0803000081{i}", ip=f"10.0.1.{i}")
    n = len(TEXTS)
    r = start("08030000820", ip="10.0.2.1")
    check("daily cap reached: no text goes out (sign-up goes on without a code)",
          r.status_code == 200 and r.json().get("nocode") and len(TEXTS) == n, (r.text, len(TEXTS), n))
    os.environ["SMS_DAILY_MAX"] = "100"

    # the hourly limits still hold (every code costs money)
    codes = [start("08030000830", ip="10.0.3.1").status_code for _ in range(6)]
    check("at most 5 codes an hour for one number", codes[:5] == [200] * 5 and codes[5] == 429, codes)

    # a number shared with the Telegram bot gets its reset code there, free (no SMS spent)
    os.environ["TELEGRAM_BOT_TOKEN"] = "123:abc"
    os.environ["TELEGRAM_BOT_USERNAME"] = "TradeVoiceTestBot"
    sent_tg = []
    telegram.call = lambda method, payload=None, **kw: sent_tg.append((method, payload)) or {}
    telegram.link("555", "555", "2348030000801")
    n = len(TEXTS)
    r = start("08030000801", "reset", ip="10.0.4.1").json()
    check("a number shared with the Telegram bot: the reset code goes to Telegram, no SMS spent",
          r["channel"] == "telegram" and len(TEXTS) == n and sent_tg and sent_tg[-1][1]["chat_id"] == "555", (r, sent_tg))
    r = start("08030000840", ip="10.0.4.2").json()
    check("…but sign-up still goes by SMS (Telegram can't reach a number nobody shared)", r["channel"] == "sms", r)

    # the pilot check reads the Termii wallet and the sender ID's approval, without printing the key
    import importlib
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    preflight = importlib.import_module("preflight")
    st, detail = preflight.codes()
    check("pilot check: codes go by Termii, texts from the approved sender ID, the wallet shown, no key",
          st == "PASS" and "Termii" in detail and "texts from TradeVoice" in detail and "900.50" in detail
          and "tm-secret-key" not in detail, (st, detail))
    os.environ.pop("TERMII_SENDER_ID")
    st, detail = preflight.codes()
    check("…no sender ID: PASS, codes go by phone call, the wallet shown", st == "PASS" and "phone call" in detail
          and "900.50" in detail, (st, detail))
    os.environ["TERMII_SENDER_ID"] = "TradeVoice"
    SENDERS["content"][0]["status"] = "pending"
    st, detail = preflight.codes()
    check("…sender ID still pending: a WARN that says sign-up goes on without a code until Termii approves it",
          st == "WARN" and "pending" in detail and "number + password" in detail, (st, detail))

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} SMS code checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
