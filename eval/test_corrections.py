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

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} correction checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
