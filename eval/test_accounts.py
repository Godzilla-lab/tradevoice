"""TradeVoice 2.0 accounts (src/v2.py): WhatsApp code, sign-up, password, log in, delete with 7 days to undo, and the
real erase after 7 days. No keys needed (WhatsApp is faked). Made-up numbers only.

python eval/test_accounts.py
"""
import datetime as dt
import hashlib
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"  # never let the real .env keys into a test
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith("LOCAL_") or k.startswith("WHATSAPP_") or k in ("AUTH_DEMO", "TV_PUBLIC"):
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
    r = c.post("/api/auth/v2/code/start", json={"phone": PHONE, "purpose": purpose})
    body = SENT[-1]["text"]["body"] if SENT else ""
    code = "".join(ch for ch in body.split("*")[1] if ch.isdigit()) if "*" in body else ""
    return r, code


def main():
    c = TestClient(web.app)

    # no WhatsApp and no demo mode: no code is made up on screen
    r = c.post("/api/auth/v2/code/start", json={"phone": PHONE, "purpose": "signup"})
    check("no WhatsApp: sign-up code can't be sent (503), nothing on screen", r.status_code == 503, r.text)

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

    # delete with 7 days to undo
    r = c.post("/api/v2/delete", json={"biz": "Wrong Name", "pw": pw("Balogun2027y")})
    check("delete: the business name must match", r.status_code == 400, r.text)
    r = c.post("/api/v2/delete", json={"biz": "ada test stores", "pw": pw("guess-guess")})
    check("delete: the password must match", r.status_code == 401, r.text)
    r = c.post("/api/v2/delete", json={"biz": "ada test stores", "pw": pw("Balogun2027y")})
    days = (dt.datetime.fromisoformat(r.json()["delAt"]) - v2._now()).days if r.status_code == 200 else None
    check("delete: asks for 7 days' grace", days == 6 or days == 7, r.text)
    check("within the 7 days nothing is erased", v2.purge_deleted() == [] and os.path.exists(ledger_file))
    c.post("/api/v2/restore", json={})
    check("undo: the account is back", c.get("/api/v2/me").json()["delAt"] is None)

    c.post("/api/v2/delete", json={"biz": "Ada Test Stores", "pw": pw("Balogun2027y")})
    with v2._db() as db:   # 8 days later
        db.execute("UPDATE users SET delete_at=? WHERE phone=?", ((v2._now() - dt.timedelta(days=1)).isoformat(), FULL))
    check("after 7 days the account is erased", v2.purge_deleted() == [FULL])
    check("…its book file is gone", not os.path.exists(ledger_file), ledger_file)
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
    _, temp2 = add_account.reset("08030000531")
    check("add_account --reset: the old password stops working, the new one works, other phones logged out",
          t.get("/api/v2/me").status_code == 401
          and t.post("/api/auth/v2/login", json={"phone": "08030000531", "pw": add_account.page_hash(temp)}).status_code == 401
          and t.post("/api/auth/v2/login", json={"phone": "08030000531", "pw": add_account.page_hash(temp2)}).status_code == 200)

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} account checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
