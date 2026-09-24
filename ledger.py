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
    type TEXT NOT NULL CHECK (type IN ('sale','credit_sale','payment_received','expense')),
    item TEXT, quantity REAL, unit TEXT,
    amount REAL NOT NULL CHECK (amount >= 0),
    customer TEXT, due_date TEXT,
    raw_text TEXT, engine TEXT, demo INTEGER NOT NULL DEFAULT 0
)"""


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute(SCHEMA)
    return c


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
        return c.execute("DELETE FROM entries").rowcount


def day_summary(day=None):
    day = day or dt.date.today()
    rows = entries(day, limit=10_000)
    tot = defaultdict(float)
    for r in rows:
        tot[r["type"]] += r["amount"]
    sales = tot["sale"] + tot["credit_sale"]
    return {
        "date": day.isoformat(), "count": len(rows),
        "sales": sales, "cash_sales": tot["sale"], "credit_sales": tot["credit_sale"],
        "payments_received": tot["payment_received"], "expenses": tot["expense"],
        "profit": sales - tot["expense"],
        "cash_in_hand_change": tot["sale"] + tot["payment_received"] - tot["expense"],
    }


def customer_key(name):
    return " ".join((name or "").lower().split())


def customer_books():
    """Per customer: credits and repayments. Payments clear the oldest credit first (FIFO),
    and we remember when each credit was fully paid, to judge on-time behaviour."""
    book = {}
    with conn() as c:
        rows = c.execute("SELECT * FROM entries WHERE type IN ('credit_sale','payment_received') "
                         "AND customer IS NOT NULL ORDER BY created_at, id").fetchall()
    for r in rows:
        d = book.setdefault(customer_key(r["customer"]),
                            {"customer": r["customer"], "owed": 0.0, "paid": 0.0, "open": [], "closed": []})
        if r["type"] == "credit_sale":
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


def debtors(today=None):
    """Customers who still owe money. 'due_date' is the promise date of their oldest unpaid debt."""
    today = today or dt.date.today()
    out = []
    for d in customer_books().values():
        if d["balance"] <= 0:
            continue
        due = [x["due"] for x in d["open"] if x["due"]]
        items = [x["item"] for x in d["open"] if x["item"]]
        out.append({"customer": d["customer"], "owed": d["owed"], "paid": d["paid"], "balance": d["balance"],
                    "due_date": min(due) if due else None, "items": sorted(set(items)),
                    "overdue": bool(due and min(due) < today.isoformat()),
                    "days_late": max((today - dt.date.fromisoformat(min(due))).days, 0) if due else 0})
    return sorted(out, key=lambda d: (not d["overdue"], -d["balance"]))


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
    tot = defaultdict(float)
    for r in rows:
        tot[r["type"]] += r["amount"]
    revenue = tot["sale"] + tot["credit_sale"]
    profit = revenue - tot["expense"]
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
        "revenue": revenue, "expenses": tot["expense"], "profit": profit,
        "avg_daily_sales": revenue / span, "outstanding": outstanding, "overdue": overdue,
        "has_demo_data": any(r["demo"] for r in rows),
    }
