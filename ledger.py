"""SQLite ledger + the numbers shown on the dashboard and credit profile."""
import datetime as dt
import os
import sqlite3
from collections import defaultdict

DB_PATH = os.getenv("DB_PATH", "tradevoice.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('sale','credit_sale','payment_received','expense',
                                       'credit_purchase','payment_made')),
    item TEXT, quantity REAL, unit TEXT,
    amount REAL NOT NULL CHECK (amount >= 0),
    customer TEXT, due_date TEXT,
    raw_text TEXT, engine TEXT, demo INTEGER NOT NULL DEFAULT 0
)"""

# "Remind Mama Tunde tomorrow": on that day the app (or WhatsApp bot) tells the TRADER, with the message ready;
# nothing is ever sent to the customer automatically.
REMINDERS = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT NOT NULL, remind_on TEXT NOT NULL, language TEXT,
    created_at TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0
)"""


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    old = c.execute("SELECT sql FROM sqlite_master WHERE name='entries'").fetchone()
    if old and "credit_purchase" not in old[0]:  # books made before "I owe" existed: widen the type list
        with c:
            c.execute("ALTER TABLE entries RENAME TO entries_old")
            c.execute(SCHEMA)
            c.execute("INSERT INTO entries SELECT * FROM entries_old")
            c.execute("DROP TABLE entries_old")
    c.execute(SCHEMA)
    c.execute(REMINDERS)
    return c


# Money the TRADER owes: 'credit_purchase' = goods (or cash) taken on credit from a supplier/lender,
# 'payment_made' = the trader paying that back. Goods on credit count as spending when taken (like a credit sale
# counts as sales when made); borrowed CASH is not spending, so it gets its own kind.
_LOAN_WORDS = ("loan", "borrow", "lend", "cash")


def kind(r):
    if r["type"] == "credit_purchase" and any(w in (r.get("item") or "").lower() for w in _LOAN_WORDS):
        return "loan_taken"
    return r["type"]


def _totals(rows):
    tot = defaultdict(float)
    for r in rows:
        tot[kind(dict(r))] += r["amount"]
    tot["spent"] = tot["expense"] + tot["credit_purchase"]
    return tot


def add_entry(rec, raw_text="", engine="", created_at=None, demo=False):
    if rec.get("amount") in (None, ""):
        raise ValueError("Amount is required")
    with conn() as c:
        cur = c.execute(
            "INSERT INTO entries (created_at,type,item,quantity,unit,amount,customer,due_date,raw_text,engine,demo)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ((created_at or dt.datetime.now()).isoformat(timespec="seconds"), rec["type"], rec.get("item"),
             rec.get("quantity"), rec.get("unit"), float(rec["amount"]), rec.get("customer") or None,
             rec.get("due_date") or None, raw_text, engine, int(demo)),
        )
        return cur.lastrowid


def entries(day=None, limit=200):
    q, args = "SELECT * FROM entries", []
    if day:
        q += " WHERE substr(created_at,1,10)=?"
        args.append(day.isoformat())
    q += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def delete_entry(entry_id):
    with conn() as c:
        return c.execute("DELETE FROM entries WHERE id=?", (int(entry_id),)).rowcount


def wipe():
    with conn() as c:
        c.execute("DELETE FROM reminders")
        return c.execute("DELETE FROM entries").rowcount


def add_reminder(customer, remind_on, language=None):
    with conn() as c:
        c.execute("DELETE FROM reminders WHERE lower(customer)=? AND done=0", (customer_key(customer),))
        return c.execute("INSERT INTO reminders (customer, remind_on, language, created_at) VALUES (?,?,?,?)",
                         (customer, str(remind_on), language,
                          dt.datetime.now().isoformat(timespec="seconds"))).lastrowid


