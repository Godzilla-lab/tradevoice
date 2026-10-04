"""Money features on top of the ledger: forecast, top items, debt reminders, Ask-my-book, lender statement.
All numbers are computed here in plain Python; the LLM only phrases answers from these facts.
"""
import datetime as dt
import html
import json
import os
import re
import statistics
import urllib.parse
from collections import defaultdict

import ledger

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def naira(x):
    return ("-" if x < 0 else "") + f"₦{abs(x):,.0f}"  # -₦693,900, not ₦-693,900


def _rows(days=28, today=None):
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=days)).isoformat()
    with ledger.conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM entries WHERE created_at >= ? ORDER BY created_at", (since,))]


# ---------------------------------------------------------------- forecast + top items

def forecast(today=None, days_ahead=7):
    """Weekday-average sales forecast + debts due to come in. Simple on purpose: explainable to a trader."""
    today = today or dt.date.today()
    rows = _rows(28, today)
    if not rows:
        return None
    daily = defaultdict(lambda: defaultdict(float))
    for r in rows:
        daily[r["created_at"][:10]][r["type"]] += r["amount"]
    by_wd = defaultdict(list)
    for d, t in daily.items():
        by_wd[dt.date.fromisoformat(d).weekday()].append(t["sale"] + t["credit_sale"])
    open_days = len(daily)
    avg_exp = sum(t["expense"] for t in daily.values()) / open_days
    avg_sales = sum(t["sale"] + t["credit_sale"] for t in daily.values()) / open_days
    cash_share = (sum(t["sale"] for t in daily.values()) /
                  max(sum(t["sale"] + t["credit_sale"] for t in daily.values()), 1))

    owing = ledger.debtors(today)
    horizon = (today + dt.timedelta(days=days_ahead)).isoformat()
    due_soon = [d for d in owing if d["due_date"] and today.isoformat() <= d["due_date"] <= horizon]
    overdue = [d for d in owing if d["overdue"]]

    plan = []
    for i in range(1, days_ahead + 1):
        day = today + dt.timedelta(days=i)
        hist = by_wd.get(day.weekday())
        # days the shop never opened on (e.g. Sunday) forecast as closed
        sales = statistics.mean(hist) if hist else 0.0
        plan.append({"date": day.isoformat(), "weekday": WEEKDAYS[day.weekday()], "sales": sales,
                     "collections": sum(d["balance"] for d in due_soon if d["due_date"] == day.isoformat())})
    busiest = max(by_wd.items(), key=lambda kv: statistics.mean(kv[1]))[0]
    total_sales = sum(p["sales"] for p in plan)
    open_ahead = sum(1 for p in plan if p["sales"] > 0)
    expected_cash = (total_sales * cash_share + sum(p["collections"] for p in plan) - avg_exp * open_ahead)
    return {"plan": plan, "busiest_day": WEEKDAYS[busiest], "avg_daily_sales": avg_sales,
            "avg_daily_expenses": avg_exp, "week_sales": total_sales, "expected_cash": expected_cash,
            "due_soon": due_soon, "overdue": overdue, "cash_share": cash_share}


# ---------------------------------------------------------------- margin per item + cheapest supplier
# Only rows where the trader said HOW MANY (quantity) count: a price per unit is never guessed.

_NOT_GOODS = {"transport", "rent", "levy", "market levy", "fuel", "diesel", "salary", "shop rent", "loan", "restock", "tax"}


def _key(item, unit):
    """'Bags' / 'bag', 'Eggs' / 'egg': the same thing."""
    def one(w):
        w = " ".join((w or "").lower().split())
        return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
    return one(item), one(unit)


def _per_unit(rows):
    """{(item, unit): {"qty", "amount", "rows": [...]}} for rows with an item and a quantity."""
    out = {}
    for r in rows:
        if not r.get("item") or not r.get("quantity") or float(r["quantity"]) <= 0:
            continue
        k = _key(r["item"], r.get("unit"))
        if k[0] in _NOT_GOODS:
            continue
        g = out.setdefault(k, {"qty": 0.0, "amount": 0.0, "rows": [], "name": r["item"].strip().lower(),
                               "unit_name": (r.get("unit") or "").strip().lower()})
        g["qty"] += float(r["quantity"])
        g["amount"] += float(r["amount"])
        g["rows"].append(r)
    return out


