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

TYPES = ("sale", "credit_sale", "payment_received", "expense", "credit_purchase", "payment_made")
import llm

SYSTEM_PROMPT = """You turn a Nigerian market trader's voice note (English, Nigerian Pidgin, or mixed) into ONE bookkeeping record.
Today is __TODAY__ (__WEEKDAY__).
Return ONLY a JSON object with these keys:
- "type": one of "sale" (customer paid now), "credit_sale" (customer took goods and will pay later / owes), "payment_received" (customer paying back an earlier debt), "expense" (the trader spent money: restock, transport, rent, levy, fuel, etc.), "credit_purchase" (the TRADER took goods or money on credit from a supplier/lender and OWES them: "I owe Alhaji 200k", "Alhaji give me 10 bags, I go pay Friday"), "payment_made" (the TRADER paid back money they owed: "I don pay Alhaji 50k", "I settle my supplier")
- "item": short product or expense name, or null
- "quantity": number or null
- "unit": e.g. "bag", "carton", "crate", "paint", "mudu", or null
- "amount": TOTAL amount in naira as a plain number (45k -> 45000, 1.5m -> 1500000, "twenty thousand" -> 20000), or null if not said
- "customer": the other person's name as said (customer, or the supplier/lender for credit_purchase/payment_made), or null
- "item": for money borrowed (not goods), use "loan"
- "due_date": date the customer promised to pay, as YYYY-MM-DD, or null
- "confidence": number 0-1, how sure you are
- "note": short description of anything unclear, or null
Pidgin hints: "e don pay", "don settle", "come pay" = payment_received. "go pay", "owe", "na credit", "never pay", "balance remain" = credit_sale. "I buy", "I pay for" (the trader spending) = expense.
Yoruba/Hausa/Igbo hints: "mo ta" (yo), "na sayar" (ha), "ere m" (ig) = I SOLD, so it is a sale (or credit_sale if a debt
word appears), never an expense. "mo san" (yo), "na biya" (ha), "akwụrụ m" (ig) = I paid = expense. Debt words:
"gbèsè"/"jẹ mí" (yo), "bashi" (ha), "ụgwọ"/"ji m" (ig) = credit_sale. "ti san" (yo), "ta biya"/"biya bashi" (ha),
"akwụọla" (ig) = payment_received.
Amounts: the number said IS the total ("2 cartons indomie 3500" = 3500). Multiply ONLY when the price is per unit:
"each", "per", "ọ̀kọ̀ọ̀kan" (yo), "kowanne" (ha), "otu ọ bụla" (ig). If the trader corrects themself ("10k, no, 12k"),
use the last amount. Number words: "dubu" (ha), "puku" (ig), "ẹgbẹ̀rún" (yo) = thousand ("dubu biyar" = 5000,
"puku iri abụọ" = 20000, "ẹgbẹ̀rún mẹ́wàá" = 10000); "ẹgbàá" (yo) = 2000. Phone numbers and dates are not amounts.
Not yet paid = still owes = credit_sale: "has not paid", "never pay", "no pay yet", "kò tíì san" (yo),
"bai biya ba"/"ba ta biya ba" (ha), "kwụbeghị" (ig). A customer paying PART of a debt ("paid 20k out of 45k,
remain 25k") = payment_received with the part paid (20000).
Yoruba days: Ajé Mon, Ìṣẹ́gun Tue, Ọjọ́rú Wed, Ọjọ́bọ̀ Thu, Ẹtì Fri, Àbámẹ́ta Sat, Àìkú Sun.
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
              r"chief|brother|sister|bros|mallam|mallama|iyawo|hajiya|hajia|dr\.?|customer")
_NOT_NAMES = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
              "today", "tomorrow", "next", "week", "month", "i", "naira", "the", "me", "am", "am"}
_FILLERS = {"ehn", "abeg", "sha", "um", "so", "okay", "o", "se", "to", "wai", "dai", "ngwa", "kwa", "ni", "fun",
            "don", "go", "no", "na", "ti", "ta", "ya", "has", "paid", "carry", "take", "took"}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# Weekday names in Yoruba / Hausa / Igbo, written WITHOUT tone marks (text is de-accented before matching).
# ⚠️ Have native speakers check these lists.
_LOCAL_WEEKDAYS = [
    ("aje", "litinin", "monde"), ("isegun", "talata", "tiuzdee"), ("ojoru", "laraba", "wenezdee"),
    ("ojobo", "alhamis", "tozdee"), ("eti", "juma'a", "fraidee"), ("abameta", "asabar", "satodee"),
    ("aiku", "lahadi", "sondee"),
]

# English / Pidgin keywords, then Yoruba (yo), Hausa (ha), Igbo (ig) WITHOUT tone marks. ⚠️ native-speaker check.
_PAYMENT_KW = ("don pay", "don bring", "ti pay", "has paid", "have paid", "paid me", "pay me back", "come pay", "don settle",
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
# The TRADER owes / pays back (first person). Checked before the customer-side words. ⚠️ yo/ha native check.
_I_OWE_RE = re.compile(r"\b(?:i|we)\s+(?:(?:still|dey|don|am|are)\s+)*(?:owe|owing)\b|\bon credit from\b"
                       r"|\b(?:give|gave|supply|supplied|lend|lent|borrow(?:ed)?)\s+me\b"
                       r"|\bi (?:borrow|borrowed|collect|collected|take|took)\b.*\b(?:on credit|credit|from)\b"
                       r"|\bi (?:go|will) pay (?:him|her|am|them)\b"
                       r"|\b(?:i|we)\s+(?:has not|have not|haven'?t|did not|didn'?t|never|no|not)\s+(?:yet\s+)?"
                       r"(?:pay|paid)\s+(?:him|her|am|them|my supplier|back|alhaji|oga|madam|mama|hajiya)\b"
                       r"|\bmo je\b|\bina da bashin\b")
_I_PAID_BACK_RE = re.compile(r"\b(?:i|we)\s+(?:don\s+|have\s+|just\s+)?(?:pay|paid|settle|settled|clear|cleared|"
                             r"repay|repaid|return|returned)\s+(?:back\s+)?(?:my\s+)?(?:supplier|alhaji|oga|madam|"
                             r"mama|hajiya|chief|mallam|aunty|uncle|iya|baba|him|her|am|them)\b"
                             r"|\b(?:i|we)\s+(?:don\s+)?(?:pay|paid)\s+back\b|\bmo ti san gbese\b")
_SOLD_RE = re.compile(r"\b(sell|sold|mo ta|sayar|ere m|gave|took|carry)\b")  # stricter: Hausa "ta biya" is not "sold"
# "has not paid" = still owes. Checked BEFORE the "paid me" payment words. (text is folded: no tone marks)
_NEG_PAY_RE = re.compile(r"\b(?:has not|have not|hasn'?t|haven'?t|did not|didn'?t|does not|doesn'?t|never|no|not)\s+"
                         r"(?:yet\s+)?(?:pay|paid)\b|\bko tii? i? ?san\b|\bbai biya\b|\bba (?:ta|ya|su) biya\b"
                         r"|\b(?:a?kwubeghi|kwughi)\b")
_PART_RE = re.compile(r"\b(out of|remain|remaining|balance is|balance na|saura|o ku|foduru|ninu|daga cikin|n'ime)\b")
_PAYVERB_RE = re.compile(r"\b(paid|pay|bring|brought|ti san|biya|akwuola|kwuola)\b")
_EACH_RE = re.compile(r"\b(each|per (?:one|bag|carton|crate|piece|unit)|one one|okookan|kowanne|kowane|otu o bula)\b")
_CORRECT_RE = re.compile(r"\b(?:sorry|no no|i mean|correction|abeg no)\b|,\s*no\s*,")
# Nigerian mobile numbers (0803 456 7812, +2348034567812) are never amounts
_PHONE_RE = re.compile(r"(?:\+?234|\b0)[789][01]\d(?:[\s-]?\d){7}\b")

# Number words -> value. ⚠️ Yoruba/Hausa/Igbo lists need a native-speaker check.
_EN_NUM = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                      "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_EN_NUM.update({w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split())
                if w != "_"})
_EN_SCALE = {"hundred": 100, "thousand": 1000, "million": 1000000}
_HA_NUM = {"daya": 1, "biyu": 2, "uku": 3, "hudu": 4, "biyar": 5, "shida": 6, "bakwai": 7, "takwas": 8, "tara": 9,
           "goma": 10, "ashirin": 20, "talatin": 30, "arba'in": 40, "hamsin": 50, "sittin": 60, "saba'in": 70,
           "tamanin": 80, "casa'in": 90, "dari": 100}
_IG_NUM = {"otu": 1, "abuo": 2, "ato": 3, "ano": 4, "ise": 5, "isii": 6, "asaa": 7, "asato": 8, "itoolu": 9, "iri": 10}
_YO_NUM = {"kan": 1, "meji": 2, "meta": 3, "merin": 4, "marun": 5, "marun-un": 5, "mefa": 6, "meje": 7, "mejo": 8,
           "mesan": 9, "mewaa": 10, "mewa": 10, "ogun": 20, "ogbon": 30, "ogoji": 40, "aadota": 50}


def fold(text):
    """Lowercase and strip tone marks/diacritics: 'Gbèsè' -> 'gbese', 'ụgwọ' -> 'ugwo'."""
    t = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("’", "'")


def _words_amount(text):
    """Money said in words: 'sixty thousand naira', Hausa 'dubu biyar', Igbo 'puku ise', Yoruba 'ẹgbẹ̀rún márùn-ún'."""
    toks = fold(text).replace(",", " ").split()
    for i, w in enumerate(toks):
        if w == "dubu":                                   # ha: dubu (da/sha) <n>
            n, j = 0, i + 1
            while j < len(toks) and (toks[j] in _HA_NUM or toks[j] in ("da", "sha")):
                n += _HA_NUM.get(toks[j], 0)
                j += 1
            return 1000 * (n or 1)
        if w == "puku":                                   # ig: puku iri abuo = 20 x 1000, "na" = plus
            n, j = 0, i + 1
            while j < len(toks) and (toks[j] in _IG_NUM or toks[j] == "na"):
                if toks[j] == "iri" and j + 1 < len(toks) and toks[j + 1] in _IG_NUM and toks[j + 1] != "iri":
                    n += 10 * _IG_NUM[toks[j + 1]]
                    j += 2
                    continue
                n += _IG_NUM.get(toks[j], 0)
                j += 1
            return 1000 * (n or 1)
        if w == "egbaa":                                  # yo: 2000
            return 2000
        if w == "egberun":                                # yo: egberun <n>
            return 1000 * (_YO_NUM.get(toks[i + 1], 1) if i + 1 < len(toks) else 1)
    # English: longest run of number words that has a scale word or is followed by "naira"
    words = fold(text).replace("-", " ").replace(",", " ").split()
    i = 0
    while i < len(words):
        if words[i] not in _EN_NUM and words[i] not in _EN_SCALE:
            i += 1
            continue
        total, cur, scaled, j = 0, 0, False, i
        while j < len(words) and (words[j] in _EN_NUM or words[j] in _EN_SCALE or
                                  (words[j] == "and" and j + 1 < len(words) and words[j + 1] in _EN_NUM)):
            w = words[j]
            if w in _EN_NUM:
                cur += _EN_NUM[w]
            elif w == "hundred":
                cur, scaled = (cur or 1) * 100, True
            elif w in _EN_SCALE:
                total, cur, scaled = total + (cur or 1) * _EN_SCALE[w], 0, True
            j += 1
        value = total + cur
        if value and (scaled or (j < len(words) and words[j] == "naira")):
            return value
        i = j
    return None


def parse_amount(text):
    """Return the most likely naira amount in the text, or None. Ignores phone numbers; after a self-correction
    ('10k, sorry no, 12k') only the corrected part counts; falls back to amounts said in words."""
    text = _PHONE_RE.sub(" ", text or "")
    c = _CORRECT_RE.search(text.lower())
    if c:
        tail = _digits_amount(text[c.end():]) or _words_amount(text[c.end():])
        if tail is not None:
            return tail
    value = _digits_amount(text)
    return value if value is not None else _words_amount(text)


def _amount_values(text):
    """Every money-looking number in the text (for checking the AI's amount really was said)."""
    text = _PHONE_RE.sub(" ", text or "")
    out = set()
    for m in _AMOUNT_RE.finditer(text):
        v = float(m.group("num").replace(",", "")) * _SUFFIX.get((m.group("suf") or "").lower(), 1)
        if v >= 100 or m.group("suf") or m.group("cur"):
            out.add(v)
    w = _words_amount(text)
    if w:
        out.add(float(w))
    return out


def unit_total(text):
    """'5 bags at 15k each' -> 75000. None if no per-unit price is said."""
    t = _PHONE_RE.sub(" ", fold(text))
    each = _EACH_RE.search(t)
    if not each:
        return None
    prices = [(abs(m.start() - each.start()), m) for m in _AMOUNT_RE.finditer(t)
              if m.group("suf") or m.group("cur") or "," in m.group("num") or float(m.group("num")) >= 100]
    if not prices:
        return None
    price_m = min(prices, key=lambda p: p[0])[1]
    price = float(price_m.group("num").replace(",", "")) * _SUFFIX.get((price_m.group("suf") or "").lower(), 1)
    for q in re.finditer(r"(?<![\d.,])(\d{1,3})(?![\d.,])(?!\s*(?:k|thousand|m\b|naira))", t):
        if price_m.start() <= q.start() < price_m.end():
            continue
        total = int(q.group(1)) * price
        return int(total) if total == int(total) else total
    return None


def part_payment_amount(text):
    """'Mama Tunde paid 20k out of the 45k she owes, 25k remain' -> 20000 (the amount right after the pay word)."""
    t = fold(text)
    if not (_PART_RE.search(t) and _PAYVERB_RE.search(t)) or _SOLD_RE.search(t):
        return None
    verb = _PAYVERB_RE.search(t)
    for m in _AMOUNT_RE.finditer(t[verb.end():]):  # the FIRST amount after "paid", not the biggest
        v = float(m.group("num").replace(",", "")) * _SUFFIX.get((m.group("suf") or "").lower(), 1)
        if m.group("suf") or m.group("cur") or v >= 100:
            return int(v) if v == int(v) else v
    return None


def _digits_amount(text):
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
    m = re.search(rf"\b((?i:{_HONORIFIC})\s+[A-Z][^\W\d_]+)", text)
    if m:
        return m.group(1).strip()
    for m in re.finditer(r"\b(?i:give|to|for|from|by|fun|fún|ga|nye)\s+([A-Z][^\W\d_']+(?:\s[A-Z][^\W\d_']+)?)",
                         text):
        name = m.group(1)
        if name.split()[0].lower() not in _NOT_NAMES:
            return name
    m = re.match(r"\s*([A-Z][\w']+)\s+(?i:don pay|has paid|paid|come pay|owe|ti san|ta biya|ya biya|akwụọla|akwuola)",
                 text)
    if m and m.group(1).lower() not in _NOT_NAMES:
        return m.group(1)
    # speech-to-text often writes names in lower case: "fun mama tunde", "hajiya amina akwuola"
    m = re.search(rf"\b({_HONORIFIC})\s+([^\W\d_]+)", text, re.IGNORECASE)
    if m and fold(m.group(2)) not in _NOT_NAMES | _FILLERS and m.group(1).lower() != "customer":
        return f"{m.group(1).title()} {m.group(2).title()}"
    return None


def parse_type(text):
    t = fold(text)
    if _I_OWE_RE.search(t) and not _I_PAID_BACK_RE.search(t):
        return "credit_purchase"
    if _I_PAID_BACK_RE.search(t) and not re.search(r"\bfor (?:transport|rent|levy|motor|fuel)\b", t):
        return "payment_made"
    if _NEG_PAY_RE.search(t):
        return "credit_sale"
    if part_payment_amount(text) is not None:
        return "payment_received"
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
           "amount": unit_total(text) or part_payment_amount(text) or parse_amount(text),
           "customer": parse_customer(text), "due_date": None,
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
    if rec["type"] in ("credit_sale", "credit_purchase"):
        rec["due_date"] = parse_due(text, today)
    t = fold(text)
    if _SOLD_RE.search(t) and _PART_RE.search(t) and re.search(r"\b(paid|pay)\b", t):
        rec["note"] = "Two things in one note? A sale and a part payment. Please check."
        rec["confidence"] = 0.3
    elif rec["amount"] is not None:
        rec["confidence"] = 0.6
    else:
        rec["note"] = "No amount heard"
    return rec


# ---------------------------------------------------------------- LLM

def _parse_json(content):
    """Return the LAST valid JSON object in the reply. Some models think out loud first (and may quote
    JSON while doing so), so the final object is the answer."""
    text = llm.clean(content).replace("```json", "").replace("```", "")
    dec, found, i = json.JSONDecoder(), None, 0
    while i < len(text):
        if text[i] == "{":
            try:
                obj, length = dec.raw_decode(text[i:])
            except ValueError:
                i += 1
                continue
            if isinstance(obj, dict):
                found = obj
            i += length  # skip the whole object so nested {...} inside it are not picked instead
        else:
            i += 1
    if found is None:
        raise ValueError("LLM returned no JSON")
    return found


def _vocab_line(vocab):
    names = ", ".join((vocab or {}).get("names") or [])
    return (f"\nPeople already in this trader's book: {names}. If the note names one of them (even misheard or "
            f"misspelt), use that exact spelling.") if names else ""


def llm_extract(text, today=None, vocab=None):
    """Return (record dict, model used)."""
    today = today or dt.date.today()
    prompt = (SYSTEM_PROMPT.replace("__TODAY__", today.isoformat()).replace("__WEEKDAY__", today.strftime("%A"))
              + _vocab_line(vocab))
    content, model = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": text}],
                              max_tokens=900, timeout=int(os.getenv("LLM_TIMEOUT", "20")))  # then next model
    return _parse_json(content), model


