"""TradeVoice 2.0 accounts (src/v2.py): WhatsApp code, sign-up, password, log in, delete with 90 days to undo, and the
real erase after 90 days (everything for the number), erase sooner on request, and the privacy notice. No keys needed (WhatsApp is faked). Made-up numbers only.

python eval/test_accounts.py
"""
import datetime as dt
import hashlib
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"  # never let the real .env keys into a test
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "WHATSAPP_", "TERMII_", "TELEGRAM_", "SMS_")) or k in ("AUTH_DEMO", "TV_PUBLIC", "SIGNUP_CODE"):
        os.environ.pop(k)
os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "shared.db"), BOOKS_DIR=tempfile.mkdtemp(),
                  ACCOUNTS_DB=os.path.join(tempfile.mkdtemp(), "a.db"), TRADEVOICE_ADMIN="0", AUTH_REQUIRED="1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import ledger  # noqa: E402
import v2  # noqa: E402
import web  # noqa: E402
import whatsapp  # noqa: E402

SENT = []
whatsapp.graph_post = lambda p: SENT.append(p) or {"messages": [{"id": "x"}]}
CHECKS = []
PHONE, FULL = "08030000521", "2348030000521"


def check(name, ok, got=""):
    ok = bool(ok)
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:300]}"))


def pw(p):   # the page sends a hash of the password, never the password
    return hashlib.sha256(("pw:" + p).encode()).hexdigest()


def code_for(c, purpose):
    whatsapp.saw(FULL)   # the trader wrote to the bot today: Meta's 24-hour window is open
    r = c.post("/api/auth/v2/code/start", json={"phone": PHONE, "purpose": purpose})
    body = SENT[-1]["text"]["body"] if SENT else ""
    code = "".join(ch for ch in body.split("*")[1] if ch.isdigit()) if "*" in body else ""
    return r, code