def _bought(rows):
    return [r for r in rows if r["type"] in ("expense", "credit_purchase") and ledger.kind(r) != "loan_taken"]


def margins(days=60, today=None):
    """Per item: average selling price per unit vs average buying price per unit, from the trader's own records.
    'Rice: sell ₦15,000, buy ₦12,000 = ₦3,000 per bag (20%)'. Best total margin first."""
    rows = _rows(days, today)
    sold = _per_unit([r for r in rows if r["type"] in ("sale", "credit_sale")])
    bought = _per_unit(_bought(rows))
    out = []
    for (item, unit), s in sold.items():
        b = bought.get((item, unit))
        if not b:
            continue
        sell, buy = s["amount"] / s["qty"], b["amount"] / b["qty"]
        per = sell - buy
        out.append({"item": s["name"], "unit": s["unit_name"] or unit or "", "sell": round(sell), "buy": round(buy), "margin": round(per),
                    "pct": round(per / sell * 100) if sell else 0, "sold_qty": s["qty"], "total": round(per * s["qty"])})
    return sorted(out, key=lambda x: -x["total"])


def suppliers(days=120, today=None):
    """Per item: each supplier's average price per unit, cheapest first. Needs the supplier's name on the purchase."""
    rows = [r for r in _bought(_rows(days, today)) if r.get("customer")]
    by_item, names = {}, {}
    for r in rows:
        if not r.get("item") or not r.get("quantity"):
            continue
        k = _key(r["item"], r.get("unit"))
        if k[0] in _NOT_GOODS:
            continue
        names.setdefault(k, (r["item"].strip().lower(), (r.get("unit") or "").strip().lower()))
        who = by_item.setdefault(k, {})
        g = who.setdefault(r["customer"], {"qty": 0.0, "amount": 0.0, "last": ""})
        g["qty"] += float(r["quantity"])
        g["amount"] += float(r["amount"])
        g["last"] = max(g["last"], r["created_at"][:10])
    out = []
    for (item, unit), who in by_item.items():
        offers = sorted(({"supplier": name, "price": round(g["amount"] / g["qty"]), "qty": g["qty"], "last": g["last"]}
                         for name, g in who.items() if g["qty"] > 0), key=lambda x: x["price"])
        if offers:
            out.append({"item": names[(item, unit)][0], "unit": names[(item, unit)][1] or unit or "", "offers": offers,
                        "saving": offers[-1]["price"] - offers[0]["price"] if len(offers) > 1 else 0})
    return sorted(out, key=lambda x: (-len(x["offers"]), -x["saving"]))


# ---------------------------------------------------------------- repeat orders ("Mama Tunde buys 4 crates of egg every Friday")

