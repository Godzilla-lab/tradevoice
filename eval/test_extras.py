"""Lender link, pay links (bank + Paystack), automatic reminders, receipts, PIN lock, CSV export, offline worker.
No keys needed (WhatsApp and Paystack are faked).   python eval/test_extras.py
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"  # never let the real .env keys into a test
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "WHATSAPP_", "PAYSTACK_")) or k in ("AUTH_DEMO", "PUBLIC_URL"):
        os.environ.pop(k)
os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "shared.db"), BOOKS_DIR=tempfile.mkdtemp(),
                  ACCOUNTS_DB=os.path.join(tempfile.mkdtemp(), "a.db"), WHATSAPP_TOKEN="test", WHATSAPP_PHONE_ID="123",
                  WHATSAPP_VERIFY_TOKEN="v", WHATSAPP_DISPLAY_NUMBER="15551549545", TRADEVOICE_ADMIN="0",
                  AUTH_REQUIRED="1", AUTO_REMINDERS="0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient  # noqa: E402

import extras  # noqa: E402
import ledger  # noqa: E402
import web  # noqa: E402
import whatsapp  # noqa: E402

SENT = []
whatsapp.graph_post = lambda p: SENT.append(p) or {"messages": [{"id": "x"}]}
CHECKS = []


def check(name, ok, got=""):
    ok = bool(ok)
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def login(client, phone, shop="Chioma Stores"):
    SENT.clear()
    st = client.post("/api/auth/start", json={"phone": phone}).json()
    code = next(p["text"]["body"].split("*")[1] for p in SENT if p.get("type") == "text")
    client.post("/api/auth/verify", json={"login_id": st["login_id"], "code": code})
    client.post("/api/auth/me", json={"shop": shop, "lang": "English"})


def main():
    a = TestClient(web.app)
    login(a, "08031112222")
    PHONE = "2348031112222"

    # a customer with a phone, a credit sale due today -> receipt draft
    cid = a.post("/api/customers", json={"name": "Mama Tunde", "phone": "08035550000"}).json()["id"]
    today = dt.date.today().isoformat()
    r = a.post(f"/api/customers/{cid}/record", json={"type": "credit_sale", "amount": 45000, "item": "rice",
                                                     "due_date": today}).json()
    rc = [m for m in r["thread"] if m.get("kind") == "receipt"]
    check("🧾 receipt drafted after a credit sale", rc and "₦45,000" in rc[-1]["content"] and "owe" in rc[-1]["content"], rc)
    r = a.post(f"/api/customers/{cid}/record", json={"type": "payment_received", "amount": 5000}).json()
    rc = [m for m in r["thread"] if m.get("kind") == "receipt"]
    check("🧾 receipt after a payment shows the new balance", "₦5,000" in rc[-1]["content"] and "₦40,000" in rc[-1]["content"],
          rc[-1]["content"])

    # reminder carries a pay link
    r = a.post(f"/api/customers/{cid}/reminder", json={"lang": "English"}).json()
    m = re.search(r"/pay/([\w-]+)", r["message"] or "")
    from urllib.parse import unquote

    check("💸 reminder includes a pay link (in the text and the WhatsApp link)",
          m and "wa.me/2348035550000" in r["link"] and f"/pay/{m.group(1)}" in unquote(r["link"]), r)
    token = m.group(1)
    anon = TestClient(web.app)
    page = anon.get(f"/pay/{token}").text
    check("pay page opens without login and shows what is owed", "₦40,000" in page and "Mama Tunde" in page, page[:300])
    check("…no bank / Paystack yet -> says pay directly", "not added a way to pay" in page)
    check("bank number must be 10 digits", a.post("/api/bank", json={"account_number": "123"}).status_code == 400)
    a.post("/api/bank", json={"bank_name": "Moniepoint", "account_number": "0123456789", "account_name": "Chioma Okafor"})
    page = anon.get(f"/pay/{token}").text
    check("pay page shows the trader's bank details", "0123456789" in page and "I have paid" in page)
    anon.post(f"/pay/{token}/claimed")
    th = a.get(f"/api/customers/{cid}").json()["thread"]
    claim = [x for x in th if x.get("kind") == "payclaim"]
    check("'I have paid' -> the trader sees a claim to confirm", claim and claim[-1]["status"] == "claim:40000", claim)
    r = a.post(f"/api/customers/{cid}/confirm_paid", json={"message_id": claim[-1]["id"]}).json()
    check("trader confirms -> payment recorded, balance 0", r["customer"]["owes_me"] == 0, r["customer"])
    check("…and it can't be confirmed twice",
          a.post(f"/api/customers/{cid}/confirm_paid", json={"message_id": claim[-1]["id"]}).status_code == 404)
    check("pay page now says nothing to pay", "Nothing to pay" in anon.get(f"/pay/{token}").text)

    # Paystack: the debt settles by itself
    a.post(f"/api/customers/{cid}/record", json={"type": "credit_sale", "amount": 12000, "item": "beans"})
    r = a.post(f"/api/customers/{cid}/reminder", json={"lang": "English"}).json()
    token = re.search(r"/pay/([\w-]+)", r["message"]).group(1)
    os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_x"
    calls = []

    class Fake:
        ok = True

        def __init__(self, j):
            self._j = j

        def json(self):
            return self._j
    extras.requests.post = lambda url, **kw: calls.append(kw["json"]) or Fake(
        {"status": True, "data": {"authorization_url": "https://checkout.paystack.com/abc"}})
    check("with Paystack the pay page offers 'Pay now'", "Pay now" in anon.get(f"/pay/{token}").text)
    r = anon.post(f"/pay/{token}/paystack", follow_redirects=False)
    check("'Pay now' -> Paystack checkout for the right amount (kobo)", r.status_code == 303 and
          "paystack.com" in r.headers["location"] and calls[-1]["amount"] == 1200000, (r.status_code, calls))
    ref = calls[-1]["reference"]
    ev = json.dumps({"event": "charge.success", "data": {"reference": ref, "amount": 1200000}}).encode()
    bad = anon.post("/paystack/webhook", content=ev, headers={"x-paystack-signature": "nope"})
    check("forged Paystack webhook refused", bad.status_code == 401)
    sig = hmac.new(b"sk_test_x", ev, hashlib.sha512).hexdigest()
    anon.post("/paystack/webhook", content=ev, headers={"x-paystack-signature": sig})
    s = a.get(f"/api/customers/{cid}").json()["customer"]
    check("signed Paystack webhook -> paid, balance 0 by itself", s["owes_me"] == 0, s)
    anon.post("/paystack/webhook", content=ev, headers={"x-paystack-signature": sig})
    th = a.get(f"/api/customers/{cid}").json()["thread"]
    check("same webhook twice is not counted twice", sum(1 for x in th if x.get("engine") == "paylink") == 2, th)
    os.environ.pop("PAYSTACK_SECRET_KEY")

    # automatic reminders on the promised day
    cid2 = a.post("/api/customers", json={"name": "Oga Emeka", "phone": "08036660000"}).json()["id"]
    a.post(f"/api/customers/{cid2}/record", json={"type": "credit_sale", "amount": 21600, "item": "eggs",
                                                  "due_date": today})
    SENT.clear()
    n = extras.run_due_reminders(base="https://tv.example", send=True)
    th = a.get(f"/api/customers/{cid2}").json()["thread"]
    auto = [x for x in th if x.get("kind") == "reminder"]
    check("⏰ due today -> reminder drafted by itself, with a pay link", n >= 1 and auto and "/pay/" in auto[-1]["content"],
          (n, auto))
    summ = [p for p in SENT if p.get("type") == "text" and p["to"] == PHONE]
    check("…and the trader gets one WhatsApp summary", summ and "Oga Emeka" in summ[-1]["text"]["body"], SENT)
    check("…only once a day", extras.run_due_reminders(base="https://tv.example") == 0)

    # lender link
    check("share needs consent", a.post("/api/share", json={"days": 7, "consent": False}).status_code == 400)
    r = a.post("/api/share", json={"days": 7, "consent": True}).json()
    lt = r["url"].rsplit("/", 1)[1]
    v = anon.get(f"/lender/{lt}")
    check("🏦 lender opens the statement without logging in", v.status_code == 200 and "Record score" in v.text
          and "consent" in v.text and "Chioma Stores" in v.text, v.text[:300])
    check("…phone number is masked (last 4 only)", "2222" in v.text and PHONE not in v.text)
    sh = a.get("/api/shares").json()["shares"]
    check("views are counted", sh[0]["views"] == 1 and sh[0]["active"], sh)
    b = TestClient(web.app)
    login(b, "08097778888", "Other Shop")
    check("another trader can't stop my link", b.delete(f"/api/shares/{sh[0]['id']}").status_code == 404)
    check("another trader can't see my book", "Mama Tunde" not in json.dumps(b.get("/api/customers").json()))
    a.delete(f"/api/shares/{sh[0]['id']}")
    check("stopped link no longer works", "expired" in anon.get(f"/lender/{lt}").text)
    r = a.post("/api/share", json={"days": 1, "consent": True}).json()
    lt = r["url"].rsplit("/", 1)[1]
    with extras._db() as c:
        c.execute("UPDATE shares SET expires='2000-01-01T00:00:00+00:00' WHERE token_hash=?", (extras._h(lt),))
    check("expired link no longer works", "expired" in anon.get(f"/lender/{lt}").text)

    # CSV
    csv_r = a.get("/api/export.csv")
    check("📤 CSV export of my book", csv_r.status_code == 200 and "created_at,type,amount" in csv_r.text
          and "Mama Tunde" in csv_r.text and "attachment" in csv_r.headers.get("content-disposition", ""), csv_r.text[:200])
    check("CSV needs login", anon.get("/api/export.csv").status_code == 401)

    # PIN
    r = a.post("/api/auth/pin", json={"pin": "12a4"})
    check("PIN must be 4 numbers", r.status_code == 400)
    unlock = a.post("/api/auth/pin", json={"pin": "2468"}).json()["unlock"]
    check("🔒 with a PIN set, the book is locked without it", a.get("/api/today").status_code == 423)
    check("…me still loads (so the app can ask for the PIN)", a.get("/api/auth/me").json()["has_pin"])
    check("…unlocked with the header", a.get("/api/today", headers={"X-TV-Unlock": unlock}).status_code == 200)
    check("…a made-up unlock doesn't work", a.get("/api/today", headers={"X-TV-Unlock": "nope"}).status_code == 423)
    r = a.post("/api/auth/unlock", json={"pin": "0000"})
    check("wrong PIN -> tries left", r.status_code == 400 and "4 tries left" in r.text, r.text)
    for _ in range(4):
        a.post("/api/auth/unlock", json={"pin": "0000"})
    r = a.post("/api/auth/unlock", json={"pin": "2468"})
    check("5 wrong -> wait, even the right PIN", r.status_code == 429, r.text)
    extras.PIN_FAILS.clear()
    tok = a.post("/api/auth/unlock", json={"pin": "2468"}).json()["unlock"]
    check("right PIN -> new unlock", a.get("/api/today", headers={"X-TV-Unlock": tok}).status_code == 200)
    check("turning the PIN off needs the unlock", a.delete("/api/auth/pin").status_code in (403, 423))
    a.delete("/api/auth/pin", headers={"X-TV-Unlock": tok})
    check("PIN off -> open again", a.get("/api/today").status_code == 200)

    # offline
    sw = anon.get("/sw.js")
    check("📴 offline worker served at the root", sw.status_code == 200 and "caches" in sw.text
          and sw.headers.get("service-worker-allowed") == "/")

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} extras checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
