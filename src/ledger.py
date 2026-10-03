"""SQLite ledger + the numbers shown on the dashboard and credit profile."""
import contextvars
import datetime as dt
import os
import sqlite3
from collections import defaultdict

import clock  # noqa: F401  (the process runs on Nigeria time: 'today' means today in Lagos)

DB_PATH = os.getenv("DB_PATH", "tradevoice.db")  # the book when nobody is logged in (tests, the admin page)
BOOKS_DIR = os.getenv("BOOKS_DIR", "books")      # one book per phone number: books/2348031234567.db
_BOOK = contextvars.ContextVar("book", default=None)


def book_file(phone):
    return os.path.join(BOOKS_DIR, "".join(ch for ch in str(phone) if ch.isdigit()) + ".db")


def use_book(phone):
    """Everything after this (in this request / this WhatsApp message) reads and writes this number's book."""
    os.makedirs(BOOKS_DIR, exist_ok=True)
    return _BOOK.set(book_file(phone))


def done_with_book(token):
    _BOOK.reset(token)


def book_path():
    return _BOOK.get() or DB_PATH

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


# Customers have stable ids: two different "Feranmi"s are two customers, never merged by name.
# A conversation per customer = its records + messages (notes, reminder drafts); last_read_at = read state.
CUSTOMERS = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, phone TEXT, notes TEXT, language TEXT,
    created_at TEXT NOT NULL, last_read_at TEXT
)"""
MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL, sender TEXT NOT NULL, kind TEXT NOT NULL,
    content TEXT NOT NULL, status TEXT, created_at TEXT NOT NULL
)"""


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def _migrate(c):
    """Older books: add customer ids (one customer per distinct name) and link every record to one."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(entries)")}
    if "customer_id" not in cols:
        c.execute("ALTER TABLE entries ADD COLUMN customer_id INTEGER")
    ccols = {r[1] for r in c.execute("PRAGMA table_info(customers)")}
    if "credit_limit" not in ccols:  # the most this customer may owe me (None = no limit)
        c.execute("ALTER TABLE customers ADD COLUMN credit_limit REAL")
    rcols = {r[1] for r in c.execute("PRAGMA table_info(reminders)")}
    if "customer_id" not in rcols:
        c.execute("ALTER TABLE reminders ADD COLUMN customer_id INTEGER")
    todo = c.execute("SELECT id, customer, created_at FROM entries WHERE customer IS NOT NULL AND customer_id IS NULL "
                     "ORDER BY created_at, id").fetchall()
    for e in todo:
        key = customer_key(e["customer"])
        row = next((x for x in c.execute("SELECT id, name FROM customers ORDER BY id") if customer_key(x["name"]) == key),
                   None)
        cid = row["id"] if row else c.execute("INSERT INTO customers (name, created_at) VALUES (?,?)",
                                              (e["customer"].strip(), e["created_at"])).lastrowid
        c.execute("UPDATE entries SET customer_id=? WHERE id=?", (cid, e["id"]))
    for rm in c.execute("SELECT id, customer FROM reminders WHERE customer_id IS NULL").fetchall():
        m = [x["id"] for x in c.execute("SELECT id, name FROM customers") if customer_key(x["name"]) == customer_key(rm["customer"])]
        if m:
            c.execute("UPDATE reminders SET customer_id=? WHERE id=?", (m[-1], rm["id"]))


def conn():
    c = sqlite3.connect(book_path())
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
    c.execute(CUSTOMERS)
    c.execute(MESSAGES)
    c.execute(MEMORY)
    with c:
        _migrate(c)
    return c


# What TradeVoice remembers about this trader's way of talking (ROADMAP 8a), kept in their own book: deleted with it.
# kind "nick": a name as the trader says it ("mama t", or a name the speech model hears wrong) -> customer id.
MEMORY = """CREATE TABLE IF NOT EXISTS memory (kind TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
    updated_at TEXT NOT NULL, PRIMARY KEY (kind, key))"""


def remember(kind, key, value):
    key = customer_key(key)
    if not key:
        return
    with conn() as c:
        c.execute("INSERT INTO memory VALUES (?,?,?,?) ON CONFLICT(kind, key) DO UPDATE SET value=excluded.value, "
                  "updated_at=excluded.updated_at", (kind, key, str(value), dt.datetime.now().isoformat(timespec="seconds")))


def recall(kind, key=None):
    """One remembered value (or None); without a key, everything of that kind as {key: value}."""
    with conn() as c:
        if key is None:
            return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM memory WHERE kind=?", (kind,))}
        r = c.execute("SELECT value FROM memory WHERE kind=? AND key=?", (kind, customer_key(key))).fetchone()
    return r["value"] if r else None


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
    """Save one confirmed record. rec["customer_id"] picks the exact customer; with only a name, the one customer of
    that name is used (a new one is created if there is none; with several, the most recently active, which is why
    the chat asks "Which Feranmi?" first)."""
    if rec.get("amount") in (None, ""):
        raise ValueError("Amount is required")
    cid, name = rec.get("customer_id"), (rec.get("customer") or "").strip() or None
    if cid:
        cust = get_customer(cid)
        name = cust["name"] if cust else name
    elif name:
        cid = resolve_customer(name, created_at=created_at)
    with conn() as c:
        cur = c.execute(
            "INSERT INTO entries (created_at,type,item,quantity,unit,amount,customer,due_date,raw_text,engine,demo,"
            "customer_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ((created_at or dt.datetime.now()).isoformat(timespec="seconds"), rec["type"], rec.get("item"),
             rec.get("quantity"), rec.get("unit"), float(rec["amount"]), name,
             rec.get("due_date") or None, raw_text, engine, int(demo), cid),
        )
        rid = cur.lastrowid
    if not demo:
        try:
            import events
            events.log("record_saved", engine=engine)   # no amount, no name: just that a record was saved
        except Exception:  # noqa: BLE001
            pass
    return rid


# ---------------------------------------------------------------- customers (stable ids)

def find_customers(name):
    """Customers whose name is this name (or contains it: "Alhaji" finds "Alhaji Sani"). Most recent activity first."""
    key = customer_key(name)
    if not key:
        return []
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT c.*, (SELECT max(created_at) FROM entries e WHERE e.customer_id=c.id) AS last_at FROM customers c")]
    exact = [r for r in rows if customer_key(r["name"]) == key]
    found = exact or [r for r in rows if all(w in customer_key(r["name"]).split() for w in key.split())]
    return sorted(found, key=lambda r: r["last_at"] or r["created_at"], reverse=True)


def _initials_fit(said, name):
    """"Mama T" fits "Mama Tunde": every word said is a word of the name, or its first letter or two, in order."""
    a, n = customer_key(said).split(), customer_key(name).split()
    if not a or len(a) > len(n) or not any(w in n for w in a):
        return False
    i = 0
    for w in a:
        while i < len(n) and not (n[i] == w or (len(w) <= 2 and n[i].startswith(w.rstrip(".")))):
            i += 1
        if i == len(n):
            return False
        i += 1
    return True


def _sounds(a, b):
    import difflib
    return difflib.SequenceMatcher(None, customer_key(a).replace(" ", ""), customer_key(b).replace(" ", "")).ratio()


def match_customers(name):
    """Who a name said by the trader means, and how sure: (customers, how). how = "nick" (a name they taught it),
    "name" (the name, or part of it: "Alhaji" -> "Alhaji Sani"), "initials" ("Mama T"), "sounds" (close to a name
    in the book: "Hajia Aminat" -> "Hajiya Amina", to be asked about), or "none"."""
    key = customer_key(name)
    if not key:
        return [], "none"
    nick = recall("nick", key)
    if nick and get_customer(int(nick)):
        return [get_customer(int(nick))], "nick"
    found = find_customers(name)
    if found:
        return found, "name"
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT c.*, (SELECT max(created_at) FROM entries e WHERE e.customer_id=c.id) AS last_at FROM customers c")]
    rows.sort(key=lambda r: r["last_at"] or r["created_at"], reverse=True)
    fits = [r for r in rows if _initials_fit(name, r["name"])]
    if fits:
        return fits, "initials"
    close = sorted(((_sounds(name, r["name"]), r) for r in rows), key=lambda x: -x[0])
    close = [r for score, r in close if score >= 0.8][:3]
    return (close, "sounds") if close else ([], "none")


def _item_key(item):
    w = customer_key(item).split()
    return " ".join(w[:-1] + [w[-1][:-1] if len(w[-1]) > 3 and w[-1].endswith("s") else w[-1]]) if w else ""


def usual_price(item):
    """What ONE of this item usually sells for in this trader's own book (code, never the AI): the middle of the
    last 10 sales that had a quantity, with the unit they used most. None until there are at least 2 such sales."""
    key = _item_key(item)
    if not key:
        return None
    with conn() as c:
        rows = c.execute("SELECT item, unit, quantity, amount FROM entries WHERE type IN ('sale','credit_sale') AND "
                         "quantity > 0 AND item IS NOT NULL ORDER BY created_at DESC, id DESC LIMIT 500").fetchall()
    mine = [r for r in rows if _item_key(r["item"]) == key][:10]
    if len(mine) < 2:
        return None
    prices = sorted(r["amount"] / r["quantity"] for r in mine)
    mid = len(prices) // 2
    price = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
    units = [_item_key(r["unit"]) for r in mine if r["unit"]]
    return {"price": round(price), "unit": max(set(units), key=units.count) if units else None, "sales": len(mine)}


def resolve_customer(name, created_at=None):
    m = find_customers(name)
    exact = [x for x in m if customer_key(x["name"]) == customer_key(name)]
    if exact:
        return exact[0]["id"]
    return create_customer(name, created_at=created_at)


def create_customer(name, phone=None, notes=None, created_at=None):
    with conn() as c:
        return c.execute("INSERT INTO customers (name, phone, notes, created_at) VALUES (?,?,?,?)",
                         (name.strip(), (phone or "").strip() or None, notes,
                          (created_at or dt.datetime.now()).isoformat(timespec="seconds"))).lastrowid


def get_customer(cid):
    with conn() as c:
        r = c.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    return dict(r) if r else None


def update_customer(cid, **fields):
    allowed = {k: v for k, v in fields.items()
               if k in ("name", "phone", "notes", "language", "last_read_at", "credit_limit")}
    with conn() as c:
        for k, v in allowed.items():
            c.execute(f"UPDATE customers SET {k}=? WHERE id=?", (v, cid))
        if "name" in allowed:
            c.execute("UPDATE entries SET customer=? WHERE customer_id=?", (allowed["name"], cid))
    return get_customer(cid)


def delete_customer(cid):
    """Remove the customer and their conversation. Their records stay in the book (money is history)."""
    with conn() as c:
        c.execute("UPDATE entries SET customer_id=NULL WHERE customer_id=?", (cid,))
        c.execute("DELETE FROM messages WHERE customer_id=?", (cid,))
        c.execute("DELETE FROM reminders WHERE customer_id=?", (cid,))
        return c.execute("DELETE FROM customers WHERE id=?", (cid,)).rowcount


def add_message(cid, content, sender="trader", kind="note", status=None):
    with conn() as c:
        return c.execute("INSERT INTO messages (customer_id, sender, kind, content, status, created_at) "
                         "VALUES (?,?,?,?,?,?)", (cid, sender, kind, content, status, _now())).lastrowid


def set_message(mid, **fields):
    with conn() as c:
        for k, v in fields.items():
            if k in ("content", "status"):
                c.execute(f"UPDATE messages SET {k}=? WHERE id=?", (v, mid))


def customer_summary(cid, today=None):
    """Live context for one customer: what they owe, what I owe them, last record, promised date, late or not."""
    cust = get_customer(cid)
    if not cust:
        return None
    today = today or dt.date.today()
    theirs = next((d for d in debtors(today) if d["customer_id"] == cid), None)
    mine = next((d for d in creditors(today) if d["customer_id"] == cid), None)
    with conn() as c:
        last = c.execute("SELECT * FROM entries WHERE customer_id=? ORDER BY created_at DESC, id DESC LIMIT 1",
                         (cid,)).fetchone()
    return dict(cust, owes_me=theirs["balance"] if theirs else 0, i_owe=mine["balance"] if mine else 0,
                due_date=(theirs or mine or {}).get("due_date"), overdue=bool(theirs and theirs["overdue"]),
                days_late=theirs["days_late"] if theirs else 0,
                last=dict(last) if last else None, last_at=last["created_at"] if last else cust["created_at"])


def conversations(today=None):
    """One row per customer, most recent activity first: last thing that happened, balance, unread count."""
    today = today or dt.date.today()
    owed = {d["customer_id"]: d for d in debtors(today)}
    owe = {d["customer_id"]: d for d in creditors(today)}
    with conn() as c:
        custs = [dict(r) for r in c.execute("SELECT * FROM customers")]
        last_e = {r["customer_id"]: dict(r) for r in c.execute(
            "SELECT * FROM entries WHERE customer_id IS NOT NULL AND id IN (SELECT max(id) FROM entries "
            "WHERE customer_id IS NOT NULL GROUP BY customer_id)")}
        last_m = {r["customer_id"]: dict(r) for r in c.execute(
            "SELECT * FROM messages WHERE id IN (SELECT max(id) FROM messages GROUP BY customer_id)")}
        unread = {}
        for cu in custs:
            since = cu["last_read_at"] or today.isoformat()
            unread[cu["id"]] = c.execute("SELECT count(*) FROM entries WHERE customer_id=? AND created_at>?",
                                         (cu["id"], since)).fetchone()[0]
    out = []
    for cu in custs:
        e, m = last_e.get(cu["id"]), last_m.get(cu["id"])
        last = max([x for x in (e, m) if x], key=lambda x: x["created_at"], default=None)
        out.append(dict(cu, owes_me=owed.get(cu["id"], {}).get("balance", 0),
                        i_owe=owe.get(cu["id"], {}).get("balance", 0),
                        overdue=owed.get(cu["id"], {}).get("overdue", False),
                        days_late=owed.get(cu["id"], {}).get("days_late", 0),
                        last=last, last_is_message=bool(last and last is m),
                        last_at=last["created_at"] if last else cu["created_at"], unread=unread.get(cu["id"], 0)))
    return sorted(out, key=lambda x: x["last_at"], reverse=True)


def thread(cid):
    """Everything about one customer, oldest first: records (from the book) and messages (notes, reminder drafts)."""
    with conn() as c:
        ents = [dict(r, event="record") for r in c.execute("SELECT * FROM entries WHERE customer_id=?", (cid,))]
        msgs = [dict(r, event="message") for r in c.execute("SELECT * FROM messages WHERE customer_id=?", (cid,))]
    return sorted(ents + msgs, key=lambda x: (x["created_at"], x["event"] == "message", x["id"]))


def is_empty():
    with conn() as c:
        return c.execute("SELECT 1 FROM entries LIMIT 1").fetchone() is None


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
        c.execute("DELETE FROM messages")
        c.execute("DELETE FROM customers")
        return c.execute("DELETE FROM entries").rowcount


def add_reminder(customer, remind_on, language=None, customer_id=None):
    if customer_id is None:
        customer_id = resolve_customer(customer)
    with conn() as c:
        c.execute("DELETE FROM reminders WHERE customer_id=? AND done=0", (customer_id,))
        return c.execute("INSERT INTO reminders (customer, remind_on, language, created_at, customer_id) "
                         "VALUES (?,?,?,?,?)", (customer, str(remind_on), language, _now(), customer_id)).lastrowid


def reminders(today=None, due_only=False):
    """Open reminders (due_only: those for today or earlier), each with what the person still owes."""
    today = (today or dt.date.today()).isoformat()
    with conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM reminders WHERE done=0 ORDER BY remind_on")]
    owed = {d["customer_id"]: d["balance"] for d in debtors()}
    out = []
    for r in rows:
        r["balance"] = owed.get(r["customer_id"], 0)
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
        # cash that really moved today (credit sales and goods taken on credit are not cash): Home shows these
        "money_in": tot["sale"] + tot["payment_received"] + tot["loan_taken"],
        "money_out": tot["expense"] + tot["payment_made"],
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
        d = book.setdefault(r["customer_id"] or ("name", customer_key(r["customer"])),
                            {"customer": r["customer"], "customer_id": r["customer_id"],
                             "owed": 0.0, "paid": 0.0, "open": [], "closed": []})
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
        out.append({"customer": d["customer"], "customer_id": d["customer_id"], "owed": d["owed"], "paid": d["paid"], "balance": d["balance"],
                    "due_date": min(due) if due else None, "items": sorted(set(items)),
                    "overdue": bool(due and min(due) < today.isoformat()),
                    "days_late": max((today - dt.date.fromisoformat(min(due))).days, 0) if due else 0})
    return sorted(out, key=lambda d: (not d["overdue"], -d["balance"]))


def creditors(today=None):
    """Suppliers/lenders the TRADER still owes, oldest promised date first."""
    return debtors(today, customer_books("credit_purchase", "payment_made"))


def balance_with(name=None, today=None, customer_id=None):
    """(what this person owes the trader, what the trader owes this person). By id when known, else by name."""
    if customer_id is None and name:
        m = [x for x in find_customers(name) if customer_key(x["name"]) == customer_key(name)]
        customer_id = m[0]["id"] if m else None
    theirs = next((d["balance"] for d in debtors(today) if d["customer_id"] == customer_id), 0)
    mine = next((d["balance"] for d in creditors(today) if d["customer_id"] == customer_id), 0)
    return theirs, mine


def limit_check(customer_id, amount, today=None):
    """Would this credit sale take the customer over their limit? None when no limit is set.
    {limit, balance (owed now), after (owed after this sale), over (bool)}"""
    cust = get_customer(customer_id) if customer_id else None
    if not cust or not cust.get("credit_limit"):
        return None
    theirs = next((d for d in debtors(today) if d["customer_id"] == customer_id), None)
    balance = theirs["balance"] if theirs else 0.0
    after = balance + float(amount or 0)
    return {"limit": cust["credit_limit"], "balance": balance, "after": after, "over": after > cust["credit_limit"],
            "name": cust["name"]}


def customer_risk(name, today=None, customer_id=None):
    """Should I give this customer more credit? Transparent rules over their own history."""
    today = today or dt.date.today()
    if customer_id is None:
        m = [x for x in find_customers(name) if customer_key(x["name"]) == customer_key(name)]
        customer_id = m[0]["id"] if m else None
    d = customer_books().get(customer_id) if customer_id else None
    if not d:
        return {"level": "new", "message": f"First credit for {name}. Start small until they build a record."}
    closed = [x for x in d["closed"] if x["due"]]
    on_time = sum(1 for x in closed if x["paid_on"] <= x["due"])
    late_open = [x for x in d["open"] if x["due"] and x["due"] < today.isoformat()]
    days_late = max(((today - dt.date.fromisoformat(x["due"])).days for x in late_open), default=0)
    history = f"{on_time} of {len(closed)} past debts paid on time" if closed else "no finished debts yet"
    if late_open and (days_late > 7 or d["balance"] >= 50_000):
        level, lead = "high", f"{d['customer']} already owes ₦{d['balance']:,.0f} and is {days_late} days late"
    elif late_open or (closed and on_time / len(closed) < 0.6):
        level, lead = "medium", f"{d['customer']} owes ₦{d['balance']:,.0f}" + (
            f", {days_late} days late" if late_open else "") + ". Consider asking for part payment"
    else:
        level, lead = "low", f"{d['customer']} is reliable" + (
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
# Yoruba (yo) / Hausa (ha) / Igbo (ig) words need a native-speaker check.
EXPENSE_TYPES = [
    ("Rent", ("rent", "stall", "shop fee", "owo ile", "haya", "ugwo ulo")),
    ("Levies & dues", ("levy", "levies", "ticket", "dues", "association", "tax", "local government", "lga",
                       "haraji", "owo ori", "utu isi")),
    ("Power & fuel", ("light", "nepa", "phcn", "generator", "gen ", "diesel", "petrol", "fuel", "power")),
    ("Transport", ("transport", "motor", "bus", "okada", "keke", "fare", "owo oko", "kudin mota", "ugbo ala")),
    ("Staff", ("salary", "apprentice", "wage", "worker", "boy", "girl", "help")),
    ("Restock (goods to sell)", ("restock", "stock", "goods", "bag", "carton", "crate", "paint", "rice", "beans",
                                 "garri", "indomie", "oil", "tomato", "pepper", "yam", "egg", "cement", "shoe")),
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
        names = [r[0] for r in c.execute("SELECT c.name FROM customers c LEFT JOIN entries e ON e.customer_id=c.id "
                                         "GROUP BY lower(c.name) ORDER BY count(e.id) DESC, max(e.created_at) DESC "
                                         "LIMIT ?", (limit,))]
        items = [r[0] for r in c.execute("SELECT item FROM entries WHERE item IS NOT NULL "
                                         "GROUP BY lower(item) ORDER BY count(*) DESC LIMIT ?", (limit // 2,))]
    return {"names": names, "items": items}