def _sell_guard(rec, rules, text):
    """The AI sometimes misreads Yoruba/Igbo/Hausa keywords. Trust clear words over the AI:
    - 'has paid back' words (akwụọla, ti san, ta biya, don pay...) -> payment_received, not a new credit sale
    - 'I sold' words with nothing saying the trader paid for something -> sale, not expense."""
    t = fold(text)
    if rec.get("type") in ("credit_sale", "sale") and rules["type"] == "payment_received":
        rec["type"] = "payment_received"
        rec["note"] = ((rec.get("note") or "") + " Type corrected to payment: the words say 'has paid'.").strip()
        rec["confidence"] = min(rec.get("confidence") or 0.6, 0.6)
        return rec
    if rec.get("type") == "expense" and _SELL_RE.search(t) and not _EXPENSE_RE.search(t):
        rec["type"] = rules["type"] if rules["type"] in ("sale", "credit_sale") else "sale"
        rec["note"] = ((rec.get("note") or "") + " Type corrected to sale: the words say 'sold'.").strip()
        rec["confidence"] = min(rec.get("confidence") or 0.6, 0.6)
    return rec


def _fix(rec, key, value, why):
    rec[key] = value
    rec["note"] = ((rec.get("note") or "") + f" {why}").strip()
    rec["confidence"] = min(rec.get("confidence") or 0.6, 0.6)