def repeat_orders(today=None, weeks=8, min_times=3, only_today=True):
    """Same customer + same item, bought on the same weekday at least `min_times` times in the last `weeks` weeks,
    the last time within 2 weeks. only_today: just the ones whose day is today and that aren't recorded yet today.
    Suggestions only: the trader confirms before anything is saved."""
    from statistics import median

    today = today or dt.date.today()
    rows = [r for r in _rows(weeks * 7, today) if r["type"] in ("sale", "credit_sale") and r.get("customer_id")
            and r.get("item") and r["created_at"][:10] < today.isoformat()]
    groups = {}
    for r in rows:
        d = dt.date.fromisoformat(r["created_at"][:10])
        groups.setdefault((r["customer_id"], _key(r["item"], r.get("unit"))[0], d.weekday()), []).append(r)
    done_today = set()
    with ledger.conn() as c:
        for r in c.execute("SELECT customer_id, item FROM entries WHERE substr(created_at,1,10)=?", (today.isoformat(),)):
            if r["customer_id"] and r["item"]:
                done_today.add((r["customer_id"], _key(r["item"], None)[0]))
    out = []
    for (cid, item, wday), rs in groups.items():
        days = sorted({r["created_at"][:10] for r in rs})
        if len(days) < min_times or (today - dt.date.fromisoformat(days[-1])).days > 14:
            continue
        if only_today and (wday != today.weekday() or (cid, item) in done_today):
            continue
        qtys = [float(r["quantity"]) for r in rs if r.get("quantity")]
        qty = median(qtys) if qtys else None
        per = [r["amount"] / float(r["quantity"]) for r in rs if r.get("quantity")]
        amount = round(median(per) * qty, -1) if qty and per else round(median([r["amount"] for r in rs]), -1)
        kinds = [r["type"] for r in rs]
        last = rs[-1]
        out.append({"customer_id": cid, "customer": last["customer"], "item": last["item"], "unit": last.get("unit") or "",
                    "quantity": qty, "amount": amount, "type": max(set(kinds), key=kinds.count),
                    "weekday": WEEKDAYS[wday], "times": len(days), "last": days[-1]})
    return sorted(out, key=lambda x: -x["times"])


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def top_items(days=14, today=None, n=5):
    rows = [r for r in _rows(days, today) if r["type"] in ("sale", "credit_sale") and r["item"]]
    agg = defaultdict(lambda: {"revenue": 0.0, "qty": 0.0, "unit": None, "count": 0})
    for r in rows:
        a = agg[r["item"]]
        a["revenue"] += r["amount"]
        a["qty"] += r["quantity"] or 0
        a["unit"] = a["unit"] or r["unit"]
        a["count"] += 1
    return sorted(({"item": k, **v} for k, v in agg.items()), key=lambda x: -x["revenue"])[:n]


# ---------------------------------------------------------------- debt reminders

TEMPLATES = {
    "English": ("Good day {name} . A gentle reminder about the {amount} balance for {items} from {since}. "
                "Please can you pay today or tell me when? Thank you, {shop}."),
    "Pidgin": ("Good day {name} . Abeg no vex, na small reminder for the {amount} wey remain for {items} "
               "since {since}. You fit pay today or tell me when you go pay? Thank you, {shop}."),
    # Yoruba: have a native speaker check this wording before the demo.
    "Yoruba": ("Ẹ káàárọ̀ {name} . Ẹ jọ̀wọ́, mo fẹ́ rán yín létí owó {amount} tí ó kù fún {items} láti {since}. "
               "Ṣé ẹ lè san án lónìí, tàbí ẹ sọ ìgbà tí ẹ máa san? Ẹ ṣé o, {shop}."),
}


def reminder(customer, language="Pidgin", shop="your trader", today=None, customer_id=None):
    """Polite reminder text + a WhatsApp link. The trader sends it; with the customer's phone saved the link opens
    their chat directly, otherwise WhatsApp asks the trader to pick the contact."""
    owing = ledger.debtors(today)
    if customer_id is not None:
        d = next((x for x in owing if x["customer_id"] == customer_id), None)
    else:
        d = next((x for x in owing if ledger.customer_key(x["customer"]) == ledger.customer_key(customer)), None)
    if not d:
        return None, None
    try:
        since = dt.date.fromisoformat(d["due_date"]).strftime("%-d %b") if d["due_date"] else "last time"
    except ValueError:
        since = d["due_date"]
    msg = TEMPLATES.get(language, TEMPLATES["English"]).format(
        name=d["customer"], amount=naira(d["balance"]), items=", ".join(d["items"]) or "goods",
        since=since, shop=shop)
    # wa.me without a number opens WhatsApp and lets the trader choose the contact and press send themselves
    cust = ledger.get_customer(d["customer_id"]) if d.get("customer_id") else None
    phone = "".join(ch for ch in ((cust or {}).get("phone") or "") if ch.isdigit())
    if phone.startswith("0") and len(phone) == 11:  # 0803… -> 234803…
        phone = "234" + phone[1:]
    return msg, f"https://wa.me/{phone}?text=" + urllib.parse.quote(msg)


# ---------------------------------------------------------------- ask my book

