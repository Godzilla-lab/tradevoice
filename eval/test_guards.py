"""Offline regression tests: real AI mistakes from our hard test run (25 Sep) must be caught by our guards.

python eval/test_guards.py      # no key needed; fakes the AI's wrong answers
"""
import datetime as dt
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import extract  # noqa: E402

TODAY = dt.date(2026, 9, 27)  # a Sunday
# (text, what the AI wrongly answered, what we must end up with)
CASES = [
    ("Gave Aunty Kemi 3 crates of eggs worth 60000, she has not paid me yet",
     {"type": "payment_received", "amount": 60000, "customer": "Aunty Kemi"}, {"type": "credit_sale"}),
    ("Mo ta àpò ẹ̀wà 4 fún Baba Sola ní 2500, kò tíì san owó náà",
     {"type": "sale", "amount": 2500, "customer": "Baba Sola"}, {"type": "credit_sale"}),
    ("Aunty Kemi bring 30k today, e remain 30k",
     {"type": "sale", "amount": 30000, "customer": "Aunty Kemi"}, {"type": "payment_received"}),
    ("Na sayar da katan indomie 2 a 3500", {"type": "sale", "amount": 7000}, {"amount": 3500}),
    ("Mo ta káàtọ̀nù indomie 2 ní ẹgbàá", {"type": "sale", "amount": 4000}, {"amount": 2000}),
    ("Mo ta káàtọ̀nù indomie 4 ní ẹgbẹ̀rún mẹ́wàá", {"type": "sale", "amount": 20000}, {"amount": 10000}),
    ("Mallam Sani akwụọla naira puku ise nke ọ ji m",
     {"type": "payment_received", "amount": 500, "customer": "Mallam Sani"}, {"amount": 5000}),
    ("I sell 5 bag garri give Oga Emeka, 7.5k each, he go pay Thursday",
     {"type": "credit_sale", "amount": 7500, "customer": "Oga Emeka"}, {"amount": 37500, "due_date": "2026-10-01"}),
    ("I sell 3 bag rice 3k, no no, na 2,500", {"type": "sale", "amount": 3000}, {"amount": 2500}),
    ("Madam Ngozi ta biya 12000 na bashin ta, lambar wayarsa 08034567812",
     {"type": "payment_received", "amount": 12000, "customer": "Madam Ngozi"}, {"amount": 12000}),
    ("Mo ta àpò gaàrí 3 fún Oga Emeka ní 2,500, gbèsè ni, yóò san lọ́jọ́ Ẹtì",
     {"type": "credit_sale", "amount": 2500, "customer": "Oga Emeka", "due_date": "2026-09-29"},
     {"due_date": "2026-10-02"}),
    ("sold 3 cartons of indomie to Mama Tunde two thousand, five hundred naira she will pay on Wednesday",
     {"type": "credit_sale", "amount": None, "customer": "Mama Tunde"}, {"amount": 2500}),
    ("sha hajiya amina carry 4 bag rice 18.5k ehn she never pay me",
     {"type": "credit_sale", "amount": 18500, "customer": None}, {"customer": "Hajiya Amina"}),
    ("Sold 4 cartons of indomie for N27,000 cash", {"type": "sale", "amount": 27000, "customer": None},
     {"customer": None}),
    ("Mo jẹ Alhaji Musa ní 100000 fún àpò ìrẹsì",
     {"type": "sale", "amount": 100000, "customer": "Alhaji Musa"}, {"type": "credit_purchase"}),
    ("Oga Emeka owe me 30k, he go pay Friday", {"type": "credit_sale", "amount": 30000, "customer": "Emeka"},
     {"customer": "Oga Emeka"}),
    ("I paid back Oga Emeka 60,000 today", {"type": "expense", "amount": 60000, "customer": "Oga Emeka"},
     {"type": "payment_made"}),
    ("Uncle Chidi carry 3 carton indomie 90k, he pay 50k, remain 40k",
     {"type": "credit_sale", "amount": 90000, "customer": "Uncle Chidi", "confidence": 0.95}, {"confidence": 0.3}),
    ("Iya Bisi ta biya 60000 na bashin ta", {"type": "sale", "amount": 60000, "customer": "Iya Bisi"},
     {"type": "payment_received"}),
    ("ẹ̀n mo ta kaatonu indomie 5 fun oga emeka ni 18500 ṣé ko tii san owo naa",
     {"type": "credit_sale", "amount": 18500, "customer": "Emeka"}, {"customer": "Oga Emeka"}),
    # must NOT be changed: the AI was right
    ("Aunty Kemi paid 26k out of the 80k she owes, 54k remaining",
     {"type": "payment_received", "amount": 26000, "customer": "Aunty Kemi"}, {"amount": 26000}),
    ("Iya Bisi don pay 12000 wey she owe me", {"type": "payment_received", "amount": 12000, "customer": "Iya Bisi"},
     {"type": "payment_received", "amount": 12000}),
]


def run():
    fails = 0
    for text, ai, want in CASES:
        fake = dict({"item": None, "quantity": None, "unit": None, "due_date": None, "confidence": 0.9,
                     "note": None}, **ai)
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}), \
                mock.patch.object(extract, "llm_extract", return_value=(fake, "fake-ai")):
            rec, _ = extract.extract(text, today=TODAY)
        bad = {k: (rec.get(k), v) for k, v in want.items() if rec.get(k) != v}
        fails += bool(bad)
        print(("✗" if bad else "✓"), text[:70], bad or "")
    print(f"\n{len(CASES) - fails}/{len(CASES)} guard tests pass")
    return fails


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
