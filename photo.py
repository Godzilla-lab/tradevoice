"""Notebook photo -> draft rows -> the trader ticks/fixes -> saved. Shared by the web app and the WhatsApp bot."""
import ledger
from extract import TYPES, extract_many

LABEL = {"sale": "🛒 Sold", "credit_sale": "📝 Sold on credit", "payment_received": "💰 Paid me back",
         "expense": "💸 Spent", "credit_purchase": "📦 Bought on credit", "payment_made": "↩️ I paid back"}


def read(path):
    """Photo file -> {rows, lines, engine, brain, ms}. Raises if no vision model is set up."""
    from vision import read_notebook

    res = read_notebook(path)
    if not res["text"]:
        return {"rows": [], "lines": "", "engine": res["engine"]}
    recs, meta = extract_many(res["text"])
    return {"rows": [row(r) for r in recs], "lines": res["text"], "engine": res["engine"],
            "brain": meta["engine"], "ms": res["latency_ms"] + meta["latency_ms"]}


def row(r):
    checks = []
    if r["amount"] is None:
        checks.append("add amount")
    if r["confidence"] < 0.6:
        checks.append("check this")
    if r.get("note"):
        checks.append(r["note"])
    if r["type"] == "credit_sale" and r.get("customer"):
        risk = ledger.customer_risk(r["customer"])
        if risk["level"] in ("medium", "high"):
            checks.append(risk["message"])
    return {"save": r["amount"] is not None and r["confidence"] >= 0.6, "type": r["type"], "amount": r["amount"],
            "customer": r.get("customer") or "", "due_date": r.get("due_date") or "", "item": r.get("item") or "",
            "quantity": r.get("quantity"), "unit": r.get("unit") or "", "line": r.get("line") or "",
            "checks": checks}


def save(rows, engine="photo"):
    """Save the ticked rows. Returns {saved, problems}."""
    saved, problems = 0, []
    for n, r in enumerate(rows, 1):
        if not r.get("save"):
            continue
        try:
            amount = float(str(r.get("amount") or 0).replace(",", "").replace("₦", ""))
        except ValueError:
            amount = 0
        if r.get("type") not in TYPES or amount <= 0:
            problems.append(f"line {n}: needs a type and an amount")
            continue
        qty = r.get("quantity")
        ledger.add_entry({"type": r["type"], "amount": amount, "customer": (r.get("customer") or "").strip() or None,
                          "due_date": (r.get("due_date") or "").strip() or None,
                          "item": (r.get("item") or "").strip() or None,
                          "quantity": float(qty) if qty not in (None, "") else None,
                          "unit": (r.get("unit") or "").strip() or None},
                         raw_text=r.get("line") or "", engine=engine)
        saved += 1
    return {"saved": saved, "problems": problems}


def as_text(rows):
    """Numbered list for WhatsApp: '1. ✅ 📝 Sold on credit · Mama Tunde · ₦45,000'."""
    out = []
    for n, r in enumerate(rows, 1):
        amt = f"₦{float(r['amount']):,.0f}" if r.get("amount") not in (None, "") else "₦?"
        bits = [LABEL.get(r["type"], r["type"]), r.get("item"), r.get("customer"), amt]
        line = f"{n}. {'✅' if r.get('save') else '⬜'} " + " · ".join(b for b in bits if b)
        if r.get("checks"):
            line += f"\n    ⚠️ {'; '.join(r['checks'])}"
        out.append(line)
    return "\n".join(out)
