"""Money features on top of the ledger: forecast, top items, debt reminders, Ask-my-book, lender statement.
All numbers are computed here in plain Python; the LLM only phrases answers from these facts.
"""
import datetime as dt
import html
import json
import os
import statistics
import urllib.parse
from collections import defaultdict

import ledger

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def naira(x):
    return f"₦{x:,.0f}"


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
    "English": ("Good day {name} 🙏. A gentle reminder about the {amount} balance for {items} from {since}. "
                "Please can you pay today or tell me when? Thank you, {shop}."),
    "Pidgin": ("Good day {name} 🙏. Abeg no vex, na small reminder for the {amount} wey remain for {items} "
               "since {since}. You fit pay today or tell me when you go pay? Thank you, {shop}."),
    # Yoruba: have a native speaker check this wording before the demo.
    "Yoruba": ("Ẹ káàárọ̀ {name} 🙏. Ẹ jọ̀wọ́, mo fẹ́ rán yín létí owó {amount} tí ó kù fún {items} láti {since}. "
               "Ṣé ẹ lè san án lónìí, tàbí ẹ sọ ìgbà tí ẹ máa san? Ẹ ṣé o, {shop}."),
}


def reminder(customer, language="Pidgin", shop="your trader", today=None):
    d = next((x for x in ledger.debtors(today) if ledger.customer_key(x["customer"]) == ledger.customer_key(customer)),
             None)
    if not d:
        return None, None
    since = d["due_date"] or "last time"
    msg = TEMPLATES.get(language, TEMPLATES["English"]).format(
        name=d["customer"], amount=naira(d["balance"]), items=", ".join(d["items"]) or "goods",
        since=since, shop=shop)
    # wa.me without a number opens WhatsApp and lets the trader choose the contact and press send themselves
    return msg, "https://wa.me/?text=" + urllib.parse.quote(msg)


# ---------------------------------------------------------------- ask my book

def book_facts(today=None):
    today = today or dt.date.today()
    week = defaultdict(float)
    for r in _rows(7, today):
        week[r["type"]] += r["amount"]
    f = forecast(today)
    p = ledger.credit_profile(today)
    return {
        "today": ledger.day_summary(today),
        "last_7_days": {"sales": week["sale"] + week["credit_sale"], "expenses": week["expense"],
                        "debts_collected": week["payment_received"],
                        "sales_minus_expenses": week["sale"] + week["credit_sale"] - week["expense"]},
        "debtors": [{k: d[k] for k in ("customer", "balance", "due_date", "overdue", "days_late", "items")}
                    for d in ledger.debtors(today)],
        "top_items_14_days": top_items(14, today),
        "forecast_next_7_days": None if not f else {
            "expected_sales": round(f["week_sales"]), "expected_cash_after_expenses": round(f["expected_cash"]),
            "busiest_day": f["busiest_day"]},
        "record_score": None if not p else {"score": p["score"], "band": p["band"]},
    }


ASK_PROMPT = """You are TradeVoice, a friendly bookkeeping helper for a Nigerian market trader.
Answer the trader's question using ONLY the facts in the JSON below. Use naira with commas (₦45,000).
Reply in the same style the trader used (English or Nigerian Pidgin), in 1-4 short sentences.
If the facts do not contain the answer, say you don't have that record yet. Never invent numbers.
Never give investment, tax or legal advice; for loans, remind them a lender makes the decision.
FACTS:
"""


def ask_offline(question, facts):
    q = question.lower()
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
    facts = book_facts(today)
    if not os.getenv("NVIDIA_API_KEY"):
        return ask_offline(question, facts), "rules"
    try:
        import llm

        answer, model = llm.chat([{"role": "system", "content": ASK_PROMPT + json.dumps(facts, default=str)},
                                  {"role": "user", "content": question}], max_tokens=400, temperature=0.2, timeout=30)
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
        weeks[(d - dt.timedelta(days=d.weekday())).isoformat()][r["type"]] += r["amount"]
    wk_rows = "".join(
        f"<tr><td>Week of {w}</td><td>{naira(t['sale'] + t['credit_sale'])}</td><td>{naira(t['expense'])}</td>"
        f"<td>{naira(t['sale'] + t['credit_sale'] - t['expense'])}</td><td>{naira(t['payment_received'])}</td></tr>"
        for w, t in sorted(weeks.items()))
    parts = "".join(f"<tr><td>{html.escape(k)}</td><td>{v[0]:.0f} / {v[1]}</td><td>{html.escape(v[2])}</td></tr>"
                    for k, v in p["parts"].items())
    demo = ("<p class='warn'>⚠️ This statement contains SYNTHETIC DEMO DATA created for a hackathon "
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
<h3>Weekly summary</h3><table><tr><th>Week</th><th>Sales</th><th>Expenses</th><th>Sales − expenses</th>
<th>Debts collected</th></tr>{wk_rows}</table>
<h3>How the score is calculated</h3><table><tr><th>Factor</th><th>Points</th><th>Basis</th></tr>{parts}</table>
<p><small>This statement is generated from records entered and confirmed by the business owner. It has not been
audited. The score is a transparent indicator, not a credit decision; any lending decision must be made by the
lender after its own checks.</small></p></body></html>"""
