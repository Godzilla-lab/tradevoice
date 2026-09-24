"""Turn a trader's voice-note transcript into one ledger entry.

Primary engine: an LLM on build.nvidia.com (OpenAI-compatible API).
Fallback engine: deterministic rules (works offline, no key needed).
The rules also backfill fields the LLM missed, e.g. the amount.
"""
import datetime as dt
import json
import os
import re
import time
import unicodedata

TYPES = ("sale", "credit_sale", "payment_received", "expense")
import llm

SYSTEM_PROMPT = """You turn a Nigerian market trader's voice note (English, Nigerian Pidgin, or mixed) into ONE bookkeeping record.
Today is __TODAY__ (__WEEKDAY__).
Return ONLY a JSON object with these keys:
- "type": one of "sale" (customer paid now), "credit_sale" (customer took goods and will pay later / owes), "payment_received" (customer paying back an earlier debt), "expense" (the trader spent money: restock, transport, rent, levy, fuel, etc.)
- "item": short product or expense name, or null
- "quantity": number or null
- "unit": e.g. "bag", "carton", "crate", "paint", "mudu", or null
- "amount": TOTAL amount in naira as a plain number (45k -> 45000, 1.5m -> 1500000, "twenty thousand" -> 20000), or null if not said
- "customer": the person's name as said (e.g. "Mama Tunde", "Alhaji Musa"), or null
- "due_date": date the customer promised to pay, as YYYY-MM-DD, or null
- "confidence": number 0-1, how sure you are
- "note": short description of anything unclear, or null
Pidgin hints: "e don pay", "don settle", "come pay" = payment_received. "go pay", "owe", "na credit", "never pay", "balance remain" = credit_sale. "I buy", "I pay for" (the trader spending) = expense.
Never invent an amount or a name that was not said."""

# ---------------------------------------------------------------- rules

_SUFFIX = {"k": 1e3, "thousand": 1e3, "grand": 1e3, "m": 1e6, "mil": 1e6, "million": 1e6}
_AMOUNT_RE = re.compile(
    r"(?P<cur>₦|\bNGN\s?|\bN(?=\d))?\s*(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(?P<suf>k|thousand|grand|million|mil|m)?(?![a-z])(?P<naira>\s*naira)?",
    re.IGNORECASE,
)
_UNITS = (r"bags?|cartons?|crates?|pieces?|pcs|tins?|packs?|packets?|paints?|derica|mudu|"
          r"kg|kilos?|litres?|liters?|yards?|dozens?|sachets?|bottles?|tubers?|baskets?|rolls?|tubes?")
_QTY_RE = re.compile(rf"\b(\d+(?:\.\d+)?)\s*({_UNITS})\s+(?:of\s+)?([a-z]+(?:\s(?!for\b|to\b|give\b)[a-z]+)?)",
                     re.IGNORECASE)
_HONORIFIC = (r"mama|papa|iya|baba|alhaji|alhaja|madam|oga|aunty|auntie|uncle|mr\.?|mrs\.?|"
              r"chief|brother|sister|bros|mallam|iyawo|customer")
_NOT_NAMES = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
              "today", "tomorrow", "next", "week", "month", "i", "naira", "the", "me", "am", "am"}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# Weekday names in Yoruba / Hausa / Igbo, written WITHOUT tone marks (text is de-accented before matching).
# ⚠️ Have native speakers check these lists.
_LOCAL_WEEKDAYS = [
    ("aje", "litinin", "monde"), ("isegun", "talata", "tiuzdee"), ("ojoru", "laraba", "wenezdee"),
    ("ojobo", "alhamis", "tozdee"), ("eti", "juma'a", "fraidee"), ("abameta", "asabar", "satodee"),
    ("aiku", "lahadi", "sondee"),
]

