"""Corrections the way traders say them (from the team's WhatsApp test, 27 Sep): the fix updates the draft that is
waiting for "yes" instead of starting a new one; Pidgin "X no be Y" / "no be Y, na X" keeps the right number; the
trader never sees technical notes.   python eval/test_corrections.py   (no keys; the AI is faked where needed)
"""
import datetime as dt
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith("LOCAL_"):
        os.environ.pop(k)
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import converse  # noqa: E402
import extract  # noqa: E402

CHECKS = []
TODAY = dt.date(2026, 9, 27)


def check(name, ok, got=""):
    ok = bool(ok)
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:300]}"))


def main():
    pa = extract.parse_amount
    check("'2000 no be 20000 na 2000' -> 2000", pa("I talk say 2000 no be 20000 na 2000 Oga Chinedu suppose pay me") == 2000)
    check("'no be 20000, na 2000' -> 2000", pa("no be 20000, na 2000") == 2000)
    check("'20k not 25k' -> 20k", pa("20k not 25k") == 20000)
    check("'not 25k but 20k' -> 20k", pa("not 25k but 20k") == 20000)
    check("'10k, sorry no, 12k' still -> 12k", pa("10k, sorry no, 12k") == 12000)
    check("stutter '20000 20000 naira' -> 20000", pa("I say 20000 20000 naira") == 20000)
    r = extract.rule_extract("Oga Chinedu suppose pay me 2000 for the 50 pairs of shoe wey he come collect", TODAY)
    check("'50 pairs of shoe' -> 50 pair shoe", (r["quantity"], r["unit"], r["item"]) == (50, "pair", "shoe"), r)
    check("'Alhaji collect…' -> customer Alhaji (not 'Alhaji Collect')",
          extract.rule_extract("Alhaji collect 5 bags cement 30k on credit")["customer"] == "Alhaji")
    r = extract.rule_extract("Iya Bisi paid 10000", TODAY)   # found by eval/browser_test.cjs: was a cash sale
    check("'Iya Bisi paid 10000' -> she paid me back", (r["type"], r["customer"], r["amount"]) == ("payment_received", "Iya Bisi", 10000), r)
    r = extract.rule_extract("Iya Bisi paid 5000 for 2 bags of rice", TODAY)
    check("'… paid 5000 for 2 bags of rice' -> still a cash sale", r["type"] == "sale", r)

    # the AI (Brev) got the correction wrong: the rules' kept number wins, no scary note
    extract.llm.available = lambda *a, **k: True
    extract.llm_extract = lambda t, today, vocab: ({"type": "credit_sale", "amount": 20000, "customer": "Oga Chinedu",
                                                    "item": "shoe", "quantity": 50, "unit": "pair", "due_date": None,
                                                    "confidence": 0.9, "note": "uncertain amount"}, "fake")
    rec, _ = extract.extract("I talk say 2000 no be 20000 na 2000 Oga Chinedu suppose pay me", TODAY)
    check("AI said 20,000 for '2000 no be 20000' -> 2,000", rec["amount"] == 2000, rec)
    extract.llm.available = lambda *a, **k: False

    st = converse.new_state()
    say = lambda m: converse.reply(m, st, today=TODAY)  # noqa: E731
    r = say("I say 20000 20000 naira")
    check("no technical text shown to the trader", "AI said" not in r["text"] and "rules heard" not in r["text"], r["text"])
    r = say("I talk say 2000 no be 20000 na 2000 Oga Chinedu suppose pay me wey he never pay me for the 50 pairs of shoe")
    p = st["pending"]
    check("the correction updates the waiting draft", p["amount"] == 2000 and p["customer"] == "Oga Chinedu"
          and p["type"] == "credit_sale" and ("changed" in r["english"].lower() if r.get("english") else "changed" in r["text"].lower()), r)
    r = say("make am 2500")
    check("'make am 2500' -> amount 2,500, customer kept", st["pending"]["amount"] == 2500
          and st["pending"]["customer"] == "Oga Chinedu", st["pending"])
    r = say("just 3000")
    check("a bare amount while a draft waits = the right amount", st["pending"]["amount"] == 3000, st["pending"])
    say("yes")
    check("saved once, with the corrected amount", st["pending"] is None)
    say("Mama Tunde owe me 45k for rice")
    r = say("Iya Bisi has not paid 20k")
    check("a different customer with an amount = a new record, and it says the old one wasn't saved",
          st["pending"]["customer"] == "Iya Bisi" and "not saved" in (r.get("english") or r["text"]), r)
    say("no")
    say("Alhaji collect 5 bags cement 30k on credit")
    say("no be 30k, na 35k")
    check("'no be 30k, na 35k' updates the draft to 35k", st["pending"]["amount"] == 35000 and st["pending"]["item"] == "cement",
          st["pending"])

    say("no")
    # said out loud in the live conversation, answers come with a little more
    say("Mama Tunde owe me 45k for rice")
    say("Yes please, save it.")
    check("spoken 'Yes please, save it.' saves", st["pending"] is None)
    say("Iya Bisi paid 5000")
    say("No, leave it.")
    check("spoken 'No, leave it.' cancels", st["pending"] is None)
    say("Alhaji collect 5 bags cement 30k on credit")
    say("yes she will pay friday")
    check("'yes' + new details is not a bare yes: nothing saved by accident", st["pending"] is not None, st["pending"])

    say("no")
    # part payment with a promise for the rest: money IN now, never a new debt (it was saved as a ₦10,000 debt)
    for line in ("Iya Bisi paid 10000, she will pay the rest Friday", "Mama Tunde don pay 10k, she go pay the balance Friday"):
        say(line)
        p = st["pending"] or {}
        check(f"'{line}' -> she paid ₦10,000 (not a new debt)", p.get("type") == "payment_received"
              and p.get("amount") == 10000, p)
        say("no")
    say("Mama Tunde took rice 45000, she paid 10000, she will pay the rest Friday")
    check("goods taken in the same breath stay a credit sale", (st["pending"] or {}).get("type") == "credit_sale",
          st["pending"])

    say("no")
    # E14 memory: nicknames, "did you mean", usual prices (all in this trader's own book)
    import ledger
    for line in ("Mama Tunde took 2 bags of rice 90000 on credit", "yes", "Mama Titi owes me 5000", "yes",
                 "Hajiya Amina owes me 20000", "yes", "Iya Bisi took 1 bag of rice 45000 on credit", "yes"):
        say(line)
    r = say("Mama T took 1 bag of rice 45000 on credit")
    check("'Mama T' with Mama Tunde and Mama Titi in the book -> 'Which Mama T?'", "Which Mama T" in r["text"], r["text"])
    r = say("Mama Tunde")
    check("…saying the name picks her", st["pending"]["customer"] == "Mama Tunde", st["pending"])
    say("no")
    r = say("Mama T took 1 bag of rice 45000 on credit")
    check("…and next time 'Mama T' is Mama Tunde without asking (remembered in the book)",
          "Which" not in r["text"] and st["pending"]["customer"] == "Mama Tunde", r["text"])
    say("no")
    r = converse.reply("How much does Mama T owe?", st, today=dt.date.today())   # (records are saved today)
    check("questions understand the nickname too", "Mama Tunde owes you" in r["text"], r["text"])
    r = say("Hajia Aminat took 1 bag of rice 45000 on credit")
    check("a name close to one in the book -> 'Did you mean Hajiya Amina?' (not a second customer)",
          "Did you mean Hajiya Amina" in r["text"], r["text"])
    say("yes")
    check("…'yes' picks Hajiya Amina", st["pending"]["customer"] == "Hajiya Amina", st["pending"])
    say("no")
    r = say("Hajiya Aminah owes me 1000")
    say("no")
    check("…'no' after 'Did you mean' = a new customer with the name said",
          "Did you mean" in r["text"] and st["pending"] and st["pending"]["customer"] == "Hajiya Aminah"
          and not st["pending"].get("customer_id"), st["pending"])
    r = say("Oga Bayo took 2 bags of rice 9000 on credit")
    check("usual price: ₦9,000 for 2 bags of rice (usually ₦45,000 a bag) -> 'Did you mean ₦90,000?'",
          "Did you mean ₦90,000" in r["text"] and "₦45,000 a bag" in r["text"], r["text"])
    r = say("90000")
    check("…saying the right amount fixes it, and the warning goes", st["pending"]["amount"] == 90000
          and "Did you mean" not in r["text"], r["text"])
    say("no")
    say("Oga Bayo took 2 bags of rice 9000 on credit")
    r = say("yes")
    check("…or 'yes' keeps what they said (never silently changed)", "₦9,000" in r["text"], r["text"])
    check("nicknames live in the trader's own book", ledger.recall("nick", "mama t") is not None)

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} correction checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
