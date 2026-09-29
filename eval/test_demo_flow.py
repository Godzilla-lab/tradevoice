"""The 90-second demo, end to end through the API (docs: TRADEVOICE_UIUX_CHANGES §23 + definition of done).
A fresh trader logs in -> says a credit sale -> sees what TradeVoice understood -> changes it -> saves -> the customer
owes -> "who owes me the most?" -> reminder with a pay link -> a Yoruba question answered from the same book.
No keys needed (rules only; WhatsApp faked).   python eval/test_demo_flow.py
"""
import os
import re
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "WHATSAPP_", "PAYSTACK_")) or k in ("AUTH_DEMO", "PUBLIC_URL"):
        os.environ.pop(k)
os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "shared.db"), BOOKS_DIR=tempfile.mkdtemp(),
                  ACCOUNTS_DB=os.path.join(tempfile.mkdtemp(), "a.db"), AUTH_DEMO="1", TRADEVOICE_ADMIN="0",
                  AUTH_REQUIRED="1", AUTO_REMINDERS="0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import web  # noqa: E402

CHECKS = []


def check(name, ok, got=""):
    ok = bool(ok)
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def main():
    c = TestClient(web.app)
    st = c.post("/api/auth/start", json={"phone": "0803 555 0101"}).json()
    c.post("/api/auth/verify", json={"login_id": st["login_id"], "code": st["demo_code"]})
    me = c.post("/api/auth/me", json={"shop": "Chioma Stores", "lang": "English"}).json()
    check("fresh trader logs in with a phone number, empty book", me["empty_book"] and me["shop"] == "Chioma Stores", me)
    say = lambda text, lang="English": c.post("/api/message", json={"session": "demo", "text": text, "lang": lang}).json()  # noqa: E731

    # 1. speak -> what TradeVoice understood, field by field; nothing saved yet
    r = say("I sell Mama Tunde two bags of rice for forty-five thousand. She go pay Friday")
    d = r["draft"]
    check("draft: customer, amount, item, quantity, type, due date", d and d["customer"] == "Mama Tunde" and d["amount"] == 45000
          and d["item"] == "rice" and d["quantity"] == 2 and d["type"] == "credit_sale" and d["due_date"], d)
    check("draft: Mama Tunde marked as a new customer", d["new_customer"], d)
    check("nothing saved before confirming", c.get("/api/debts").json()["owed_to_me"] == [])

    # 2. Change -> fix the amount, still waiting for Save
    r = c.post("/api/draft", json={"session": "demo", "amount": 46000}).json()
    check("Change: amount fixed, still a draft", r["draft"]["amount"] == 46000 and r["pending"], r)
    check("Change refuses nonsense", c.post("/api/draft", json={"session": "demo", "amount": -5}).status_code == 400)

    # 3. Save -> the ledger updates
    r = say("yes")
    check("Save -> saved, no draft left", not r["pending"] and not r["draft"] and "46,000" in r["text"], r)
    owed = c.get("/api/debts").json()["owed_to_me"]
    check("Mama Tunde now owes ₦46,000", owed and owed[0]["customer"] == "Mama Tunde" and owed[0]["balance"] == 46000, owed)

    # 4. uncertainty: no amount heard -> the card asks, and nothing is invented
    r = say("Alhaji Sani dey owe me")
    check("no amount heard -> amount marked unsure, not invented", r["draft"] and r["draft"]["amount"] is None
          and "amount" in r["draft"]["unsure"], r)
    r = say("no")
    check("Cancel -> nothing saved", len(c.get("/api/debts").json()["owed_to_me"]) == 1)

    # 5. another debt in Pidgin, then "who owes me the most?"
    say("Iya Bisi collect indomie 20k on credit")
    say("yes")
    r = c.post("/api/assist", data={"screen": "owes", "lang": "English", "session": "demo",
                                    "text": "Who owes me the most?"}).json()
    check("Ask 'who owes me the most?' -> exact, from the book", "Mama Tunde" in r["text"] and "46,000" in r["text"]
          and r["engine"] == "book:exact", r)

    # 6. reminder: prepared, reviewed, sent by the trader (with a pay link)
    cid = next(x["id"] for x in c.get("/api/customers").json()["customers"] if x["name"] == "Mama Tunde")
    r = c.post(f"/api/customers/{cid}/reminder", json={"lang": "English"}).json()
    check("reminder drafted with the amount and a pay link", "₦46,000" in r["message"] and "/pay/" in r["message"], r)
    th = c.get(f"/api/customers/{cid}").json()["thread"]
    rem = [x for x in th if x.get("kind") == "reminder"][-1]
    check("reminder waits as a draft (never sent automatically)", rem["status"] == "draft", rem)

    # 7. switch language: Yoruba question on the same book
    say("Mo jẹ Alhaji Sani ẹgbẹ̀rún mẹ́wàá", "Yoruba")
    say("bẹ́ẹ̀ni", "Yoruba")
    r = say("Ṣé mo ní gbèsè lọ́wọ́ Alhaji?", "Yoruba")
    check("Yoruba question answered in Yoruba from the same book", r["lang"] == "Yoruba" and "10,000" in r["text"], r)
    check("language switch did not reset the book", c.get("/api/debts").json()["owed_to_me"][0]["balance"] in (46000, 20000))

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} demo-flow checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
