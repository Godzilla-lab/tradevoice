"""Understand a LONG voice note: many money entries + a short summary in the trader's language + helpful extras.

"Mo bá ìyá Bísí sọ̀rọ̀ … balance mi 50,000 … bag rice àti spaghetti … ilé tí mò ń rent 1.8 million …"
→ entries (each checked like a single note), a 2–4 sentence summary of EVERYTHING said (in the reply language),
  helpful extras computed by us (rent per month/day, new debt totals, money in vs out), and questions for unclear parts.
Safety: the AI's summary may only use numbers that were said; otherwise we fall back to a summary built from the
entries. The extras never come from the AI.
⚠️ Yoruba/Hausa/Igbo sentences: native-speaker check.
"""
import datetime as dt
import os
import re

import llm
import ledger
from extract import (SYSTEM_PROMPT, _amount_values, _check_guard, _normalise, _parse_json, _sell_guard,
                     _words_amount, fold, rule_extract)

NOTE_PROMPT = """A Nigerian market trader sent a LONG voice note (English, Nigerian Pidgin, Yoruba, Hausa, Igbo or mixed).
Today is __TODAY__ (__WEEKDAY__). It may contain several money events and also talk that is not money.
Return ONLY this JSON:
{"entries": [ {"said": "<the exact words from the note this entry comes from>", "type": ..., "item": ...,
   "quantity": ..., "unit": ..., "amount": ..., "customer": ..., "due_date": ..., "confidence": ..., "note": ...} ],
 "summary_en": "<2-4 very short sentences in SIMPLE English covering EVERYTHING the trader said, also the non-money
                parts. Words a child understands, max 12 words per sentence. Amounts as digits with ₦ (₦50,000).
                Use ONLY numbers the trader said. No advice.>",
 "summary": "<the same summary in __LANG__, just as simple (it will be read aloud)>",
 "unclear_en": ["<short simple English question for each part you could not understand for sure>"],
 "unclear": ["<the same questions in __LANG__>"]}
One entry per money event that HAPPENED now: a sale, goods given on credit, money received, money spent, goods taken on
credit, a debt paid back. NOT entries (mention them in the summary only): asking someone to pay a debt they already owe
("I told Iya Bisi to bring my balance of 50k": that debt is already in the book), prices or costs just described
("the shop I rent is 1.8 million"), plans and talk. If it is not clear whether money moved, or what an amount is for,
do not guess: leave it out of "entries" and ask about it in "unclear". Entry fields mean exactly this:
""" + SYSTEM_PROMPT.split("Return ONLY a JSON object with these keys:")[1]

LANG_NAMES = {"Pidgin": "Nigerian Pidgin", "English": "simple Nigerian English", "Yoruba": "Yoruba (with tone marks)",
              "Hausa": "Hausa", "Igbo": "Igbo"}

# Helpful extras, computed from the entries (never by the AI). {a} amounts, {n} names.
EXTRA = {
    "rent": {"English": "If that rent of {a} is for one year, that is {m} a month, about {d} a day to set aside.",
             "Pidgin": "If that {a} rent na for one year, e mean {m} every month, like {d} every day to keep.",
             "Yoruba": "Tí owó ilé {a} yẹn bá jẹ́ ti ọdún kan, ó jẹ́ {m} lóṣù, nǹkan bí {d} lójoojúmọ́.",
             "Hausa": "Idan kuɗin haya {a} na shekara ɗaya ne, {m} ne a wata, kusan {d} a rana.",
             "Igbo": "Ọ bụrụ na ụgwọ ụlọ {a} bụ maka otu afọ, ọ bụ {m} kwa ọnwa, ihe dị ka {d} kwa ụbọchị."},
    "owes": {"English": "{n} will owe you {a} in total.", "Pidgin": "{n} go dey owe you {a} total.",
             "Yoruba": "Gbogbo gbèsè {n} yóò jẹ́ {a}.", "Hausa": "Jimlar bashin {n} zai zama {a}.",
             "Igbo": "Ụgwọ {n} niile ga-abụ {a}."},
    "inout": {"English": "In this note: {i} coming in, {o} going out.",
              "Pidgin": "For this note: {i} dey enter, {o} dey comot.",
              "Yoruba": "Nínú ọ̀rọ̀ yìí: {i} ń wọlé, {o} ń jáde.",
              "Hausa": "A wannan saƙo: {i} yana shigowa, {o} yana fita.",
              "Igbo": "N'ozi a: {i} na-abata, {o} na-apụ."},
}
ASK = {"English": "Check the list and tick what to save.", "Pidgin": "Check the list, tick wetin make I save.",
       "Yoruba": "Ẹ ṣàyẹ̀wò àkọsílẹ̀ náà, kí ẹ sì yan èyí tí mo máa kọ sílẹ̀.",
       "Hausa": "Duba jerin, ka zaɓi abin da za a rubuta.", "Igbo": "Lelee ndepụta ahụ, họrọ nke m ga-edebe."}