def book_facts(today=None):
    today = today or dt.date.today()
    week = defaultdict(float)
    for r in _rows(7, today):
        week[ledger.kind(r)] += r["amount"]
    week["expense"] += week["credit_purchase"]  # goods taken on credit are spending too
    f = forecast(today)
    p = ledger.credit_profile(today)
    return {
        "today": ledger.day_summary(today),
        "last_7_days": {"sales": week["sale"] + week["credit_sale"], "expenses": week["expense"],
                        "debts_collected": week["payment_received"],
                        "sales_minus_expenses": week["sale"] + week["credit_sale"] - week["expense"]},
        "debtors": [{k: d[k] for k in ("customer", "balance", "due_date", "overdue", "days_late", "items")}
                    for d in ledger.debtors(today)],
        "i_owe_suppliers": [{k: c[k] for k in ("customer", "balance", "due_date", "overdue", "days_late")}
                            for c in ledger.creditors(today)],
        "top_items_14_days": top_items(14, today),
        "forecast_next_7_days": None if not f else {
            "expected_sales": round(f["week_sales"]), "expected_cash_after_expenses": round(f["expected_cash"]),
            "busiest_day": f["busiest_day"]},
        "record_score": None if not p else {"score": p["score"], "band": p["band"]},
    }


ASK_PROMPT = """You are TradeVoice, a calm bookkeeping helper for a Nigerian market trader.
Answer the trader's question using ONLY the facts in the JSON below. Use naira with commas (₦45,000).
Reply in the same style the trader used (English or Nigerian Pidgin), in 1-4 short sentences.
If the facts do not contain the answer, say you don't have that record yet. Never invent numbers.
Never give investment, tax or legal advice; for loans, remind them a lender makes the decision. No emojis.
Be calm: no praise, no exclamation marks, and don't ask the trader questions. If the message is not a question about
the book (small talk, a list they shared, something you can't see), say in one sentence what you can do: write down
sales, debts and spending, and answer questions about their book.
"""


def ask_offline(question, facts):
    q = question.lower()
    if re.search(r"\b(i|we)\s+(still\s+|dey\s+)?(owe|owing)\b|who i owe|my supplier", q):
        cs = [c for c in facts["i_owe_suppliers"] if c["customer"].lower() in q] or facts["i_owe_suppliers"]
        if not cs:
            return "You don't owe any supplier right now."
        return " ".join(f"You owe {c['customer']} {naira(c['balance'])}" + (" (late)." if c["overdue"] else ".")
                        for c in cs[:5])
    if any(w in q for w in ("owe", "debt", "credit", "gbese")):
        who = [d for d in facts["debtors"] if d["customer"].lower() in q]
        ds = who or facts["debtors"]
        if not ds:
            return "Nobody owes you money right now."
        return " ".join(f"{d['customer']} owes {naira(d['balance'])}" + (" (late)." if d["overdue"] else ".")
                        for d in ds[:5])
    if any(w in q for w in ("sell pass", "best", "top", "fast")):
        t = facts["top_items_14_days"]
        return ("Your best sellers in 2 weeks: " + ", ".join(f"{x['item']} ({naira(x['revenue'])})" for x in t[:3])
                + ".") if t else "No item sales recorded yet."
    if any(w in q for w in ("next week", "forecast", "expect", "go make")):
        f = facts["forecast_next_7_days"]
        return (f"Next 7 days you fit sell about {naira(f['expected_sales'])}; cash after expenses about "
                f"{naira(f['expected_cash_after_expenses'])}. {f['busiest_day']} na your busiest day.") if f else \
            "I need more records to forecast."
    if "week" in q:
        w = facts["last_7_days"]
        return f"Last 7 days: sales {naira(w['sales'])}, expenses {naira(w['expenses'])}."
    t = facts["today"]
    return (f"Today: sales {naira(t['sales'])}, expenses {naira(t['expenses'])}, "
            f"sales minus expenses {naira(t['profit'])}.")