def reminders(today=None, due_only=False):
    """Open reminders (due_only: those for today or earlier), each with what the person still owes."""
    today = (today or dt.date.today()).isoformat()
    with conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM reminders WHERE done=0 ORDER BY remind_on")]
    owed = {customer_key(d["customer"]): d["balance"] for d in debtors()}
    out = []
    for r in rows:
        r["balance"] = owed.get(customer_key(r["customer"]), 0)
        if r["balance"] and (not due_only or r["remind_on"] <= today):
            out.append(r)
    return out


def reminder_done(reminder_id):
    with conn() as c:
        return c.execute("UPDATE reminders SET done=1 WHERE id=?", (reminder_id,)).rowcount


def day_summary(day=None):
    day = day or dt.date.today()
    rows = entries(day, limit=10_000)
    tot = _totals(rows)
    sales = tot["sale"] + tot["credit_sale"]
    return {
        "date": day.isoformat(), "count": len(rows),
        "sales": sales, "cash_sales": tot["sale"], "credit_sales": tot["credit_sale"],
        "payments_received": tot["payment_received"], "expenses": tot["spent"],
        "bought_on_credit": tot["credit_purchase"], "paid_suppliers": tot["payment_made"],
        "profit": sales - tot["spent"],
        "cash_in_hand_change": (tot["sale"] + tot["payment_received"] + tot["loan_taken"] - tot["expense"]
                                - tot["payment_made"]),
    }


def customer_key(name):
    return " ".join((name or "").lower().split())


def customer_books(credit="credit_sale", payback="payment_received"):
    """Per person: credits and repayments. Payments clear the oldest credit first (FIFO),
    and we remember when each credit was fully paid, to judge on-time behaviour.
    Default = customers who owe the trader; credit='credit_purchase', payback='payment_made' = who the trader owes."""
    book = {}
    with conn() as c:
        rows = c.execute("SELECT * FROM entries WHERE type IN (?,?) AND customer IS NOT NULL ORDER BY created_at, id",
                         (credit, payback)).fetchall()
    for r in rows:
        d = book.setdefault(customer_key(r["customer"]),
                            {"customer": r["customer"], "owed": 0.0, "paid": 0.0, "open": [], "closed": []})
        if r["type"] == credit:
            d["owed"] += r["amount"]
            d["open"].append({"left": r["amount"], "amount": r["amount"], "item": r["item"],
                              "taken": r["created_at"][:10], "due": r["due_date"]})
        else:
            d["paid"] += r["amount"]
            left = r["amount"]
            while left > 0 and d["open"]:
                cr = d["open"][0]
                take = min(left, cr["left"])
                cr["left"] -= take
                left -= take
                if cr["left"] <= 0:
                    cr["paid_on"] = r["created_at"][:10]
                    d["closed"].append(d["open"].pop(0))
    for d in book.values():
        d["balance"] = round(d["owed"] - d["paid"], 2)
    return book


def debtors(today=None, _books=None):
    """Customers who still owe money. 'due_date' is the promise date of their oldest unpaid debt."""
    today = today or dt.date.today()
    out = []
    for d in (_books if _books is not None else customer_books()).values():
        if d["balance"] <= 0:
            continue
        due = [x["due"] for x in d["open"] if x["due"]]
        items = [x["item"] for x in d["open"] if x["item"]]
        out.append({"customer": d["customer"], "owed": d["owed"], "paid": d["paid"], "balance": d["balance"],
                    "due_date": min(due) if due else None, "items": sorted(set(items)),
                    "overdue": bool(due and min(due) < today.isoformat()),
                    "days_late": max((today - dt.date.fromisoformat(min(due))).days, 0) if due else 0})
    return sorted(out, key=lambda d: (not d["overdue"], -d["balance"]))


def creditors(today=None):
    """Suppliers/lenders the TRADER still owes, oldest promised date first."""
    return debtors(today, customer_books("credit_purchase", "payment_made"))