_RENT = ("rent", "owo ile", "haya", "ugwo ulo", "shop rent", "ile ti mo n")


def is_long(text):
    """Worth the 'whole note' treatment: several amounts or a long ramble."""
    t = text or ""
    amounts = [m for m in re.finditer(r"\d[\d,.]*\s*(k|m|million|thousand|naira)?\b", t, re.I) if len(m.group(0)) > 2]
    return len(amounts) >= 2 or len(t.split()) > 30


def _naira(x):
    return f"₦{x:,.0f}"


def _numbers(s):
    """Money-looking numbers in a text (₦50,000 / 1.8 million / 50k)."""
    out = set()
    for m in re.finditer(r"₦?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|m|million|thousand|milli)?", s or "", re.I):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        v *= {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "milli": 1e6}.get((m.group(2) or "").lower(), 1)
        if v >= 100:
            out.add(round(v, 2))
    return out


def _allowed_numbers(text, entries):
    ok = {round(v, 2) for v in _amount_values(text)} | {round(float(e["amount"]), 2) for e in entries if e.get("amount")}
    ok |= _numbers(text)
    w = _words_amount(text)
    if w:
        ok.add(float(w))
    return ok


def _entry_line(e, lang):
    import tts

    return tts.entry_sentence(e, lang, money=_naira)


def _rent_amount(entries, text):
    """Rent saved as an entry, or just mentioned ("the house I rent is 1.8 million"): the amount nearest a rent word."""
    for e in entries:
        words = fold(f"{e.get('item') or ''} {e.get('said') or ''}")
        if e["type"] == "expense" and (e.get("amount") or 0) >= 100_000 and any(w in words for w in _RENT):
            return float(e["amount"])
    t = fold(text or "")
    spots = [m.start() for w in _RENT for m in re.finditer(re.escape(w), t)]
    best = None
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(k|m|million|thousand)?\b", t):
        v = float(m.group(1).replace(",", "")) * {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}.get(
            (m.group(2) or ""), 1)
        dist = min((abs(m.start() - p) for p in spots), default=999)
        if v >= 100_000 and dist <= 60 and (best is None or dist < best[0]):
            best = (dist, v)
    return best[1] if best else None


def extras(entries, lang, today=None, text=""):
    """Deterministic helpful sentences (the AI never computes these)."""
    lang = lang if lang in EXTRA["rent"] else "English"
    out = []
    rent = _rent_amount(entries, text)
    if rent:
        out.append(EXTRA["rent"][lang].format(a=_naira(rent), m=_naira(rent / 12), d=_naira(round(rent / 365, -2))))
    debts = {}
    for e in entries:
        if e["type"] in ("credit_sale", "payment_received") and e.get("customer") and e.get("amount"):
            debts.setdefault(e["customer"], 0)
            debts[e["customer"]] += e["amount"] if e["type"] == "credit_sale" else -e["amount"]
    for name, change in debts.items():
        before = ledger.balance_with(name, today)[0]
        if change and before + change > 0:
            out.append(EXTRA["owes"][lang].format(n=name, a=_naira(before + change)))
    money_in = sum(e["amount"] or 0 for e in entries if e["type"] in ("sale", "payment_received"))
    money_out = sum(e["amount"] or 0 for e in entries if e["type"] in ("expense", "payment_made"))
    if len(entries) > 1 and money_in and money_out:
        out.append(EXTRA["inout"][lang].format(i=_naira(money_in), o=_naira(money_out)))
    return out