# English / Pidgin keywords, then Yoruba (yo), Hausa (ha), Igbo (ig) WITHOUT tone marks. ⚠️ native-speaker check.
_PAYMENT_KW = ("don pay", "has paid", "have paid", "paid me", "pay me back", "come pay", "don settle",
               "settled", "don clear", "paid back", "payed back", "repaid", "cleared", "paid her debt", "paid his debt", "paid the balance",
               "pay the balance", "balance me",
               "ti san",                                   # yo: has paid
               "biya bashi", "biyan bashi", "na bashin",   # ha: paid the debt
               "akwuola", "kwuola", "kwuru ugwo")          # ig: has paid / paid the debt
_CREDIT_KW = ("owe", "owes", "owing", "go pay", "will pay", "on credit", "na credit", "credit", "later", "balance remain",
              "never pay", "no pay", "pay by", "pay on", "pay next",
              "gbese", "je mi", "yoo san", "o ma san",      # yo: debt, owes me, will pay
              "bashi", "za ta biya", "za ya biya",          # ha: debt, will pay
              "ugwo", "ji m", "ga-akwu", "ga akwu")         # ig: debt, owes me, will pay
_EXPENSE_RE = re.compile(r"\b(i|we)\s+(buy|bought|pay for|paid for|spend|spent|restock|restocked)\b"
                         r"|\b(i|we)\s+(pay|paid)\s+(n|₦)?\d"
                         r"|\b(transport|motor fare|rent|levy|fuel|diesel|salary|shop rent|market levy|restock)\b"
                         r"|\bmo san\b|\bowo oko\b"                # yo: I paid, transport money
                         r"|\bna biya\b|\bkudin mota\b"            # ha: I paid, transport money
                         r"|\bakwuru m\b|\bugbo ala\b",            # ig: I paid, vehicle
                         re.IGNORECASE)


_SELL_RE = re.compile(r"\b(sell|sold|ta|sayar|ere m|ree)\b")  # en, yo, ha, ig


def fold(text):
    """Lowercase and strip tone marks/diacritics: 'Gbèsè' -> 'gbese', 'ụgwọ' -> 'ugwo'."""
    t = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("’", "'")


def parse_amount(text):
    """Return the most likely naira amount in the text, or None."""
    best, best_score = None, -1
    for m in _AMOUNT_RE.finditer(text or ""):
        num = float(m.group("num").replace(",", ""))
        suf = (m.group("suf") or "").lower()
        value = num * _SUFFIX.get(suf, 1)
        score = 0
        if m.group("cur") or m.group("naira"):
            score += 3
        if suf:
            score += 3
        if "," in m.group("num"):
            score += 2
        if value >= 100:
            score += 1
        # a number immediately followed by a unit ("3 bags") is a quantity, not money
        tail = text[m.end():m.end() + 12].lower()
        if not suf and re.match(rf"\s*({_UNITS})\b", tail):
            score -= 5
        if score > best_score or (score == best_score and value > (best or 0)):
            best, best_score = value, score
    if best is None or best_score < 1:
        return None
    return int(best) if best == int(best) else best


def parse_due(text, today):
    t = fold(text)
    if re.search(r"\b(tomorrow|tomoro|tmrw|tomorow|gobe|echi)\b", t):
        return (today + dt.timedelta(days=1)).isoformat()
    if "next week" in t:
        return (today + dt.timedelta(days=7)).isoformat()
    if re.search(r"(month end|end of (the )?month)", t):
        nxt = (today.replace(day=28) + dt.timedelta(days=4))
        return (nxt - dt.timedelta(days=nxt.day)).isoformat()
    for i, day in enumerate(_WEEKDAYS):
        if any(re.search(rf"(?<![\w']){re.escape(n)}(?![\w'])", t) for n in (day, *_LOCAL_WEEKDAYS[i])):
            delta = (i - today.weekday()) % 7 or 7
            return (today + dt.timedelta(days=delta)).isoformat()
    return None