def main():
    c = TestClient(web.app)

    # nothing can send a code and SIGNUP_CODE=required: sign-up waits, no code is made up on screen
    os.environ["SIGNUP_CODE"] = "required"
    r = c.post("/api/auth/v2/code/start", json={"phone": PHONE, "purpose": "signup"})
    check("SIGNUP_CODE=required and no WhatsApp or SMS: sign-up waits (503), nothing on screen", r.status_code == 503, r.text)
    os.environ.pop("SIGNUP_CODE")

    # no WhatsApp, no SMS (the pilot this week): sign-up goes straight on with number + password, no code
    other = "08030000522"
    r = c.post("/api/auth/v2/code/start", json={"phone": other, "purpose": "signup"})
    d = r.json()
    check("no code channel: sign-up needs no code (nocode), and no code on screen", r.status_code == 200 and d["nocode"]
          and not d["demo_code"] and not d["sent"], r.text)
    s = c.post("/api/auth/v2/signup", json={"login_id": d["login_id"], "pw": pw("Kola-pass-2026"), "name": "Kola Testtrader",
                                           "biz": "Kola Test Stores"})
    check("…and the account is made with that number and password", s.status_code == 200, s.text)
    check("…a reset with that ticket is refused (it was for sign-up only)",
          c.post("/api/auth/v2/reset", json={"login_id": d["login_id"], "pw": pw("Other-pass-2026")}).status_code == 400)
    check("…the same number can't sign up again (409): nobody takes over a book",
          c.post("/api/auth/v2/code/start", json={"phone": other, "purpose": "signup"}).status_code == 409)
    for purpose in ("reset", "login"):
        check(f"…'{purpose}' by code needs a code, and none can be sent: 503, no code-free way in",
              c.post("/api/auth/v2/code/start", json={"phone": other, "purpose": purpose}).status_code == 503)
    check("…the page is told: no codes, sign-up without one", v2.channels()["codes"] == "" and v2.channels()["nocode"])
    page = c.get("/app").text
    check("…and the page carries that flag (window.TV_CH)", 'window.TV_CH={"codes": ""' in page and '"nocode": true' in page,
          page[:300])
    c.post("/api/auth/v2/logout")

    os.environ.update(WHATSAPP_TOKEN="test", WHATSAPP_PHONE_ID="123")
    r, code = code_for(c, "signup")
    check("code goes to the trader's WhatsApp, not the screen",
          r.status_code == 200 and not r.json()["demo_code"] and SENT[-1]["to"] == FULL and len(code) == 6, r.text)
    lid = r.json()["login_id"]
    check("a wrong code is refused", c.post("/api/auth/v2/code/check",
                                             json={"login_id": lid, "code": "000000" if code != "000000" else "111111"}).status_code == 400)
    check("the right code passes", c.post("/api/auth/v2/code/check", json={"login_id": lid, "code": code}).status_code == 200)
    r = c.post("/api/auth/v2/signup", json={"login_id": lid, "pw": pw("Market2026x"), "name": "Ada Testtrader",
                                           "biz": "Ada Test Stores", "type": "", "mk": "Test Market"})
    check("sign-up makes the account and logs in", r.status_code == 200 and r.json()["me"]["biz"] == "Ada Test Stores", r.text)
    check("the same number can't sign up twice",
          c.post("/api/auth/v2/code/start", json={"phone": PHONE, "purpose": "signup"}).status_code == 409)

    r = c.post("/api/message", json={"session": "hi", "text": "hello", "lang": "English"}).json()
    check("personal: 'hello' greets the trader by name", r["text"].startswith("Hello, Ada."), r["text"])
    import accounts
    import assistant
    import ledger as L
    tok = L.use_book(FULL)
    who = assistant.who_line()
    L.done_with_book(tok)
    check("personal: the AI is told who it is talking to (name, business, market)",
          "Ada" in who and "Ada Test Stores" in who and "Test Market" in who, who)
    c.post("/api/customers", json={"name": "Iya Bisi"})
    ledger_file = ledger.book_file(FULL)
    check("the trader has their own book file", os.path.exists(ledger_file), ledger_file)

    # password
    r = c.post("/api/v2/password", json={"current": pw("nope-nope"), "new": pw("Balogun2027y")})
    check("password change: wrong current password refused", r.status_code == 401 and r.json()["error"] == "wrong", r.text)
    r = c.post("/api/v2/password", json={"current": pw("Market2026x"), "new": pw("Market2026x")})
    check("password change: the same password refused", r.status_code == 400 and r.json()["error"] == "same", r.text)
    r = c.post("/api/v2/password", json={"current": pw("Market2026x"), "new": pw("Balogun2027y")})
    check("password change works", r.status_code == 200, r.text)

    # log out, log in
    c.post("/api/auth/v2/logout")
    check("logged out: /api/v2/me refused", c.get("/api/v2/me").status_code == 401)
    r = c.post("/api/auth/v2/login", json={"phone": PHONE, "pw": pw("Market2026x")})
    check("old password refused", r.status_code == 401, r.text)
    r = c.post("/api/auth/v2/login", json={"phone": PHONE, "pw": pw("Balogun2027y")})
    check("new password logs in", r.status_code == 200 and c.get("/api/v2/me").status_code == 200, r.text)
    other = TestClient(web.app)
    for _ in range(5):
        other.post("/api/auth/v2/login", json={"phone": PHONE, "pw": pw("guess-guess")})
    r = other.post("/api/auth/v2/login", json={"phone": PHONE, "pw": pw("Balogun2027y")})
    check("5 wrong passwords: locked for a while, even the right one waits", r.status_code == 429, r.text)
    v2.FAILS.clear()

    # delete with 90 days to undo (the delete screen and the privacy notice say so)
    r = c.post("/api/v2/delete", json={"biz": "Wrong Name", "pw": pw("Balogun2027y")})
    check("delete: the business name must match", r.status_code == 400, r.text)
    r = c.post("/api/v2/delete", json={"biz": "ada test stores", "pw": pw("guess-guess")})
    check("delete: the password must match", r.status_code == 401, r.text)
    r = c.post("/api/v2/delete", json={"biz": "ada test stores", "pw": pw("Balogun2027y")})
    days = (dt.datetime.fromisoformat(r.json()["delAt"]) - v2._now()).days if r.status_code == 200 else None
    check("delete: keeps the account 90 days", days in (89, 90), r.text)
    check("within the 90 days nothing is erased", v2.purge_deleted() == [] and os.path.exists(ledger_file))
    c.post("/api/v2/restore", json={})
    check("undo: the account is back", c.get("/api/v2/me").json()["delAt"] is None)

    c.post("/api/v2/delete", json={"biz": "Ada Test Stores", "pw": pw("Balogun2027y")})
    import extras
    with extras._db() as db:   # a share link and a pay link the trader made earlier
        db.execute("INSERT INTO shares (token_hash, phone, created_at) VALUES ('t1', ?, '2026-10-01')", (FULL,))
        db.execute("INSERT INTO paylinks (token_hash, phone, customer_id, amount) VALUES ('p1', ?, 1, 500)", (FULL,))
    # while it waits: no daily WhatsApp summary, and the bot says it is closed without touching the book
    extras.run_due_reminders(send=False)
    with extras._db() as db:
        ran = db.execute("SELECT 1 FROM auto_runs WHERE phone=?", (FULL,)).fetchone()
    check("closed account: no daily summary", ran is None)
    before = len(SENT)
    import sqlite3
    with sqlite3.connect(ledger_file) as b:
        n0 = b.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    whatsapp._safe({"from": FULL, "type": "text", "id": "w1", "text": {"body": "sold rice 5000"}})
    said = " ".join(str(p) for p in SENT[before:])
    with sqlite3.connect(ledger_file) as b:
        n1 = b.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    check("closed account: the bot says it is closed and when it will be deleted",
          "Your account is closed" in said and str(v2.closing(FULL).year) in said, said)
    check("closed account: the book is not touched", n1 == n0, (n0, n1))
    with v2._db() as db:   # 91 days later
        db.execute("UPDATE users SET delete_at=? WHERE phone=?", ((v2._now() - dt.timedelta(days=1)).isoformat(), FULL))
    check("after 90 days the account is erased", v2.purge_deleted() == [FULL])
    check("…its book file is gone", not os.path.exists(ledger_file), ledger_file)
    with extras._db() as db:
        left = [t for t in ("shares", "paylinks", "auto_runs", "users", "sessions")
                if db.execute(f"SELECT 1 FROM {t} WHERE phone=?", (FULL,)).fetchone()]
    check("…and every row for the number (links, sessions, profile)", not left, left)
    check("…it can't log in, and its session is dead", c.get("/api/v2/me").status_code == 401 and c.post(
        "/api/auth/v2/login", json={"phone": PHONE, "pw": pw("Balogun2027y")}).status_code == 404)
    check("…and the number can sign up fresh", c.post("/api/auth/v2/code/start",
                                                      json={"phone": PHONE, "purpose": "signup"}).status_code == 200)

    # team-created accounts (scripts/add_account.py), while WhatsApp codes can't be sent
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import add_account
    phone, temp = add_account.create("08030000531", "Bola Testtrader", "Bola Test Stores", "Provisions")
    check("add_account: makes the account with a temporary password", phone == "2348030000531" and len(temp) >= 12, temp)
    t = TestClient(web.app)
    r = t.post("/api/auth/v2/login", json={"phone": "08030000531", "pw": add_account.page_hash(temp)})
    check("add_account: the tester logs in with phone + that password",
          r.status_code == 200 and r.json()["me"]["biz"] == "Bola Test Stores" and r.json()["me"]["type"] == "Provisions", r.text)
    try:
        add_account.create("08030000531", "X Y", "Z W")
        check("add_account: refuses a number that already has an account", False)
    except SystemExit:
        check("add_account: refuses a number that already has an account", True)
    # erase sooner when the owner asks (scripts/erase_account.py), and only with --yes
    import erase_account
    p3, _ = add_account.create("08030000541", "Chika Testtrader", "Chika Test Stores")
    book3 = ledger.book_file(p3)
    open(book3, "a").close()
    check("erase_account: without --yes nothing is erased",
          erase_account.main(["08030000541"]) == 1 and v2._has_account(p3) and os.path.exists(book3))
    check("erase_account --yes: account and book gone",
          erase_account.main(["08030000541", "--yes"]) == 0 and not v2._has_account(p3) and not os.path.exists(book3))

    # the privacy notice: a real page, saying what the delete screen says, with the team's contact
    os.environ["PRIVACY_CONTACT"] = "privacy@example.com <b>"
    page = TestClient(web.app).get("/privacy")
    os.environ.pop("PRIVACY_CONTACT")
    check("privacy notice: a page that states the 90 days, the contact (escaped) and the N-ATLaS sentence",
          page.status_code == 200 and "90 days" in page.text and "privacy@example.com &lt;b&gt;" in page.text
          and "{{" not in page.text and "powered by Awarri Technologies" in page.text, page.text[:300])
    app_page = open(os.path.join(os.path.dirname(__file__), "..", "web", "app.html"), encoding="utf-8").read()
    check("the app's delete screen and privacy links match", "deleted after 90 days" in app_page
          and "7 days to cancel" not in app_page and 'priv:()=>open("/privacy"' in app_page)

    p2, _ = add_account.create("08030000599", "mama ngozi testtrader", "Ngozi Test Foods")
    check("personal: titles keep the name after them ('Mama Ngozi', not 'Mama'), and a lowercase name is tidied",
          accounts.trader(p2).get("name") == "Mama Ngozi", accounts.trader(p2))
    _, temp2 = add_account.reset("08030000531")
    check("add_account --reset: the old password stops working, the new one works, other phones logged out",
          t.get("/api/v2/me").status_code == 401
          and t.post("/api/auth/v2/login", json={"phone": "08030000531", "pw": add_account.page_hash(temp)}).status_code == 401
          and t.post("/api/auth/v2/login", json={"phone": "08030000531", "pw": add_account.page_hash(temp2)}).status_code == 200)

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} account checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