def ask(question, today=None):
    import askbook

    exact = askbook.ask_book(question, today)  # counts and totals: computed exactly, answered in their language
    if exact:
        return exact[0], exact[4]
    facts = book_facts(today)
    import llm

    if not llm.available():
        return ask_offline(question, facts), "rules"
    try:
        import assistant
        answer, model = llm.chat([{"role": "system", "content": ASK_PROMPT + assistant.who_line() + "\nFACTS:\n"
                                   + json.dumps(facts, default=str)},
                                  {"role": "user", "content": question}], max_tokens=400, temperature=0.2, timeout=30)
        if not assistant.calm_ok(answer):   # cheering or chit-chat: the honest fallback instead
            print(f"AI answer refused (not calm / no fact): {answer[:80]!r}")
            return None, "rules"
        return answer, f"llm:{model}"
    except Exception as e:
        return ask_offline(question, facts) + f"\n\n_(AI unavailable, offline answer: {type(e).__name__})_", "rules"


# ---------------------------------------------------------------- lender statement

def statement_html(business="My Shop", owner="", today=None):
    today = today or dt.date.today()
    p = ledger.credit_profile(today)
    if not p:
        return None
    with ledger.conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM entries ORDER BY created_at")]
    weeks = defaultdict(lambda: defaultdict(float))
    for r in rows:
        d = dt.date.fromisoformat(r["created_at"][:10])
        weeks[(d - dt.timedelta(days=d.weekday())).isoformat()][ledger.kind(r)] += r["amount"]
    wk_rows = "".join(
        f"<tr><td>Week of {w}</td><td>{naira(t['sale'] + t['credit_sale'])}</td>"
        f"<td>{naira(t['expense'] + t['credit_purchase'])}</td>"
        f"<td>{naira(t['sale'] + t['credit_sale'] - t['expense'] - t['credit_purchase'])}</td><td>{naira(t['payment_received'])}</td></tr>"
        for w, t in sorted(weeks.items()))
    parts = "".join(f"<tr><td>{html.escape(k)}</td><td>{v[0]:.0f} / {v[1]}</td><td>{html.escape(v[2])}</td></tr>"
                    for k, v in p["parts"].items())
    demo = ("<p class='warn'>This statement contains SYNTHETIC DEMO DATA created for a hackathon "
            "presentation. It is not a real business record.</p>") if p["has_demo_data"] else ""
    e = html.escape
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Business Record Statement</title>
<style>body{{font-family:system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#1b1b1b}}
h1{{color:#1f7a3a;margin-bottom:0}} table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border:1px solid #ccc;padding:6px 8px;text-align:left}} th{{background:#eef6f0}}
.big{{font-size:28px;font-weight:700}} .warn{{background:#fff3cd;padding:8px;border-radius:6px}}
small{{color:#555}}</style></head><body>
<h1>Business Record Statement</h1>
<p><b>{e(business)}</b>{' · ' + e(owner) if owner else ''}<br><small>Generated {today.isoformat()} by TradeVoice ·
records from {p['span_days']} days ({p['days_recorded']} days with entries)</small></p>{demo}
<p class="big">Record score: {p['score']}/100 ({p['band']})</p>
<table><tr><th>Total sales</th><th>Total expenses</th><th>Sales − expenses</th><th>Avg daily sales</th>
<th>Owed to business</th></tr><tr><td>{naira(p['revenue'])}</td><td>{naira(p['expenses'])}</td>
<td>{naira(p['profit'])}</td><td>{naira(p['avg_daily_sales'])}</td><td>{naira(p['outstanding'])}
({naira(p['overdue'])} overdue)</td></tr></table>
<p>Owed by the business to suppliers/lenders: <b>{naira(p['owed_to_suppliers'])}</b></p>
<h3>Weekly summary</h3><table><tr><th>Week</th><th>Sales</th><th>Expenses</th><th>Sales − expenses</th>
<th>Debts collected</th></tr>{wk_rows}</table>
{_year_tables(today)}
<h3>How the score is calculated</h3><table><tr><th>Factor</th><th>Points</th><th>Basis</th></tr>{parts}</table>
<p><small>This statement is generated from records entered and confirmed by the business owner. It has not been
audited. The score is a transparent indicator, not a credit decision; any lending decision must be made by the
lender after its own checks.</small></p></body></html>"""


# ---------------------------------------------------------------- year record (tax office, lender, the trader)

def year_record(year=None, today=None):
    """This year so far, from the trader's own records."""
    today = today or dt.date.today()
    year = year or today.year
    end = min(dt.date(year, 12, 31), today)
    return ledger.period_summary(dt.date(year, 1, 1), end), ledger.monthly_totals(year)


def year_data(today=None):
    """This year, as numbers for the Profile screen (the words come from ui_text, so every language works)."""
    s, months = year_record(today=today)
    if not s["entries"]:
        return None
    best = max(months, key=lambda m: m["sales"]) if len(months) > 1 else None
    restock = s["expenses_by_type"].get("Restock (goods to sell)", 0)
    return {"start": s["start"], "end": s["end"], "days_recorded": s["days_recorded"], "sales": s["sales"],
            "credit_sales": s["credit_sales"], "expenses": s["expenses"], "profit": s["profit"],
            "by_type": [{"type": k, "amount": v} for k, v in s["expenses_by_type"].items()],
            "rent_levies": {"count": len(s["rent_levies"]), "amount": sum(x["amount"] for x in s["rent_levies"])},
            "stock_note": s["profit"] < 0 and restock > 0,
            "months": [{"month": m["month"], "sales": m["sales"]} for m in months],
            "best_month": {"month": best["month"], "sales": best["sales"]} if best else None,
            "has_demo_data": s["has_demo_data"]}


def year_record_text(year=None, today=None):
    """Plain words for the app, a WhatsApp message or a voice note. Facts from the book only: no tax advice."""
    s, months = year_record(year, today)
    if not s["entries"]:
        return "No records this year yet."
    lines = [f"Your business from {s['start']} to {s['end']} ({s['days_recorded']} days recorded):",
             f"- Sales: {naira(s['sales'])} ({naira(s['credit_sales'])} of it on credit)",
             f"- Money spent: {naira(s['expenses'])}"]
    lines += [f"    - {k}: {naira(v)}" for k, v in s["expenses_by_type"].items()]
    lines.append(f"- Sales minus money spent: {naira(s['profit'])}")
    if s["rent_levies"]:
        lines.append(f"- Rent and levies paid: {len(s['rent_levies'])} payments, "
                     f"{naira(sum(x['amount'] for x in s['rent_levies']))}. Keep the receipts.")
    if len(months) > 1:
        best = max(months, key=lambda m: m["sales"])
        lines.append(f"- Best month: {best['month']} ({naira(best['sales'])} sales)")
    lines.append("This is from your own records, not an audit. Record every day so it stays true.")
    return "\n".join(lines)


def _year_tables(today):
    s, months = year_record(today=today)
    if not s["entries"]:
        return ""
    by_type = "".join(f"<tr><td>{html.escape(k)}</td><td>{naira(v)}</td></tr>"
                      for k, v in s["expenses_by_type"].items())
    month_rows = "".join(f"<tr><td>{m['month']}</td><td>{naira(m['sales'])}</td><td>{naira(m['expenses'])}</td>"
                         f"<td>{naira(m['profit'])}</td><td>{m['days_recorded']}</td></tr>" for m in months)
    rl = "".join(f"<tr><td>{x['date']}</td><td>{x['kind']}</td><td>{html.escape(x['item'] or '')}</td>"
                 f"<td>{naira(x['amount'])}</td></tr>" for x in s["rent_levies"])
    return f"""<h3>This year ({s['start']} to {s['end']})</h3>
<table><tr><th>Month</th><th>Sales</th><th>Money spent</th><th>Sales − spent</th><th>Days recorded</th></tr>
{month_rows}<tr><th>Total</th><th>{naira(s['sales'])}</th><th>{naira(s['expenses'])}</th>
<th>{naira(s['profit'])}</th><th>{s['days_recorded']}</th></tr></table>
<h3>Money spent by type</h3><table><tr><th>Type</th><th>Amount</th></tr>{by_type}</table>
{"<h3>Rent and levies paid (keep the receipts)</h3><table><tr><th>Date</th><th>Type</th><th>What</th><th>Amount</th></tr>" + rl + "</table>" if rl else ""}"""