def parse_customer(text):
    text = text or ""
    m = re.search(rf"\b((?i:{_HONORIFIC})\s+[A-Z][\w']+)", text)
    if m:
        return m.group(1).strip()
    for m in re.finditer(r"\b(?i:give|to|for|from|by|fun|fún|ga|nye)\s+([A-Z][\w']+(?:\s[A-Z][\w']+)?)", text):
        name = m.group(1)
        if name.split()[0].lower() not in _NOT_NAMES:
            return name
    m = re.match(r"\s*([A-Z][\w']+)\s+(?i:don pay|has paid|paid|come pay|owe|ti san|ta biya|ya biya|akwụọla|akwuola)",
                 text)
    if m and m.group(1).lower() not in _NOT_NAMES:
        return m.group(1)
    return None


def parse_type(text):
    t = fold(text)
    if any(k in t for k in _PAYMENT_KW):
        return "payment_received"
    if _EXPENSE_RE.search(t) and not _SELL_RE.search(t):
        return "expense"
    if any(re.search(rf"(?<![\w-]){re.escape(k)}(?!\w)", t) for k in _CREDIT_KW):
        return "credit_sale"
    return "sale"


def rule_extract(text, today=None):
    today = today or dt.date.today()
    rec = {"type": parse_type(text), "item": None, "quantity": None, "unit": None,
           "amount": parse_amount(text), "customer": parse_customer(text), "due_date": None,
           "confidence": 0.3, "note": None}
    m = _QTY_RE.search(text or "")
    if m:
        rec["quantity"] = float(m.group(1)) if "." in m.group(1) else int(m.group(1))
        unit = m.group(2).lower()
        rec["unit"] = unit[:-1] if unit.endswith("s") and unit not in ("pcs",) else unit
        rec["item"] = m.group(3).lower()
    elif rec["type"] == "expense":
        k = _EXPENSE_RE.search(text or "")
        if k and k.group(3):
            rec["item"] = k.group(3).lower()
    if rec["type"] == "credit_sale":
        rec["due_date"] = parse_due(text, today)
    if rec["amount"] is not None:
        rec["confidence"] = 0.6
    else:
        rec["note"] = "No amount heard"
    return rec


# ---------------------------------------------------------------- LLM

def _parse_json(content):
    m = re.search(r"\{.*\}", llm.clean(content), re.DOTALL)
    if not m:
        raise ValueError("LLM returned no JSON")
    return json.loads(m.group(0))


def llm_extract(text, today=None):
    """Return (record dict, model used)."""
    today = today or dt.date.today()
    prompt = SYSTEM_PROMPT.replace("__TODAY__", today.isoformat()).replace("__WEEKDAY__", today.strftime("%A"))
    content, model = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": text}],
                              max_tokens=400, timeout=30)
    return _parse_json(content), model


def _normalise(rec, text, today):
    out = {k: rec.get(k) for k in ("type", "item", "quantity", "unit", "amount", "customer",
                                   "due_date", "confidence", "note")}
    if out["type"] not in TYPES:
        out["type"] = parse_type(text)
    if isinstance(out["amount"], str):
        out["amount"] = parse_amount(out["amount"])
    if out["due_date"]:
        try:
            dt.date.fromisoformat(str(out["due_date"]))
        except ValueError:
            out["due_date"] = parse_due(str(out["due_date"]), today)
    try:
        out["confidence"] = max(0.0, min(1.0, float(out["confidence"])))
    except (TypeError, ValueError):
        out["confidence"] = 0.5
    return out


def extract(text, today=None):
    """Return (record, meta). meta = {engine, latency_ms, error}."""
    today = today or dt.date.today()
    start = time.perf_counter()
    rules = rule_extract(text, today)
    meta = {"engine": "rules", "error": None}
    rec = rules
    if os.getenv("NVIDIA_API_KEY"):
        try:
            raw, model = llm_extract(text, today)
            rec = _normalise(raw, text, today)
            meta["engine"] = f"llm:{model}"
            # backfill anything the LLM left empty but the rules found
            for k in ("amount", "customer", "quantity", "unit", "item"):
                if rec.get(k) in (None, "") and rules.get(k) is not None:
                    rec[k] = rules[k]
            # guard against hallucinated money: amount must be traceable to the transcript
            if rec["amount"] is not None and rules["amount"] is not None and rec["amount"] != rules["amount"]:
                rec["note"] = ((rec.get("note") or "") + f" Check amount (rules heard {rules['amount']:,}).").strip()
                rec["confidence"] = min(rec["confidence"], 0.5)
        except Exception as e:  # network, quota, bad JSON -> fall back, never crash the demo
            meta["error"] = f"{type(e).__name__}: {e}"
            meta["engine"] = "rules (LLM fallback)"
    meta["latency_ms"] = round((time.perf_counter() - start) * 1000)
    return rec, meta