def balance_with(name, today=None):
    """(what this person owes the trader, what the trader owes this person)."""
    key = customer_key(name)
    theirs = next((d["balance"] for d in debtors(today) if customer_key(d["customer"]) == key), 0)
    mine = next((d["balance"] for d in creditors(today) if customer_key(d["customer"]) == key), 0)
    return theirs, mine


def customer_risk(name, today=None):
    """Should I give this customer more credit? Transparent rules over their own history."""
    today = today or dt.date.today()
    d = customer_books().get(customer_key(name))
    if not d:
        return {"level": "new", "message": f"First credit for {name} — start small until they build a record."}
    closed = [x for x in d["closed"] if x["due"]]
    on_time = sum(1 for x in closed if x["paid_on"] <= x["due"])
    late_open = [x for x in d["open"] if x["due"] and x["due"] < today.isoformat()]
    days_late = max(((today - dt.date.fromisoformat(x["due"])).days for x in late_open), default=0)
    history = f"{on_time} of {len(closed)} past debts paid on time" if closed else "no finished debts yet"
    if late_open and (days_late > 7 or d["balance"] >= 50_000):
        level, lead = "high", f"⛔ {d['customer']} already owes ₦{d['balance']:,.0f} and is {days_late} days late"
    elif late_open or (closed and on_time / len(closed) < 0.6):
        level, lead = "medium", f"⚠️ {d['customer']} owes ₦{d['balance']:,.0f}" + (
            f", {days_late} days late" if late_open else "") + " — consider asking for part payment"
    else:
        level, lead = "low", f"✅ {d['customer']} is reliable" + (
            f", currently owes ₦{d['balance']:,.0f}" if d["balance"] > 0 else "")
    return {"level": level, "message": f"{lead} ({history}).", "balance": d["balance"], "days_late": days_late,
            "on_time": on_time, "finished": len(closed)}


def credit_profile(today=None):
    """Transparent, rule-based indicator. Not a credit decision."""
    today = today or dt.date.today()
    with conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM entries")]
    if not rows:
        return None
    dates = sorted({r["created_at"][:10] for r in rows})
    first = dt.date.fromisoformat(dates[0])
    span = max((today - first).days + 1, 1)
    tot = _totals(rows)
    revenue = tot["sale"] + tot["credit_sale"]
    profit = revenue - tot["spent"]
    margin = profit / revenue if revenue else 0.0
    # only judge collection on credit that is already due (promised date passed, or 7 days if none given)
    due_credit = sum(r["amount"] for r in rows if r["type"] == "credit_sale" and
                     (r["due_date"] or (dt.date.fromisoformat(r["created_at"][:10]) + dt.timedelta(days=7)).isoformat())
                     < today.isoformat())
    repay = min(tot["payment_received"] / due_credit, 1.0) if due_credit else None
    owing = debtors(today)
    outstanding = sum(d["balance"] for d in owing)
    overdue = sum(d["balance"] for d in owing if d["overdue"])

    parts = {
        "Record-keeping consistency": (min(len(dates) / span, 1.0) * 30, 30,
                                       f"{len(dates)} of {span} days recorded"),
        "Profitability": (max(0.0, min(margin / 0.3, 1.0)) * 25, 25, f"margin {margin:.0%}"),
        "Debt collection": ((repay if repay is not None else 0.5) * 25, 25,
                            "no credit due yet" if repay is None else f"{repay:.0%} of due credit collected"),
        "History length": (min(span / 30, 1.0) * 20, 20, f"{span} days of records"),
    }
    score = round(sum(p[0] for p in parts.values()))
    band = "Strong" if score >= 75 else "Building" if score >= 50 else "Early"
    return {
        "score": score, "band": band, "parts": parts, "span_days": span, "days_recorded": len(dates),
        "revenue": revenue, "expenses": tot["spent"], "profit": profit,
        "avg_daily_sales": revenue / span, "outstanding": outstanding, "overdue": overdue,
        "owed_to_suppliers": sum(d["balance"] for d in creditors(today)),
        "has_demo_data": any(r["demo"] for r in rows),
    }


