"""Phone-number login + one book per trader. No keys needed (WhatsApp is faked).

python eval/test_auth.py
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"  # never let the real .env keys into a test
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith("LOCAL_") or k.startswith("WHATSAPP_") or k == "AUTH_DEMO":
        os.environ.pop(k)
os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "shared.db"), BOOKS_DIR=tempfile.mkdtemp(),
                  ACCOUNTS_DB=os.path.join(tempfile.mkdtemp(), "a.db"), WHATSAPP_TOKEN="test",
                  WHATSAPP_PHONE_ID="123", WHATSAPP_VERIFY_TOKEN="v", WHATSAPP_APP_SECRET="s3cret",
                  WHATSAPP_DISPLAY_NUMBER="+1 555 154 9545", TRADEVOICE_ADMIN="0", AUTH_REQUIRED="1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient  # noqa: E402

import accounts  # noqa: E402
import web  # noqa: E402
import whatsapp  # noqa: E402

SENT = []
whatsapp.graph_post = lambda p: SENT.append(p) or {"messages": [{"id": "x"}]}
CHECKS = []


def check(name, ok, got=""):
    ok = bool(ok)
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:300]}"))


def code_sent():
    for p in reversed(SENT):
        if p.get("type") == "text" and "code" in p["text"]["body"].lower():
            return p["text"]["body"].split("*")[1]
    return None


def login(client, phone):
    SENT.clear()
    r = client.post("/api/auth/start", json={"phone": phone}).json()
    return client.post("/api/auth/verify", json={"login_id": r["login_id"], "code": code_sent()})


def main():
    check("0803 123 4567 -> 2348031234567", accounts.normalize("0803 123 4567") == "2348031234567")
    check("+234 803 123 4567 -> same", accounts.normalize("+234 803 123 4567") == "2348031234567")
    check("803 123 4567 -> same", accounts.normalize("803 123 4567") == "2348031234567")
    check("'hello' is not a number", accounts.normalize("hello") is None)

    a = TestClient(web.app)
    r = a.get("/api/today")
    check("not logged in -> 401 on the book", r.status_code == 401 and r.json().get("login"), r.text)
    check("words for the login screen still load", a.get("/api/ui?lang=Yoruba").status_code == 200)
    check("bad number refused", a.post("/api/auth/start", json={"phone": "12"}).status_code == 400)

    SENT.clear()
    st = a.post("/api/auth/start", json={"phone": "0803 123 4567", "lang": "Pidgin"}).json()
    code = code_sent()
    check("code sent to the number on WhatsApp", st["sent"] and code and len(code) == 6
          and SENT[-1]["to"] == "2348031234567", SENT)
    check("code NOT shown on screen (not demo)", st["demo_code"] is None, st)
    check("'Verify with WhatsApp' link to the bot", st["verify_link"].startswith("https://wa.me/15551549545?text=LOGIN"),
          st)
    wrong = "000000" if code != "000000" else "111111"
    r = a.post("/api/auth/verify", json={"login_id": st["login_id"], "code": wrong})
    check("wrong code refused, tries left shown", r.status_code == 400 and "left" in r.text, r.text)
    r = a.post("/api/auth/verify", json={"login_id": st["login_id"], "code": code})
    check("right code -> logged in + cookie", r.status_code == 200 and web.COOKIE in r.cookies, r.text)
    r = a.post("/api/auth/verify", json={"login_id": st["login_id"], "code": code})
    check("the same code can't be used twice", r.status_code == 400, r.text)
    me = a.get("/api/auth/me").json()
    check("me: masked number, new user", me["phone"].endswith("4567") and "803" not in me["phone"] and me["new"], me)
    a.post("/api/auth/me", json={"shop": "Chioma Stores", "lang": "Pidgin"})
    check("shop name saved", a.get("/api/auth/me").json()["shop"] == "Chioma Stores")

    # trader A records a sale; trader B must not see it
    web.SESSIONS.clear()
    a.post("/api/message", json={"session": "s", "text": "Mama Tunde dey owe me 45k", "lang": "Pidgin"})
    a.post("/api/message", json={"session": "s", "text": "yes", "lang": "Pidgin"})
    debts_a = a.get("/api/debts").json()
    check("A's book has Mama Tunde", "Mama Tunde" in json.dumps(debts_a), debts_a)

    b = TestClient(web.app)
    login(b, "08091112222")
    debts_b = b.get("/api/debts").json()
    check("B's book is separate (no Mama Tunde)", "Mama Tunde" not in json.dumps(debts_b), debts_b)
    check("each number has its own book file", len(os.listdir(os.environ["BOOKS_DIR"])) == 2,
          os.listdir(os.environ["BOOKS_DIR"]))

    # WhatsApp from A's number writes into A's book (same book as the web app)
    def wa(phone, text, mid):
        body = json.dumps({"entry": [{"changes": [{"value": {"messages": [
            {"from": phone, "id": mid, "type": "text", "text": {"body": text}}]}}]}]})
        sig = "sha256=" + hmac.new(b"s3cret", body.encode(), hashlib.sha256).hexdigest()
        SENT.clear()
        a.post("/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": sig})
        return " ".join(p["text"]["body"] for p in SENT if p.get("type") == "text")

    # "Verify with WhatsApp": C starts on the web, sends LOGIN <word> from the right phone
    c = TestClient(web.app)
    st = c.post("/api/auth/start", json={"phone": "07012345678"}).json()
    check("not verified yet -> poll says no", c.post("/api/auth/poll", json={"login_id": st["login_id"]}).json()
          == {"ok": False})
    out = wa("2348091112222", f"LOGIN {st['word']}", "w1")
    check("LOGIN from ANOTHER number is refused", "old or not for this number" in out, out)
    check("…and does not log C in", c.post("/api/auth/poll", json={"login_id": st["login_id"]}).json()
          == {"ok": False})
    out = wa("2347012345678", f"LOGIN {st['word']}", "w2")
    check("LOGIN from the right number -> confirmed", "logged in" in out, out)
    r = c.post("/api/auth/poll", json={"login_id": st["login_id"]})
    check("web page polls -> logged in", r.status_code == 200 and r.json().get("ok") and web.COOKIE in r.cookies,
          r.text)

    # demo data only into an empty book
    r = b.post("/api/demo_data")
    check("sample data fills B's empty book", r.status_code == 200 and b.get("/api/profile").json()["profile"])
    check("…but never over real records (A)", a.post("/api/demo_data").status_code == 400)

    # log out, delete account
    b.post("/api/auth/logout")
    check("logged out -> 401", b.get("/api/today").status_code == 401)
    r = login(b, "08091112222")
    r = b.post("/api/auth/delete", json={"login_id": "-", "code": "DELETE"})
    check("delete my account removes the book", r.status_code == 200 and
          not os.path.exists(os.path.join(os.environ["BOOKS_DIR"], "2348091112222.db")))

    # WhatsApp configured but the token has expired: the code is shown, never a dead end (unless AUTH_STRICT=1)
    real_post = whatsapp.graph_post
    def expired(p):
        raise RuntimeError("WhatsApp send failed 401: Session has expired")
    whatsapp.graph_post = expired
    st = c.post("/api/auth/start", json={"phone": "08030000009"}).json()
    check("token expired -> code shown on screen (fallback)", st["fallback"] and st["demo_code"] and not st["sent"], st)
    os.environ["AUTH_STRICT"] = "1"
    st = c.post("/api/auth/start", json={"phone": "08030000010"}).json()
    check("AUTH_STRICT=1 -> no code on screen", st["demo_code"] is None, st)
    os.environ.pop("AUTH_STRICT")
    whatsapp.graph_post = real_post

    # demo mode: no WhatsApp -> code on screen
    os.environ["AUTH_DEMO"] = "1"
    st = c.post("/api/auth/start", json={"phone": "08030000000"}).json()
    check("demo mode shows the code on screen", st["demo_code"] and len(st["demo_code"]) == 6, st)
    os.environ.pop("AUTH_DEMO")

    # too many wrong codes
    st = c.post("/api/auth/start", json={"phone": "08030000001"}).json()
    for _ in range(5):
        c.post("/api/auth/verify", json={"login_id": st["login_id"], "code": "999999"})
    r = c.post("/api/auth/verify", json={"login_id": st["login_id"], "code": code_sent()})
    check("after 5 wrong codes even the right one is refused", r.status_code == 400, r.text)

    # no login: a new browser opens its own book straight away
    g = TestClient(web.app)
    check("no login: the app asks for nothing", g.get("/api/auth/me").status_code == 401)
    r = g.post("/api/auth/guest", json={"shop": "Ada Stores", "lang": "Yoruba"}).json()
    check("guest book opens with shop + language, no phone shown", r["me"]["guest"] and r["me"]["shop"] == "Ada Stores"
          and r["me"]["lang"] == "Yoruba" and r["me"]["phone"] == "", r)
    g.post("/api/message", json={"session": "g", "text": "I sell rice 5000", "lang": "English"})
    g.post("/api/message", json={"session": "g", "text": "yes", "lang": "English"})
    check("…and it keeps its records", g.get("/api/today").json()["summary"]["money_in"] == 5000)
    again = g.post("/api/auth/guest", json={}).json()["me"]
    check("same browser = same book (no second book)", again["shop"] == "Ada Stores" and not again["empty_book"], again)
    other = TestClient(web.app).post("/api/auth/guest", json={}).json()["me"]
    check("another phone gets its own empty book", other["empty_book"] and other["shop"] == "My shop", other)

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} login checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
