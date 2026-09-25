"""Ask-my-book in 5 languages: questions -> exact numbers from a small fixed book. No key needed (word lists).

python eval/test_askbook.py
⚠️ Yoruba/Hausa/Igbo questions written by a non-native speaker: add real ones from native speakers.
"""
import datetime as dt
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ.pop("NVIDIA_API_KEY", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import askbook  # noqa: E402
import ledger  # noqa: E402

TODAY = dt.date(2026, 9, 30)  # a Wednesday; this week = Mon 28 - Wed 30 Sep
BOOK = [  # (date, type, item, qty, unit, amount, customer)
    ("2026-09-29", "sale", "rice", 3, "bag", 45000, None),
    ("2026-09-30", "credit_sale", "rice", 2, "bag", 30000, "Mama Tunde"),
    ("2026-09-30", "sale", "eggs", 4, "crate", 21600, None),
    ("2026-09-22", "sale", "rice", 5, "bag", 75000, None),         # last week
    ("2026-08-20", "sale", "rice", 10, "bag", 150000, None),       # last month
    ("2026-09-29", "expense", "transport", None, None, 3500, None),
    ("2026-09-29", "credit_purchase", "rice", 10, "bag", 120000, "Alhaji Sani"),
    ("2026-09-30", "payment_made", None, None, None, 50000, "Alhaji Sani"),
]
CASES = [  # question, expected money, expected language
    ("How many bags of rice did I sell this week?", 75000, "English"),
    ("How much rice I sell today?", 30000, "Pidgin"),
    ("Ìrẹsì mélòó ni mo tà lọ́sẹ̀ yìí?", 75000, "Yoruba"),
    ("Ìrẹsì mélòó ni mo tà lóṣù yìí?", 150000, "Yoruba"),
    ("Shinkafa nawa na sayar a wannan makon?", 75000, "Hausa"),
    ("Shinkafa nawa na sayar a watan jiya?", 150000, "Hausa"),
    ("Osikapa ole ka m rere n'izu a?", 75000, "Igbo"),
    ("Akwa ole ka m rere taa?", 21600, "Igbo"),
    ("How many crates of eggs I sell this week?", 21600, "Pidgin"),
    ("How much I spend this week?", 123500, "English"),
    ("How much rice I buy this week?", 120000, "English"),
    ("Who I owe?", 70000, "English"),
    ("How much Mama Tunde owe me?", 30000, "English"),
    # everyday English phrasings
    ("What were my total sales last month?", 150000, "English"),
    ("How much did I sell yesterday?", 45000, "English"),
    ("How many eggs did I sell today?", 21600, "English"),
    ("How much did I spend on transport this week?", 3500, "English"),
    ("How much do I owe Alhaji Sani?", 70000, "English"),
    ("What are my sales today?", 51600, "English"),
    ("How much profit did I make this week?", -26900, "English"),   # sales 96,600 - spent 123,500
    ("What did I make today?", 51600, "English"),                  # nothing spent today
    ("How much money came in today?", 21600, "English"),           # cash sale only (the rice was on credit)
    ("Did Mama Tunde buy anything this week?", 30000, "English"),
    ("Show me my expenses for this month", 123500, "English"),
    ("How much rice have I sold so far?", 300000, "English"),
    ("How much I don make this week?", -26900, "Pidgin"),
    ("Èrè mélòó ni mo jẹ lọ́sẹ̀ yìí?", -26900, "Yoruba"),
    ("Riba nawa na samu a wannan makon?", -26900, "Hausa"),
    ("Uru ole ka m nwetara n'izu a?", -26900, "Igbo"),
]


def main():
    for d, typ, item, qty, unit, amt, cust in BOOK:
        ledger.add_entry({"type": typ, "item": item, "quantity": qty, "unit": unit, "amount": amt, "customer": cust},
                         created_at=dt.datetime.fromisoformat(d + "T10:00:00"))
    fails = 0
    for question, money, lang in CASES:
        r = askbook.ask_book(question, TODAY)
        got = askbook.run(r[3], TODAY)["money"] if r else None
        ok = r is not None and got == money
        fails += not ok
        print(f"{'✓' if ok else '✗'} {question}\n    {r[0] if r else 'not understood'}"
              + ("" if ok else f"   (expected ₦{money:,})") + (f"   [lang {r[2]}]" if r and r[2] != lang and {r[2], lang} != {"English", "Pidgin"} else ""))
    print(f"\n{len(CASES) - fails}/{len(CASES)} questions answered with the right numbers")
    return fails


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