def _check_entry(raw, text, today):
    said = (raw.get("said") or "").strip()
    scope = said if said and fold(said[:20]) in fold(text) else text
    rec = _normalise(raw, scope, today)
    rules = rule_extract(scope, today)
    rec = _check_guard(_sell_guard(rec, rules, scope), rules, scope, today)
    # money must have been said somewhere in the note
    if rec.get("amount") is not None and float(rec["amount"]) not in _allowed_numbers(text, []):
        rec["note"] = ((rec.get("note") or "") + f" Amount {_naira(rec['amount'])} was not said: please check.").strip()
        rec["amount"], rec["confidence"] = None, min(rec.get("confidence") or 0.3, 0.3)
    rec["said"] = said or None
    return rec


_SPLIT = re.compile(r"[.;!?\n]+|,\s*|\b(?:then|and then|also|plus|after that|and)\b", re.I)


def offline_split(text, today=None):
    """No AI: cut the note into clauses and read each clause with an amount on its own. Entries come back UNTICKED
    (the trader must check each one), because the rules can't tell a described price from a payment."""
    today = today or dt.date.today()
    out = []
    for clause in (c.strip() for c in _SPLIT.split(text or "") if c and c.strip()):
        rec = rule_extract(clause, today)
        if rec.get("amount") is not None:
            rec["said"] = clause
            rec["note"] = ((rec.get("note") or "") + " Offline reading: please check.").strip()
            rec["confidence"] = min(rec.get("confidence") or 0.3, 0.4)
            out.append(rec)
    return out


def understand(text, lang="Pidgin", today=None, vocab=None):
    """Return {entries, summary, extras, unclear, engine, error, summary_source}."""
    today = today or dt.date.today()
    lang = lang if lang in LANG_NAMES else "Pidgin"
    out = {"entries": [], "summary": "", "summary_en": "", "extras": [], "extras_en": [], "unclear": [],
           "unclear_en": [], "engine": "rules", "error": None, "summary_source": "built from the entries"}
    if llm.available():
        try:
            prompt = (NOTE_PROMPT.replace("__TODAY__", today.isoformat()).replace("__WEEKDAY__", today.strftime("%A"))
                      .replace("__LANG__", LANG_NAMES[lang]))
            if vocab and vocab.get("names"):
                prompt += f"\nPeople already in this trader's book: {', '.join(vocab['names'])}."
            content, model = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": text}],
                                      max_tokens=1500, timeout=int(os.getenv("LLM_TIMEOUT", "20")))
            data = _parse_json(content)
            out["entries"] = [_check_entry(e, text, today) for e in data.get("entries") or [] if isinstance(e, dict)]
            out["unclear"] = [str(u) for u in data.get("unclear") or [] if str(u).strip()][:3]
            out["unclear_en"] = [str(u) for u in data.get("unclear_en") or [] if str(u).strip()][:3]
            summary = str(data.get("summary") or "").strip()
            summary_en = str(data.get("summary_en") or "").strip() or (summary if lang == "English" else "")
            bad = (_numbers(summary) | _numbers(summary_en)) - _allowed_numbers(text, out["entries"])
            if summary and summary_en and not bad:
                out["summary"], out["summary_en"] = summary, summary_en
                out["summary_source"] = "AI summary (every number checked against your note)"
            elif bad:
                out["error"] = f"summary used numbers you didn't say ({', '.join(_naira(b) for b in sorted(bad))})"
            out["engine"] = f"llm:{model}"
        except Exception as e:  # noqa: BLE001 - fall back to one entry, never crash
            out["error"] = f"{type(e).__name__}: {str(e)[:80]}"
    if not out["entries"] and (out["error"] or not llm.available()):
        out["entries"] = offline_split(text, today)
        out["offline"] = True
    if not out["summary"]:
        out["summary"] = " ".join(_entry_line(e, lang) for e in out["entries"] if e.get("amount")) or ""
        out["summary_en"] = " ".join(_entry_line(e, "English") for e in out["entries"] if e.get("amount")) or ""
    out["extras"] = extras(out["entries"], lang, today, text)
    out["extras_en"] = extras(out["entries"], "English", today, text)
    out["unclear_en"] = out["unclear_en"] or (out["unclear"] if lang == "English" else [])
    return out


def spoken_text(result, lang):
    """What the voice reply says: summary + extras + questions + 'check the list', amounts in words."""
    import tts

    lang = lang if lang in ASK else "English"
    text = " ".join([result["summary"], *result["extras"], *result["unclear"], ASK[lang]])
    return re.sub(r"-?₦\s?(\d[\d,]*(?:\.\d+)?)", lambda m: tts.naira_words(float(m.group(1).replace(",", ""))), text)