# ---------------------------------------------------------------- spending by type, month and year

# First match wins (so "market levy" is a levy, not transport). Words are lower case, without tone marks.
# ⚠️ Yoruba (yo) / Hausa (ha) / Igbo (ig) words need a native-speaker check.
EXPENSE_TYPES = [
    ("Rent", ("rent", "stall", "shop fee", "owo ile", "haya", "ugwo ulo")),
    ("Levies & dues", ("levy", "levies", "ticket", "dues", "association", "tax", "local government", "lga",
                       "haraji", "owo ori", "utu isi")),
    ("Power & fuel", ("light", "nepa", "phcn", "generator", "gen ", "diesel", "petrol", "fuel", "power")),
    ("Transport", ("transport", "motor", "bus", "okada", "keke", "fare", "owo oko", "kudin mota", "ugbo ala")),
    ("Staff", ("salary", "apprentice", "wage", "worker", "boy", "girl", "help")),
    ("Restock (goods to sell)", ("restock", "stock", "goods", "bag", "carton", "crate", "paint", "rice", "beans",
                                 "garri", "indomie", "oil", "tomato", "pepper", "yam")),
]


def expense_type(entry):
    import unicodedata

    text = " ".join(str(entry.get(k) or "") for k in ("item", "raw_text")).lower()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    for name, words in EXPENSE_TYPES:
        if any(w in text for w in words):
            return name
    return "Other"


def period_summary(start, end):
    """Money in and out between two dates (inclusive). All numbers from the trader's own confirmed records."""
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM entries WHERE substr(created_at,1,10) BETWEEN ? AND ? ORDER BY created_at",
            (start.isoformat(), end.isoformat()))]
    tot, by_type, rent_levies = _totals(rows), defaultdict(float), []
    for r in rows:
        if kind(r) not in ("expense", "credit_purchase"):
            continue
        what = expense_type(r) if r["type"] == "expense" else "Restock (goods to sell)"
        by_type[what] += r["amount"]
        if what in ("Rent", "Levies & dues"):
            rent_levies.append({"date": r["created_at"][:10], "kind": what, "item": r["item"],
                                "amount": r["amount"]})
    sales = tot["sale"] + tot["credit_sale"]
    return {"start": start.isoformat(), "end": end.isoformat(), "entries": len(rows),
            "days_recorded": len({r["created_at"][:10] for r in rows}),
            "sales": sales, "cash_sales": tot["sale"], "credit_sales": tot["credit_sale"],
            "payments_received": tot["payment_received"], "expenses": tot["spent"],
            "bought_on_credit": tot["credit_purchase"], "paid_suppliers": tot["payment_made"],
            "expenses_by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
            "profit": sales - tot["spent"], "rent_levies": rent_levies,
            "has_demo_data": any(r["demo"] for r in rows)}


def monthly_totals(year):
    out = []
    for m in range(1, 13):
        start = dt.date(year, m, 1)
        end = (dt.date(year + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
        s = period_summary(start, end)
        if s["entries"]:
            out.append(dict(s, month=start.strftime("%b %Y")))
    return out


def known_words(limit=25):
    """This trader's own customer/supplier names and items, most used first, to help the speech model and the AI
    hear and spell THEIR words ("Alhaji Sani", "paint of garri")."""
    with conn() as c:
        names = [r[0] for r in c.execute("SELECT customer FROM entries WHERE customer IS NOT NULL "
                                         "GROUP BY lower(customer) ORDER BY count(*) DESC, max(created_at) DESC "
                                         "LIMIT ?", (limit,))]
        items = [r[0] for r in c.execute("SELECT item FROM entries WHERE item IS NOT NULL "
                                         "GROUP BY lower(item) ORDER BY count(*) DESC LIMIT ?", (limit // 2,))]
    return {"names": names, "items": items}
