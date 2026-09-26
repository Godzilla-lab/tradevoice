"""One conversation that changes language, on one book: record -> ask in Yoruba -> remind "her" -> ... .
Checks each reply's language, the numbers in it, and what ended up in the book. No key needed (word lists).

python eval/test_converse.py
⚠️ Yoruba/Hausa/Igbo lines written by a non-native speaker: add real ones from native speakers.
"""
import datetime as dt
import os
import sys
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith("LOCAL_"):
        os.environ.pop(k)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import converse  # noqa: E402
import ledger  # noqa: E402

TODAY = dt.date(2026, 9, 30)  # Wednesday
BOOK = [  # (date, type, item, amount, customer)
    ("2026-09-20", "credit_sale", "rice", 30000, "Mama Tunde"),
    ("2026-09-21", "credit_sale", "garri", 12000, "Alhaji Musa"),
    ("2026-09-22", "credit_purchase", "rice", 120000, "Alhaji Sani"),
    ("2026-09-25", "payment_made", None, 50000, "Alhaji Sani"),
]
# message, expected reply language, text that must be in the reply (written in that language)
TURNS = [
    ("Mama Tunde dey owe me forty-five thousand", "Pidgin", "₦45,000"),
    ("yes", "Pidgin", "₦75,000"),                                  # saved; her total is now 30k + 45k
    ("Ṣé mo ní gbèsè lọ́wọ́ Alhaji?", "Yoruba", "O jẹ Alhaji Sani ní ₦70,000"),  # "Alhaji" = the one I owe
    ("Remind Mama Tunde tomorrow", "English", "₦75,000 from Mama Tunde"),
    ("How much she dey owe me now?", "Pidgin", "Mama Tunde dey owe you ₦75,000"),  # "she" = Mama Tunde
    ("Alhaji Musa don pay me 5k", "Pidgin", "₦5,000"),
    ("ok", "Pidgin", "₦7,000"),                                    # 12k - 5k
    ("Remind him on Friday", "English", "₦7,000 from Alhaji Musa"),  # "him" = Alhaji Musa
    ("Ina bin Alhaji Musa bashi nawa?", "Hausa", "₦7,000"),
    ("Mama Tunde ji m ego ole?", "Igbo", "Mama Tunde ji gị ₦75,000"),
    ("I sell 2 bags rice give Oga Emeka", "English", "How much"),   # no amount: ask, keep the draft
    ("50k", "English", "₦50,000"),
    ("no", "English", "didn't save"),
    ("Rán Mama Tunde létí lọ́la", "Yoruba", "Lọ́la"),
]


def main():
    for d, typ, item, amt, cust in BOOK:
        ledger.add_entry({"type": typ, "item": item, "amount": amt, "customer": cust},
                         created_at=dt.datetime.fromisoformat(d + "T10:00:00"))
    state, fails = converse.new_state(), 0
    for msg, lang, want in TURNS:
        r = converse.reply(msg, state, today=TODAY, shop="Test Shop")
        ok = r["lang"] == lang and want in r["text"]
        fails += not ok
        print(f"{'✓' if ok else '✗'} {msg}\n    [{r['lang']}] {r['text']}"
              + ("" if ok else f"\n    expected [{lang}] …{want}…"))
    checks = [
        ("book has 6 entries (the 'no' draft not saved)", len(ledger.entries(limit=100)) == 6),
        ("Mama Tunde reminder due tomorrow", [(x["customer"], x["remind_on"]) for x in ledger.reminders(
            TODAY + dt.timedelta(days=1), due_only=True)] == [("Mama Tunde", "2026-10-01")]),
        ("Alhaji Musa reminder on Friday", any(x["customer"] == "Alhaji Musa" and x["remind_on"] == "2026-10-02"
                                               for x in ledger.reminders(TODAY))),
        ("due list in Yoruba", converse.due_today("Yoruba", TODAY + dt.timedelta(days=1))
         == ["📌 Lónìí: gba ₦75,000 lọ́wọ́ Mama Tunde."]),
    ]
    for name, ok in checks:
        fails += not ok
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"\n{len(TURNS) + len(checks) - fails}/{len(TURNS) + len(checks)} passed")
    return fails


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
