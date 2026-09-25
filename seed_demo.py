"""Seed ~3 weeks of clearly-flagged demo history so the credit profile has something to show.

python seed_demo.py          (python seed_demo.py --wipe to clear first)
Disclose in the submission that the demo history is synthetic.
"""
import datetime as dt
import random
import sys

import ledger

random.seed(27)
CUSTOMERS = ["Mama Tunde", "Alhaji Musa", "Iya Bisi", "Oga Emeka", "Madam Funke"]
# (item, unit, selling price); restock costs ~75% of selling price
ITEMS = [("rice", "bag", 15000), ("garri", "paint", 1800), ("beans", "paint", 1500),
         ("indomie", "carton", 9250), ("eggs", "crate", 5400)]


def add(rec, when):
    ledger.add_entry(rec, raw_text="(demo)", engine="demo", created_at=when, demo=True)


if "--wipe" in sys.argv:
    ledger.wipe()

today = dt.date.today()
open_credit = []  # [customer, amount, due_date]
for back in range(21, 0, -1):
    day = today - dt.timedelta(days=back)
    if day.weekday() == 6 or random.random() < 0.12:  # closed Sundays, a few missed days
        continue
    t = dt.datetime.combine(day, dt.time(8, 0))
    day_sales = 0
    for _ in range(random.randint(4, 8)):
        item, unit, price = random.choice(ITEMS)
        qty = random.randint(1, 4)
        t += dt.timedelta(minutes=random.randint(20, 70))
        rec = {"type": "sale", "item": item, "unit": unit, "quantity": qty, "amount": qty * price}
        if random.random() < 0.25:
            due = day + dt.timedelta(days=random.choice([3, 5, 7]))
            rec.update(type="credit_sale", customer=random.choice(CUSTOMERS), due_date=due.isoformat())
            open_credit.append([rec["customer"], rec["amount"], due])
        add(rec, t)
        day_sales += rec["amount"]
    # most customers pay on or near the promised day; some are late
    for c in [c for c in open_credit if c[2] <= day]:
        # Oga Emeka never pays (shows the overdue flag); Alhaji Musa always pays on the day (reliable customer)
        if c[0] == "Alhaji Musa" or (c[0] != "Oga Emeka" and random.random() < 0.8):
            add({"type": "payment_received", "customer": c[0], "amount": c[1]}, t + dt.timedelta(minutes=30))
            open_credit.remove(c)
    add({"type": "expense", "item": "restock", "amount": round(day_sales * 0.75, -2)}, t + dt.timedelta(hours=1))
    add({"type": "expense", "item": random.choice(["transport", "market levy"]),
         "amount": random.choice([500, 1500, 3500])}, t + dt.timedelta(hours=2))

# the trader's own debt to a wholesaler (shows "Who I owe"): 10 bags on credit, half paid back
took = dt.datetime.combine(today - dt.timedelta(days=10), dt.time(7, 30))
add({"type": "credit_purchase", "item": "rice", "unit": "bag", "quantity": 10, "amount": 120000,
     "customer": "Alhaji Sani", "due_date": (today + dt.timedelta(days=4)).isoformat()}, took)
add({"type": "payment_made", "customer": "Alhaji Sani", "amount": 60000},
    took + dt.timedelta(days=6))

p = ledger.credit_profile()
print(f"Seeded. Score {p['score']}/100 ({p['band']}), outstanding ₦{p['outstanding']:,.0f}, "
      f"overdue ₦{p['overdue']:,.0f}, you owe suppliers ₦{p['owed_to_suppliers']:,.0f}")
