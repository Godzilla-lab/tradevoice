"""Sign-up and log-in codes by SMS (src/sms.py, TextBee: a team Android phone sends ordinary texts), against a faked
TextBee: the code goes by SMS when WhatsApp is off, the page is told, the code works, the daily cap and the hourly
limits hold, a refused key or a dead gateway means 503 (never a code on screen), and neither the number nor the code
is ever logged. Also: a number shared with the Telegram bot gets its reset code in Telegram, free.
Made-up numbers only. python eval/test_sms.py
"""
import hashlib
import json
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "WHATSAPP_", "TEXTBEE_", "TELEGRAM_", "SMS_")) or \
            k in ("AUTH_DEMO", "TV_PUBLIC", "SIGNUP_CODE"):
        os.environ.pop(k)
os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "shared.db"), BOOKS_DIR=tempfile.mkdtemp(),
                  ACCOUNTS_DB=os.path.join(tempfile.mkdtemp(), "a.db"), TRAIN_DIR=tempfile.mkdtemp(),
                  TRADEVOICE_ADMIN="0", AUTH_REQUIRED="1", TV_PUBLIC="1",
                  TEXTBEE_API_KEY="tb-secret-key", TEXTBEE_DEVICE_ID="dev123", SMS_DAILY_MAX="4")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import events  # noqa: E402
import sms  # noqa: E402
import telegram  # noqa: E402
import v2  # noqa: E402
import web  # noqa: E402

CHECKS = []
TEXTS = []
MODE = {"status": 201}


class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def fake_post(url, headers=None, json=None, timeout=None, **kw):   # noqa: A002
    TEXTS.append({"url": url, "headers": headers, "json": json})
    if MODE["status"] == "down":
        raise sms.requests.ConnectionError("no route")
    return Resp(MODE["status"], {"data": {"success": True}})


sms.requests.post = fake_post
sms.requests.get = lambda url, headers=None, timeout=None: Resp(200, {"data": [{"_id": "dev123", "enabled": True}]})
c = TestClient(web.app)


def check(name, ok, got=""):
    CHECKS.append(bool(ok))
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def pw(p):
    return hashlib.sha256(("pw:" + p).encode()).hexdigest()


def start(phone, purpose="signup", ip="10.0.0.1"):
    return c.post("/api/auth/v2/code/start", json={"phone": phone, "purpose": purpose}, headers={"x-forwarded-for": ip})


def last_code():
    msg = TEXTS[-1]["json"]["message"]
    return "".join(ch for ch in msg.split(":")[1] if ch.isdigit())[:6]


def main():
    events.ENABLED = True
    check("SMS set up, no WhatsApp: the page is told codes go by SMS (and sign-up needs one)",
          v2.channels()["codes"] == "sms" and not v2.channels()["nocode"])

    r = start("08030000801").json()
    t = TEXTS[-1]
    check("sign-up: the code goes by SMS through the team's TextBee phone",
          r["sent"] and r["channel"] == "sms" and not r["demo_code"] and t["url"].endswith("/gateway/devices/dev123/send-sms")
          and t["headers"]["x-api-key"] == "tb-secret-key" and t["json"]["recipients"] == ["+2348030000801"], (r, t))
    check("…a short text: the code, how long it lasts, don't share it",
          "TradeVoice code:" in t["json"]["message"] and "10 minutes" in t["json"]["message"]
          and len(t["json"]["message"]) <= 160, t["json"]["message"])
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

    # the gateway refuses or is down: 503, never a code on screen, the reason on /team (no number, no code)
    MODE["status"] = 401
    r = start("08030000802")
    check("TextBee refuses the key: 503, no code on screen", r.status_code == 503 and "demo_code" not in r.text, r.text)
    MODE["status"] = "down"
    r = start("08030000803", ip="10.0.0.2")
    check("the phone or TextBee can't be reached: 503", r.status_code == 503, r.text)
    MODE["status"] = 201
    with events._db() as db:
        rows = [dict(x) for x in db.execute("SELECT * FROM events WHERE kind LIKE 'sms%' ORDER BY id")]
    import team
    fails = [team.describe(x)[1] for x in rows if x["kind"] == "sms_failed"]
    check("…/team shows why, in words", any("key was refused" in f for f in fails) and any("not reachable" in f for f in fails),
          fails)
    dump = json.dumps(rows)
    check("…and no phone number or code is ever logged", "08030000" not in dump and "2348030000" not in dump
          and all(x["who"] in ("", None) for x in rows), rows)

    # the daily cap (SMS_DAILY_MAX=4 here; the free plan allows 50): past it, no more texts today
    used = sms.sent_today()
    for i in range(sms.daily_max() - used):
        start(f"0803000081{i}", ip=f"10.0.1.{i}")
    n = len(TEXTS)
    r = start("08030000820", ip="10.0.2.1")
    check("daily cap reached: no text goes out, 503", r.status_code == 503 and len(TEXTS) == n, (r.text, len(TEXTS), n))
    os.environ["SMS_DAILY_MAX"] = "100"

    # the hourly limits still hold (texts cost the SIM's bundle)
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

    # the pilot check reads TextBee without printing the key
    import importlib
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    preflight = importlib.import_module("preflight")
    st, detail = preflight.codes()
    check("pilot check: 'codes go by SMS', phone registered, no key shown", st == "PASS" and "SMS" in detail
          and "tb-secret-key" not in detail, (st, detail))

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} SMS code checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