MANY_PROMPT = """You get several lines copied from a Nigerian market trader's record book (English, Pidgin or shorthand).
Today is __TODAY__ (__WEEKDAY__). Turn EACH line that records money into one record.
Return ONLY a JSON object: {"entries": [ ... ]} where each entry has the keys
"line" (the line number given, starting at 1), "type", "item", "quantity", "unit", "amount", "customer", "due_date",
"confidence", "note" with the same meaning as below.
""" + SYSTEM_PROMPT.split("Return ONLY a JSON object with these keys:")[1]


def _split_lines(text):
    lines = []
    for raw in (text or "").splitlines():
        line = raw.strip(" -*•\t")
        # keep only lines that carry money (or an unreadable number the trader must fix)
        if line and line.upper() != "NONE" and (parse_amount(line) is not None or "[?]" in line):
            lines.append(line)
    return lines


def extract_many(text, today=None):
    """Several lines (e.g. from a notebook photo) -> (list of records, meta). Each record keeps its source line."""
    today = today or dt.date.today()
    start = time.perf_counter()
    lines = _split_lines(text)
    # a photo line may be "<original> => <English meaning>": rules read both halves (keywords are multilingual,
    # the English half helps most), the trader sees the original
    rules = [dict(rule_extract(l.replace("=>", " ; "), today), line=l) for l in lines]
    meta = {"engine": "rules", "error": None}
    out = rules
    if lines and os.getenv("NVIDIA_API_KEY"):
        try:
            prompt = MANY_PROMPT.replace("__TODAY__", today.isoformat()).replace("__WEEKDAY__", today.strftime("%A"))
            numbered = "\n".join(f"{i}. {l}" for i, l in enumerate(lines, 1))
            content, model = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": numbered}],
                                      max_tokens=300 + 150 * len(lines))
            got = {}
            for e in _parse_json(content).get("entries", []):
                try:
                    got[int(e.get("line"))] = e
                except (TypeError, ValueError):
                    continue
            out = []
            for i, (line, rr) in enumerate(zip(lines, rules), 1):
                if i not in got:  # LLM skipped a line: keep the rules version so nothing is lost
                    out.append(rr)
                    continue
                rec = _normalise(got[i], line, today)
                for k in ("amount", "customer", "quantity", "unit", "item"):
                    if rec.get(k) in (None, "") and rr.get(k) is not None:
                        rec[k] = rr[k]
                if rec["amount"] is not None and rr["amount"] is not None and rec["amount"] != rr["amount"]:
                    rec["note"] = ((rec.get("note") or "") + f" Check amount (line says {rr['amount']:,}).").strip()
                    rec["confidence"] = min(rec["confidence"], 0.5)
                rec["line"] = line
                out.append(rec)
            meta["engine"] = f"llm:{model}"
        except Exception as e:
            meta["error"] = f"{type(e).__name__}: {e}"
            meta["engine"] = "rules (LLM fallback)"
    for rec in out:
        if "[?]" in rec["line"]:
            rec["confidence"] = min(rec["confidence"], 0.3)
            rec["note"] = ((rec.get("note") or "") + " Part of this line was unreadable.").strip()
    meta["latency_ms"] = round((time.perf_counter() - start) * 1000)
    return out, meta


if __name__ == "__main__":
    import sys

    r, m = extract(" ".join(sys.argv[1:]) or "I sell 3 bags of rice give Mama Tunde, 45k, she go pay Friday")
    print(json.dumps({"record": r, "meta": m}, indent=2))
