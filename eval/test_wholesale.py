"""Wholesale features: credit limit, margin per item, cheapest supplier, per-customer statement, repeat-order drafts.
No keys needed.   python eval/test_wholesale.py
"""
import datetime as dt
import os
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

import ledger  # noqa: E402
import web  # noqa: E402

CHECKS = []
TODAY = dt.date.today()


def check(name, ok, got=""):
    ok = bool(ok)
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def main():
    c = TestClient(web.app)
    st = c.post("/api/auth/start", json={"phone": "0803 777 0101"}).json()
    c.post("/api/auth/verify", json={"login_id": st["login_id"], "code": st["demo_code"]})
    c.post("/api/auth/me", json={"shop": "Bisi Wholesale", "lang": "English"})
    ledger.use_book("2348037770101")   # write the test history straight into this trader's book
    at = lambda days, h=9: dt.datetime.combine(TODAY - dt.timedelta(days=days), dt.time(h, 0))  # noqa: E731
    say = lambda text: c.post("/api/message", json={"session": "w", "text": text, "lang": "English"}).json()  # noqa: E731

    # ---- 1. credit limit
    cid = c.post("/api/customers", json={"name": "Iya Bisi", "phone": "08031230000", "credit_limit": 30000}).json()["id"]
    check("limit saved with the new customer", ledger.get_customer(cid)["credit_limit"] == 30000)
    c.post(f"/api/customers/{cid}/record", json={"type": "credit_sale", "amount": 20000, "item": "indomie"})
    r = say("Iya Bisi collect 15k on credit")
    check("draft over the limit is flagged on the card", r["draft"]["limit"] and r["draft"]["limit"]["over"]
          and r["draft"]["limit"]["after"] == 35000, r["draft"])
    check("…and said in the reply (text + voice)", "above the limit" in r["text"] and "Sell anyway" in r["text"], r["text"])
    say("no")
    rr = c.post(f"/api/customers/{cid}/record", json={"type": "credit_sale", "amount": 15000})
    check("recording over the limit asks first (409 + warning)", rr.status_code == 409 and "limit" in rr.json()["warning"],
          rr.text)
    rr = c.post(f"/api/customers/{cid}/record", json={"type": "credit_sale", "amount": 15000, "over_limit_ok": True})
    check("'Sell anyway' records it", rr.status_code == 200 and rr.json()["customer"]["owes_me"] == 35000, rr.text)
    check("payments are never blocked by the limit",
          c.post(f"/api/customers/{cid}/record", json={"type": "payment_received", "amount": 5000}).status_code == 200)
    r = say("Mama Tunde limit 50k")
    mt = [x for x in ledger.find_customers("Mama Tunde")][0]
    check("limit set by voice/text", mt["credit_limit"] == 50000 and "50,000" in r["text"], r["text"])
    say("Mama Tunde limit off")
    check("…and removed", not ledger.get_customer(mt["id"])["credit_limit"])

    # ---- 2 + 3. margins and cheapest supplier (quantities said)
    add = lambda rec, when: ledger.add_entry(rec, raw_text="(test)", created_at=when)  # noqa: E731
    add({"type": "credit_purchase", "item": "rice", "unit": "bag", "quantity": 10, "amount": 120000, "customer": "Alhaji Sani"}, at(9))
    add({"type": "expense", "item": "rice", "unit": "bags", "quantity": 5, "amount": 62500, "customer": "Alhaja Kudi"}, at(8))
    add({"type": "sale", "item": "rice", "unit": "bag", "quantity": 2, "amount": 30000}, at(6))
    add({"type": "credit_sale", "item": "rice", "unit": "bag", "quantity": 1, "amount": 15000, "customer": "Mama Tunde"}, at(5))
    add({"type": "expense", "item": "transport", "amount": 1500}, at(5))
    ins = c.get("/api/insights").json()
    rice = next((m for m in ins["margins"] if m["item"] == "rice"), None)
    check("margin: sell ₦15,000 vs buy ₦12,167 per bag -> ₦2,833", rice and rice["sell"] == 15000 and rice["buy"] == 12167
          and rice["margin"] == 2833 and rice["unit"] == "bag", ins["margins"])
    check("'bag' and 'bags' count as the same unit; transport is not an item", len(ins["margins"]) == 1)
    sup = next((x for x in ins["suppliers"] if x["item"] == "rice"), None)
    check("cheapest supplier: Alhaji Sani ₦12,000 < Alhaja Kudi ₦12,500, save ₦500", sup and
          [(o["supplier"], o["price"]) for o in sup["offers"]] == [("Alhaji Sani", 12000), ("Alhaja Kudi", 12500)]
          and sup["saving"] == 500, sup)
    a = c.post("/api/assist", data={"screen": "insights", "lang": "English", "session": "w",
                                    "text": "What is my margin on rice?"}).json()
    check("Ask: margin on rice, exact", "₦2,833" in a["text"] and a["engine"] == "book:exact", a)
    a = c.post("/api/assist", data={"screen": "insights", "lang": "Pidgin", "session": "w",
                                    "text": "Who dey sell rice cheap pass?"}).json()
    check("Ask (Pidgin): cheapest rice supplier", "Alhaji Sani" in a["text"] and "cheapest" in a["text"], a)

    # ---- 4. per-customer statement
    r = c.post(f"/api/customers/{cid}/statement").json()
    stm = [m for m in r["thread"] if m.get("kind") == "statement"][-1]
    check("statement drafted in the conversation (never sent by itself)", stm["status"] == "draft", stm)
    check("…shows what they owe, the items and a pay link", "₦30,000" in stm["content"] and "indomie" in stm["content"]
          and "/pay/" in stm["content"], stm["content"])
    r = say("send Iya Bisi her statement")
    check("statement by chat: ready to forward on WhatsApp", r.get("message") and "wa.me/2348031230000" in r["link"], r)

    # ---- 5. repeat orders (same customer + item on today's weekday, 3 weeks running)
    mid = ledger.resolve_customer("Mama Tunde")
    for w in (21, 14, 7):
        add({"type": "sale", "item": "eggs", "unit": "crate", "quantity": 4, "amount": 21600, "customer_id": mid}, at(w, 10))
    reps = c.get("/api/repeats").json()["repeats"]
    check("usual order found for today", reps and reps[0]["customer"] == "Mama Tunde" and reps[0]["quantity"] == 4
          and reps[0]["amount"] == 21600, reps)
    before = len(ledger.entries(TODAY))
    r = c.post("/api/repeats/draft", json={"session": "w", "lang": "English", "customer_id": mid, "item": "eggs"}).json()
    check("'Record it' makes a DRAFT (confirmation card), nothing saved", r["draft"] and r["draft"]["quantity"] == 4
          and len(ledger.entries(TODAY)) == before and "usually buys" in r["text"], r)
    say("yes")
    check("saved after yes, and no longer suggested today", len(ledger.entries(TODAY)) == before + 1
          and not c.get("/api/repeats").json()["repeats"])
    r = say("Mama Tunde usual")
    check("'Mama Tunde usual' by chat drafts it too", r["draft"] and r["draft"]["item"] == "eggs", r)
    say("no")

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} wholesale checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