def _check_guard(rec, rules, text, today):
    """Deterministic checks the AI got wrong in our hard test set (docs/RESULTS.md, 25 Sep)."""
    t = fold(text)
    # the words say "I owe" / "I paid back": the AI sometimes files it as a sale or a customer's debt
    flip = {"credit_purchase": ("credit_sale", "sale"), "payment_made": ("payment_received", "expense")}
    if rec.get("type") in flip.get(rules["type"], ()):
        _fix(rec, "type", rules["type"], "Corrected: YOU owe / YOU paid back (the words say 'I').")
    # keep the full name as said ("Oga Emeka", not "Emeka"), or one person becomes two in the book
    ai_name, rule_name = rec.get("customer"), rules.get("customer")
    if ai_name and rule_name and fold(rule_name) != fold(ai_name) and fold(rule_name).endswith(" " + fold(ai_name)):
        rec["customer"] = rule_name
    if (_NEG_PAY_RE.search(t) and rec.get("type") in ("payment_received", "sale")
            and rules["type"] != "credit_purchase"):
        _fix(rec, "type", "credit_sale", "Type corrected to credit: the words say 'not paid yet'.")
    if rec.get("type") == "sale" and part_payment_amount(text) is not None:
        _fix(rec, "type", "payment_received", "Type corrected to payment: part of a debt was paid.")
    # weekday arithmetic: rules are exact, the AI sometimes picks the wrong date
    if rec.get("type") in ("credit_sale", "credit_purchase"):
        due = parse_due(text, today)
        if due and rec.get("due_date") != due:
            rec["due_date"] = due
    # money: the AI's amount must be something actually said (or price x quantity when "each" is said)
    said = _amount_values(text) | ({float(unit_total(text))} if unit_total(text) else set())
    # cases where the rules are more reliable than the AI: "each", a self-correction, amounts said only in words
    digits = _digits_amount(_PHONE_RE.sub(" ", text))
    special = unit_total(text) or (parse_amount(text) if _CORRECT_RE.search(text.lower()) or digits is None else None)
    amt = rec.get("amount")
    if amt is not None and rules["amount"] is not None and float(amt) != float(rules["amount"]):
        if special and float(rules["amount"]) == float(special):
            _fix(rec, "amount", rules["amount"], f"Amount set to {rules['amount']:,} (AI said {amt:,}).")
        elif said and float(amt) not in said:
            _fix(rec, "amount", rules["amount"], f"AI said {amt:,}, which was not said; using {rules['amount']:,}.")
        else:
            rec["note"] = ((rec.get("note") or "") + f" Check amount (rules heard {rules['amount']:,}).").strip()
            rec["confidence"] = min(rec["confidence"], 0.5)
    return rec


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


def extract(text, today=None, vocab=None):
    """Return (record, meta). meta = {engine, latency_ms, error}. vocab: this trader's known names (optional)."""
    today = today or dt.date.today()
    start = time.perf_counter()
    rules = rule_extract(text, today)
    meta = {"engine": "rules", "error": None}
    rec = rules
    if os.getenv("NVIDIA_API_KEY"):
        try:
            raw, model = llm_extract(text, today, vocab)
            rec = _normalise(raw, text, today)
            meta["engine"] = f"llm:{model}"
            # backfill anything the LLM left empty but the rules found
            for k in ("amount", "customer", "quantity", "unit", "item"):
                if rec.get(k) in (None, "") and rules.get(k) is not None:
                    rec[k] = rules[k]
            rec = _sell_guard(rec, rules, text)
            rec = _check_guard(rec, rules, text, today)
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
                rec = _sell_guard(_normalise(got[i], line, today), rr, line.replace("=>", " ; "))
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
