"""The Ask chat's brain: a real language model that reads the conversation, uses the book's tools and writes the reply.

The model (NVIDIA's Nemotron first, N-ATLaS as the backup; N-ATLaS first in Yoruba, Hausa and Igbo) decides what the
trader means and which tool to use. Code does everything with money: the tools read the trader's own book, the
calculator only uses numbers that were said or came from a tool, and a record is only ever drafted by the existing
record flow (read back, "Should I save it?"). Before a reply is shown, code checks every number in it came from the
book, a tool or the trader's words, and that it is calm and about the shop. If anything fails, the rules answer.

The protocol is plain JSON (works with any model; N-ATLaS gets it as guided JSON):
  {"tool": "<name>", "args": {...}}   -> code runs it and gives back the result
  {"reply": "<words for the trader>"}  -> the answer
"""
import datetime as dt
import json
import os
import re

import askbook
import ledger

MAX_STEPS = 4
PERIODS = ("today", "yesterday", "this_week", "last_week", "this_month", "last_month", "this_year", "last_7",
           "last_30", "all")
TOOLS = ("book_summary", "who_owes", "i_owe", "customers", "sales", "calculate", "date", "record")

PROMPT = """You are TradeVoice, the record book of a Nigerian market trader (__TRADER__). Today is __TODAY__.
You talk with the trader in __LANG__. You can ONLY help with their shop: sales, spending, who owes them, who they owe,
their customers, prices and simple sums. Anything else (health, news, jokes, other topics): say in one sentence that
you can only help with their shop.

You never know a number until a tool gives it to you. Use the tools; never guess or invent a number or a name.
Reply with ONE JSON object and nothing else, either a tool call or the answer:
  {"tool": "<name>", "args": {...}}
  {"reply": "<1-3 short calm sentences for the trader>"}

Tools:
- book_summary {"period": one of today, yesterday, this_week, last_week, this_month, last_month, this_year, last_7,
  last_30, all}: sales, cash sales, credit sales, money paid back, spending, sales minus spending, for that period.
  "the last month" / "past month" = last_30; "last month" = last_month.
- who_owes {"names": [every person asked about] or null}: who owes the trader and how much, with pay-by dates and days
  late. With names: those people only (part of a name is fine, e.g. "ngozi"), and their total. When the trader asks
  about several people ("Mike and Dino"), put ALL of them in names and answer for each one.
- i_owe {"names": [people] or null}: who the trader owes (suppliers), the same way.
- customers {}: how many customers and their balances.
- sales {"item": an item or null, "customer": a name or null, "period": as above}: what was sold, how much, how many.
- calculate {"expression": "45000 - 45000 * 10%"}: arithmetic with + - * / and n%. Use only numbers the trader said
  or a tool gave you. Never do maths yourself; always use this tool.
- date {"words": "next friday" or a holiday like "christmas", "sallah", "easter"}: the date.
- record {}: the trader is telling you about a NEW sale, debt, payment or expense (or a list of them). Call it and
  stop: the record book reads it back and asks before saving. Never write a record yourself.

Rules for the reply: naira with commas (₦45,000). Calm: no praise, no exclamation marks, no emojis. Don't ask the
trader questions unless you need one missing fact. "she / he / they" = the person talked about last (see the
conversation). Say what the tool said; if a tool found nothing, say that plainly.
"""
SCHEMA = {"type": "object", "properties": {"tool": {"type": "string", "enum": list(TOOLS)}, "args": {"type": "object"},
                                           "reply": {"type": "string"}}}


def models(lang):
    """NVIDIA first (best understanding), N-ATLaS as the backup; in Yoruba / Hausa / Igbo N-ATLaS first."""
    big = [m.strip() for m in os.getenv("ASK_MODELS", "nvidia/nemotron-3-super-120b-a12b,google/gemma-4-31b-it")
           .split(",") if m.strip()]
    return ["natlas"] + big if lang in ("Yoruba", "Hausa", "Igbo") else big + ["natlas"]


def available(lang="English"):
    import llm

    have = [m for m in models(lang) if (m == "natlas" and llm.natlas_on()) or
            (m not in llm.OWN_SERVERS and os.getenv("NVIDIA_API_KEY"))]
    return bool(have) and os.getenv("ASK_BRAIN", "llm") == "llm"


# ---------------------------------------------------------------- the tools (code, on the trader's own book)
def _money(x):
    return round(float(x or 0))


def _person(name, rows):
    if not name:
        return None
    names = [r["customer"] for r in rows]
    hit = askbook.find_name(name, names)
    return [r for r in rows if hit and askbook.same_person(hit, r["customer"])] if hit else []


def _row(r):
    return {"name": r["customer"], "owes": _money(r["balance"]), "pay_by": r.get("due_date"),
            "days_late": r.get("days_late") or 0}


