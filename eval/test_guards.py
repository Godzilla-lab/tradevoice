"""Offline regression tests: real AI mistakes from our hard test run (25 Sep) must be caught by our guards.

python eval/test_guards.py      # no key needed; fakes the AI's wrong answers
"""
import datetime as dt
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import extract  # noqa: E402

TODAY = dt.date(2026, 9, 27)  # a Sunday
# (text, what the AI wrongly answered, what we must end up with)
CASES = [
    # N-ATLaS on the 1,000-sentence run (2 Oct): balance/total instead of the part paid; re-spelt names
    ("Aunty Kemi brought 20k today, balance is 40k",
     {"type": "payment_received", "amount": 40000, "customer": "Aunty Kemi"}, {"amount": 20000}),
    ("Oga Emeka paid 20k out of the 60k he owes, 40k remaining",
     {"type": "payment_received", "amount": 60000, "customer": "Oga Emeka"}, {"amount": 20000}),
    ("Mallam Sani don pay 60000 na bashin sa",
     {"type": "payment_received", "amount": 60000, "customer": "Mr. Sani"}, {"customer": "Mallam Sani"}),
    ("to na sayar da buhun shinkafa 3 ga hajiya amina 18500 to bashi ne za ta biya ranar juma'a",
     {"type": "credit_sale", "amount": 18500, "customer": "Hajia Amina"}, {"customer": "Hajiya Amina"}),
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
    # 27 Sep, the small model on our Brev GPU (Qwen2.5-7B): who paid whom in Hausa / Igbo, invented customers
    ("Na biya 27000 kudin mota zuwa kasuwa", {"type": "payment_made", "amount": 27000, "customer": None},
     {"type": "expense"}),
    ("Alhaji Musa ya biya naira dubu ashirin na bashin sa", {"type": "expense", "amount": 20000, "customer": "Alhaji Musa"},
     {"type": "payment_received"}),
    ("Madam Ngozi ta biya 12000 na bashin ta, lambar wayarsa 08034567812",
     {"type": "payment_made", "amount": 12000, "customer": "Madam Ngozi"}, {"type": "payment_received"}),
    ("Na sell katan indomie 4 ga Mama Tunde 18500, za ta pay ranar Juma'a",
     {"type": "sale", "amount": 18500, "customer": "Mama Tunde", "due_date": "2026-09-29"},
     {"type": "credit_sale", "due_date": "2026-10-02"}),
    ("Na sayar da buhun wake 4 a 1.2m", {"type": "credit_sale", "amount": 1200000, "customer": "wake"},
     {"type": "sale", "customer": None}),
    ("to na sayar da katan indomie 4 ga baba sola 60000 to bai biya ba tukuna",
     {"type": "credit_sale", "amount": 60000, "customer": "tukuna"}, {"customer": "Baba Sola"}),
    ("Hajiya Amina akwụọla 7500 nke ọ ji m", {"type": "payment_made", "amount": 7500, "customer": "Hajiya Amina"},
     {"type": "payment_received"}),
    ("Akwụrụ m 27000 maka ụgbọ ala gaa ahịa", {"type": "credit_sale", "amount": 27000, "customer": "alaa"},
     {"type": "expense", "customer": None}),
    ("ngwa hajiya amina akwuola 7500 nke o ji m ngwa",
     {"type": "credit_purchase", "amount": 7500, "customer": "Hajiya Amina"}, {"type": "payment_received"}),
    ("ehn ere m akpa agwa 5 nye mama tunde 7500 ehn o ji m ugwo o ga-akwu na sondee",
     {"type": "sale", "amount": 7500, "customer": "Mama Tunde"}, {"type": "credit_sale", "due_date": "2026-10-04"}),
    # 27 Sep, 14B on Brev: no amount was said, the AI made one up -> keep it empty and ask
    ("Mo ta káàtọ̀nù indomie 4 fún Madam Ngozi, gbèsè ni, yóò san lọ́jọ́ Ẹtì",
     {"type": "credit_sale", "amount": 48000, "customer": "Madam Ngozi"}, {"amount": None}),
    ("Ere m katọn indomie 5 nye Aunty Kemi, ọ ji m ụgwọ, ọ ga-akwụ na Sọndee",
     {"type": "credit_sale", "amount": 5, "customer": "Aunty Kemi"}, {"amount": None}),
    # must NOT be changed: the AI was right
    ("Mo ta ẹyin fún Bisi ní ẹgbẹ̀rún mẹ́wàá", {"type": "sale", "amount": 10000, "customer": "Bisi"}, {"amount": 10000}),
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