def run_tool(name, args, ctx):
    """-> a JSON-able result. ctx: {"today", "text", "lang", "state", "numbers": set of numbers seen so far}."""
    today, args = ctx["today"], args if isinstance(args, dict) else {}
    if name == "book_summary":
        period = args.get("period") if args.get("period") in PERIODS else "today"
        start, end = askbook._bounds(period, today)
        s = ledger.period_summary(start, end)
        return {"period": period, "from": s["start"], "to": s["end"], "records": s["entries"], "sales": _money(s["sales"]),
                "cash_sales": _money(s["cash_sales"]), "credit_sales": _money(s["credit_sales"]),
                "paid_back_to_you": _money(s["payments_received"]), "spending": _money(s["expenses"]),
                "sales_minus_spending": _money(s["profit"])}
    if name in ("who_owes", "i_owe"):
        rows = ledger.debtors(today) if name == "who_owes" else ledger.creditors(today)
        asked = args.get("names") if isinstance(args.get("names"), list) else ([args["name"]] if args.get("name") else [])
        asked = [str(a) for a in asked if a]
        if not asked:
            out = [_row(r) for r in rows[:15]]
            return {"people": out, "total": _money(sum(p["owes"] for p in out)), "count": len(rows)}
        out, notes = [], []
        for who in asked:   # each person asked about, in the order asked
            pick = _person(who, rows)
            if pick:
                out += [_row(r) for r in pick if _row(r) not in out]
                continue
            known = askbook.find_name(who, ledger.known_words(500)["names"])
            notes.append(f"{known} owes nothing now" if known else f"{who} is not in the book")
        if out:
            ctx["state"]["last_customer"] = out[-1]["name"]
        return {"people": out, "total": _money(sum(p["owes"] for p in out)), "count": len(out), "notes": notes}
    if name == "customers":
        conv = ledger.conversations(today)
        d = ledger.debtors(today)
        return {"customers": len(conv), "owing_you": len(d), "total_owed": _money(sum(x["balance"] for x in d)),
                "names": [c["name"] for c in conv[:30]]}
    if name == "sales":
        q = {"what": "sold", "item": args.get("item"), "customer": args.get("customer"),
             "period": args.get("period") if args.get("period") in PERIODS else "all"}
        res = askbook.run(q, today)
        return {"period": q["period"], "item": q["item"], "customer": q["customer"], "sales": _money(res["money"]),
                "records": res["entries"], "quantities": res.get("units") or {}}
    if name == "calculate":
        import tools

        try:
            value, working = tools.safe_eval(str(args.get("expression") or ""), ctx["numbers"])
        except tools.Refused as e:
            return {"error": f"can't work that out: {e}. Use only numbers the trader said or a tool gave."}
        return {"result": round(value, 2), "working": f"{working} = {tools.show(value)}"}
    if name == "date":
        import tools

        words = str(args.get("words") or "")
        hol = tools.holiday_in(words) if hasattr(tools, "holiday_in") else None
        r = tools.run_date({"holiday": hol} if hol else {"day": words}, words, ctx["lang"], today)
        return {"answer": r.get("text"), "date": r.get("value")}
    return {"error": f"no tool called {name}"}


def _numbers_in(obj):
    out = set()
    for n in re.findall(r"\d[\d,]*(?:\.\d+)?", json.dumps(obj, default=str)):
        try:
            out.add(float(n.replace(",", "")))
        except ValueError:
            pass
    return out


def _said_numbers(reply):
    out = []
    for m in re.finditer(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(\s*(?:k|m|million|thousand))?", reply or "", re.I):
        v = float(m.group(1).replace(",", ""))
        out.append(v * {"k": 1e3, "m": 1e6, "million": 1e6, "thousand": 1e3}.get((m.group(2) or "").strip().lower(), 1))
    return out


# ---------------------------------------------------------------- the conversation
def answer(text, state, lang="English", today=None):
    """One trader message -> {text, spoken, lang, engine[, record]} or None (no model / it failed: the rules answer).
    record=True: the message is a new record; the caller hands it to the record flow (converse.reply)."""
    import assistant
    import llm

    today = today or dt.date.today()
    hist = state.setdefault("history", [])
    prompt = (PROMPT.replace("__TRADER__", assistant.who_line()).replace("__LANG__", lang)
              .replace("__TODAY__", f"{today:%A %d %B %Y}"))
    msgs = [{"role": "system", "content": prompt}] + hist[-8:] + [{"role": "user", "content": text}]
    ctx = {"today": today, "text": text, "lang": lang, "state": state, "numbers": set(_numbers_from_text(text))}
    used = []
    for _ in range(MAX_STEPS):
        try:
            out, model = llm.chat(msgs, max_tokens=400, temperature=0.0, timeout=25, models=models(lang),
                                  schema=SCHEMA)
        except Exception as e:  # noqa: BLE001
            print(f"ask brain: no model answered ({type(e).__name__}: {e})")
            return None
        try:
            from extract import _parse_json

            step = _parse_json(out)
        except Exception:  # noqa: BLE001
            step = {"reply": (out or "").strip()} if out and "{" not in out else {}
        if step.get("tool") == "record":
            return {"record": True, "engine": f"llm:{model}"}
        if step.get("tool") in TOOLS:
            result = run_tool(step["tool"], step.get("args") or {}, ctx)
            ctx["numbers"] |= _numbers_in(result)
            used.append(step["tool"])
            msgs += [{"role": "assistant", "content": json.dumps({"tool": step["tool"], "args": step.get("args") or {}})},
                     {"role": "user", "content": f"TOOL RESULT {step['tool']}: {json.dumps(result, default=str)}"}]
            continue
        reply = (step.get("reply") or "").strip()
        if not reply:
            return None
        bad = [n for n in _said_numbers(reply) if n >= 100 and n not in ctx["numbers"]]
        if bad or not assistant.calm_ok(reply):
            print(f"ask brain: reply refused ({'numbers ' + str(bad) if bad else 'not calm'})")
            return None   # a number nobody gave, or cheering: the rules answer instead
        hist += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        del hist[:-12]
        return {"text": reply, "spoken": assistant.spoken(reply), "lang": lang, "engine": f"llm:{model}",
                "tools": used}
    return None


def _numbers_from_text(text):
    import extract

    return {float(v) for v in extract._amount_values(text)} | {
        float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")}


def remember(state, text, reply):
    """The record flow answered (a draft, a save): kept in the conversation so the model knows what happened."""
    hist = state.setdefault("history", [])
    hist += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
    del hist[:-12]
