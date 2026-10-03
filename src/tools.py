"""Tools v1 (E10, ROADMAP Part 11): the jobs N-ATLaS hands to code, because the AI never does maths.

    calculate       plain arithmetic, with number provenance: every number must come from the trader's words or
                    the book, else it is refused. The working is shown ("₦45,000 - 10% = ₦40,500").
    resolve_date    Nigerian dates: Christmas, Sallah (expected dates, the moon decides), Independence Day,
                    "next Friday", month end ... and "pay me after Sallah" in a record (extract.parse_due).
    convert_units   market units the trader teaches ("1 bag of rice is 40 mudu") + the fixed ones (kg, dozen,
                    crate of eggs); "how much is one mudu if a bag is ₦45,000?"
    reconcile_cash  "I counted ₦50,000 in my hand": what the book says should be there, and the difference.
    query_book      a small, checked query over the book: sum / count / average / biggest / smallest, by day,
                    week, month, weekday, customer or item ("which week in September did I sell the most?").

Routing: code first (pick(): word patterns, fast, offline). Questions nothing else understood go to N-ATLaS, which
only CHOOSES a tool and fills its fields as JSON (ai_pick(); vLLM guided JSON, so the tool names are always valid);
code checks the fields and does the work. The answers come from templates. What no tool can do is said honestly and
counted (events "unanswered", no words stored).
Yoruba / Hausa / Igbo wording needs a native-speaker check.
"""
import ast
import datetime as dt
import json
import math
import operator
import re

import clock
import ledger
from extract import fold, parse_amount, parse_due

LANGS = ("English", "Pidgin", "Yoruba", "Hausa", "Igbo")
TOOLS = ("calculate", "resolve_date", "convert_units", "reconcile_cash", "query_book")


def money(x):
    x = float(x)
    return f"₦{x:,.0f}" if abs(x - round(x)) < 0.005 else f"₦{x:,.2f}"


def _g(x):
    return f"{x:,.0f}" if abs(x - round(x)) < 1e-9 else f"{x:,.2f}".rstrip("0").rstrip(".")


def _L(lang):
    return lang if lang in LANGS else "English"


# ------------------------------------------------------------------ numbers in what the trader said

_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(k|m|thousand|million|naira)?"
                  r"(\s*(?:%|percent|per cent))?(?![\w])", re.I)
_MULT = {"k": 1000, "m": 1_000_000, "thousand": 1000, "million": 1_000_000}


def numbers(text):
    """[(value, is_percent, start)] in the order said: '45k' = 45000, '10%' = (10, True)."""
    out = []
    for m in _NUM.finditer(text or ""):
        v = float(m.group(1).replace(",", "")) * _MULT.get((m.group(2) or "").lower(), 1)
        out.append((v, bool(m.group(3)), m.start()))
    if not out:
        w = parse_amount(text or "")   # "fifty thousand"
        if w is not None:
            out.append((float(w), False, 0))
    return out


HALF = {"half": 2, "quarter": 4, "double": 2, "twice": 2, "triple": 3, "idaji": 2, "ida meji": 2, "rabi": 2,
        "rabin": 2, "okara": 2}


# ------------------------------------------------------------------ calculate: a safe evaluator

class Refused(ValueError):
    """A number that came from nowhere, or something that isn't plain arithmetic."""


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_SYM = {ast.Add: "+", ast.Sub: "-", ast.Mult: "×", ast.Div: "÷"}
_PREC = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2}


def _clean(expr):
    e = (expr or "").replace("₦", "").replace("×", "*").replace("÷", "/")
    e = re.sub(r"\bnaira\b", "", e, flags=re.I)
    e = re.sub(r"(?<=\d),(?=\d{3}\b)", "", e)
    e = re.sub(r"(?<=\d)\s*[xX]\s*(?=[\d(])", "*", e)
    e = re.sub(r"(\d+(?:\.\d+)?)\s*[kK]\b", lambda m: str(float(m.group(1)) * 1000), e)
    e = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"pct(\1)", e)
    return e.strip()


def safe_eval(expr, allowed):
    """(value, working) for plain arithmetic: numbers, + - × ÷, n%, brackets. Every number must be in `allowed`."""
    e = _clean(expr)
    if not e or len(e) > 200:
        raise Refused("empty or too long")
    try:
        tree = ast.parse(e, mode="eval")
    except SyntaxError as err:
        raise Refused("not arithmetic") from err
    ok = [float(a) for a in allowed]

    def num(v):
        if not any(abs(v - a) < 1e-6 * max(1, abs(a)) for a in ok):
            raise Refused(f"{_g(v)} was not said and is not in the book")
        return float(v)

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return num(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Div) and b == 0:
                raise Refused("divide by zero")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        if _is_pct(n):
            return num(n.args[0].value) / 100
        raise Refused("not plain arithmetic")

    value = ev(tree)
    if not math.isfinite(value):
        raise Refused("no answer")
    return value, show(tree.body)


def _is_pct(n):
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "pct" and len(n.args) == 1
            and not n.keywords and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, (int, float)))


def show(n, parent=0):
    """The sum as the trader reads it: money with ₦, '45000 - 45000 × 10%' as '₦45,000 - 10%'."""
    if _is_pct(n):
        return f"{_g(n.args[0].value)}%"
    if isinstance(n, ast.Constant):
        v = float(n.value)
        return money(v) if abs(v) >= 100 else _g(v)
    if isinstance(n, ast.UnaryOp):
        return "-" + show(n.operand, 3)
    if isinstance(n, ast.BinOp):
        r = n.right
        if (isinstance(n.op, (ast.Add, ast.Sub)) and isinstance(r, ast.BinOp) and isinstance(r.op, ast.Mult)
                and _is_pct(r.right) and ast.dump(r.left) == ast.dump(n.left)):
            text = f"{show(n.left, 1)} {_SYM[type(n.op)]} {show(r.right)}"    # A - A × 10%  ->  A - 10%
        else:
            p = _PREC[type(n.op)]
            text = f"{show(n.left, p)} {_SYM[type(n.op)]} {show(n.right, p + (0 if isinstance(n.op, (ast.Add, ast.Mult)) else 1))}"
        return f"({text})" if _PREC[type(n.op)] < parent else text
    return "?"


CALC_Q = re.compile(r"\b(how much|wetin|what(?:'s| is)|calculate|calc|total|na how much|what will|how much (?:will|go)"
                    r"|elo ni|elo|nawa|ego ole|ole ka|how e go be|abeg (?:add|calculate)|work out)\b|\?|=\s*$")
OFF = re.compile(r"\b(off|discount|reduce|reduction|remove|comot|less|minus|cut|din|yo|ragi|rage|rangwame|belata|"
                 r"wepu)\b")
MORE = re.compile(r"\b(more|add|increase|plus|on top|interest|vat|charge|kari|gbe e soke|tinye)\b")
TIMES = re.compile(r"\b(times|multiply|multiplied|each|per|every|apiece|a piece|for each|kookan|kowanne|sau|ugboro|"
                   r"otu otu)\b"
                   r"|(?<=\d)\s*[x×*]\s*(?=\d)")
PLUS = re.compile(r"\b(plus|add|and|together|with|sum|join|pelu|da|na)\b|(?<=\d)\s*\+\s*(?=\d)")
MINUS = re.compile(r"\b(minus|less|remove|take away|subtract|comot|from|deduct|yo kuro|cire|wepu)\b|(?<=\d)\s*-\s*(?=\d)")
DIVIDE = re.compile(r"\b(divide|divided|share|split|among|between|per person|each person|pin|raba|kee)\b"
                    r"|(?<=\d)\s*[/÷]\s*(?=\d)")
ARITH_ONLY = re.compile(r"^[\d\s.,+\-*/x×÷()%k₦]+=?\s*\??$", re.I)


def _owed(name, today=None):
    """What a named customer owes now (a book number the calculator may use)."""
    for d in ledger.debtors(today):
        if fold(d["customer"]) == fold(name) or fold(name) in fold(d["customer"]).split():
            return d["customer"], float(d["balance"])
    return None, None


def pick_calculate(text, vocab=None, today=None):
    t = fold(text)
    if ARITH_ONLY.match((text or "").strip()) and re.search(r"\d\s*[-+*/x×÷%]\s*\d|\d\s*%", text or ""):
        return {"tool": "calculate", "expression": text.strip().rstrip("=?").strip()}
    if not CALC_Q.search(t):
        return None
    nums = numbers(text)
    pcts = [v for v, p, _ in nums if p]
    vals = [v for v, p, _ in nums if not p]
    half = next((d for w, d in HALF.items() if re.search(rf"\b{re.escape(fold(w))}\b", t)), None)
    who = None
    if not vals and (pcts or half) and re.search(r"\bowe|\bpay|\bbalance|\bdebt|\bgbese|\bbashi|\bugwo|\bsan\b|\bbiya", t):
        import askbook

        name = askbook.find_name(text, (vocab or ledger.known_words()).get("names"))
        who, owed = _owed(name, today) if name else (None, None)
        if owed:
            vals = [owed]
    if pcts and vals:
        p, base = pcts[0], vals[0]
        if OFF.search(t):
            return {"tool": "calculate", "expression": f"{base:g} - {base:g} * {p:g}%", "who": who, "how": "off"}
        if MORE.search(t):
            return {"tool": "calculate", "expression": f"{base:g} + {base:g} * {p:g}%", "who": who}
        return {"tool": "calculate", "expression": f"{base:g} * {p:g}%", "who": who}
    if half and vals:
        return {"tool": "calculate", "expression": f"{vals[0]:g} / {half}", "who": who, "extra": [half]}
    if len(vals) < 2:
        return None
    a, b = vals[0], vals[1]
    if TIMES.search(t) and not DIVIDE.search(t):
        return {"tool": "calculate", "expression": f"{a:g} * {b:g}"}
    if DIVIDE.search(t):
        big, small = (a, b) if a >= b else (b, a)
        return {"tool": "calculate", "expression": f"{big:g} / {small:g}"}
    if MINUS.search(t) and not re.search(r"\b(plus|add|together)\b", t):
        if re.search(r"\b(remove|take away|subtract|comot|deduct|from)\b", t) and not re.search(r"\bminus\b", t):
            return {"tool": "calculate", "expression": f"{b:g} - {a:g}"}   # "remove 3000 from 45000"
        return {"tool": "calculate", "expression": f"{a:g} - {b:g}"}
    if PLUS.search(t):
        return {"tool": "calculate", "expression": " + ".join(f"{v:g}" for v in vals)}
    return None


def run_calculate(args, text, lang, today=None):
    lang = _L(lang)
    allowed = {v for v, _, _ in numbers(text)} | set(args.get("extra") or [])
    allowed |= {d for w, d in HALF.items() if re.search(rf"\b{re.escape(fold(w))}\b", fold(text))}
    allowed |= {float(x) for x in args.get("book_numbers") or []}
    if args.get("who"):
        _, owed = _owed(args["who"], today)
        if owed:
            allowed.add(owed)
    try:
        value, working = safe_eval(args.get("expression") or "", allowed)
    except Refused as e:
        print(f"calculate refused: {e}")
        return _say("cant_calc", lang)
    value = round(value, 2)
    shown = money(value) if (abs(value) >= 100 or "₦" in working) else _g(value)
    working = f"{working} = {shown}"
    key = "calc_who" if args.get("who") and args.get("how") == "off" else "calc"
    lead = SAY[key][lang].format(r=shown, who=args.get("who") or "")
    lead_en = SAY[key]["English"].format(r=shown, who=args.get("who") or "")
    return _out(f"{lead}\n{working}", lang, spoken=lead, english=f"{lead_en}\n{working}", tool="calculate",
                value=value)


# ------------------------------------------------------------------ resolve_date: the Nigerian calendar

# Islamic holidays move with the moon: these are the EXPECTED dates (Nigerian public holiday estimates), confirmed
# by the moon sighting a day or two before. Add a year as soon as the estimates are out.
MOON = {"eid_fitr": [dt.date(2026, 3, 20), dt.date(2027, 3, 10), dt.date(2028, 2, 27)],
        "eid_kabir": [dt.date(2026, 5, 27), dt.date(2027, 5, 17), dt.date(2028, 5, 5)],
        "maulud": [dt.date(2026, 8, 26), dt.date(2027, 8, 15), dt.date(2028, 8, 3)]}
FIXED = {"new_year": (1, 1), "workers_day": (5, 1), "democracy_day": (6, 12), "independence_day": (10, 1),
         "christmas": (12, 25), "boxing_day": (12, 26)}
HOLIDAY_WORDS = [  # folded; checked in this order ("big sallah" before "sallah")
    ("eid_kabir", r"\b(big|babbar|babban) sallah\b|\beid[- ]?(el|al|ul)?[- ]?(kabir|adha)\b|\bileya\b|\bid el kabir\b"
                  r"|\bram sallah\b|\bsallah ragon\b"),
    ("eid_fitr", r"\b(small|[kƙ]aramar|[kƙ]aramin) sallah\b|\beid[- ]?(el|al|ul)?[- ]?fitr\b|\bitunu aawe\b|\bid el fitr\b"),
    ("maulud", r"\bmaulud\b|\bmawlid\b|\bmaulidi\b"),
    ("sallah", r"\bsallah\b|\bsalla\b|\bodun (ileya|itunu aawe)\b"),
    ("good_friday", r"\bgood friday\b"),
    ("easter_monday", r"\beaster monday\b"),
    ("easter", r"\beaster\b|\bajinde\b|\bista\b"),
    ("christmas", r"\bchristmas\b|\bxmas\b|\bkeresimesi\b|\bkirsimeti\b|\bekeresimesi\b"),
    ("boxing_day", r"\bboxing day\b"),
    ("new_year", r"\bnew year\b|\bodun tuntun\b|\bsabuwar shekara\b|\bafo ohuru\b"),
    ("independence_day", r"\bindependence( day)?\b|\boctober (1|one|first)\b|\b1st october\b|\bominira\b|\b'?yancin kai\b"),
    ("democracy_day", r"\bdemocracy day\b|\bjune 12\b|\b12 june\b"),
    ("workers_day", r"\bworkers'? day\b|\blabou?r day\b|\bmay day\b"),
]
HOLIDAY_NAMES = {
    "eid_kabir": {"English": "Big Sallah (Eid-el-Kabir)", "Pidgin": "Big Sallah (Eid-el-Kabir)",
                  "Yoruba": "Ọdún Iléyá", "Hausa": "Babbar Sallah", "Igbo": "Big Sallah (Eid-el-Kabir)"},
    "eid_fitr": {"English": "Small Sallah (Eid-el-Fitr)", "Pidgin": "Small Sallah (Eid-el-Fitr)",
                 "Yoruba": "Ọdún Ìtúnú Ààwẹ̀", "Hausa": "Ƙaramar Sallah", "Igbo": "Small Sallah (Eid-el-Fitr)"},
    "maulud": {"English": "Eid-el-Maulud", "Pidgin": "Eid-el-Maulud", "Yoruba": "Ọdún Maulud", "Hausa": "Maulidi",
               "Igbo": "Eid-el-Maulud"},
    "good_friday": {"English": "Good Friday", "Pidgin": "Good Friday", "Yoruba": "Good Friday", "Hausa": "Good Friday",
                    "Igbo": "Good Friday"},
    "easter": {"English": "Easter", "Pidgin": "Easter", "Yoruba": "Ọdún Àjíǹde", "Hausa": "Ista", "Igbo": "Ista"},
    "easter_monday": {"English": "Easter Monday", "Pidgin": "Easter Monday", "Yoruba": "Easter Monday",
                      "Hausa": "Easter Monday", "Igbo": "Easter Monday"},
    "christmas": {"English": "Christmas", "Pidgin": "Christmas", "Yoruba": "Kérésìmesì", "Hausa": "Kirsimeti",
                  "Igbo": "Ekeresimesi"},
    "boxing_day": {"English": "Boxing Day", "Pidgin": "Boxing Day", "Yoruba": "Boxing Day", "Hausa": "Boxing Day",
                   "Igbo": "Boxing Day"},
    "new_year": {"English": "New Year's Day", "Pidgin": "New Year", "Yoruba": "Ọdún Tuntun", "Hausa": "Sabuwar Shekara",
                 "Igbo": "Afọ Ọhụrụ"},
    "independence_day": {"English": "Independence Day", "Pidgin": "Independence Day", "Yoruba": "Ọjọ́ Òmìnira",
                         "Hausa": "Ranar 'Yancin Kai", "Igbo": "Ụbọchị Nnwere Onwe"},
    "democracy_day": {"English": "Democracy Day", "Pidgin": "Democracy Day", "Yoruba": "Ọjọ́ Ìjọba Àwa-arawa",
                      "Hausa": "Ranar Dimokuradiyya", "Igbo": "Ụbọchị Ochichi Onye Kwuo Uche Ya"},
    "workers_day": {"English": "Workers' Day", "Pidgin": "Workers' Day", "Yoruba": "Ọjọ́ Òṣìṣẹ́",
                    "Hausa": "Ranar Ma'aikata", "Igbo": "Ụbọchị Ndị Ọrụ"},
}


def easter(year):
    """Western Easter Sunday (the Anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m + 114) // 451
    month, day = (h + m - 7 * n + 114) // 31, (h + m - 7 * n + 114) % 31 + 1
    return dt.date(year, month, day)


def holiday_date(key, today=None):
    """(the next date of this holiday from today, expected?) ; Sallah alone = whichever Eid comes first."""
    today = today or clock.now().date()
    if key == "sallah":
        best = [holiday_date(k, today) for k in ("eid_fitr", "eid_kabir")]
        best = [b for b in best if b[0]]
        return min(best) if best else (None, True)
    if key in MOON:
        nxt = [d for d in MOON[key] if d >= today]
        return (nxt[0] if nxt else None), True
    if key in FIXED:
        m, d = FIXED[key]
        x = dt.date(today.year, m, d)
        return (x if x >= today else dt.date(today.year + 1, m, d)), False
    shift = {"easter": 0, "good_friday": -2, "easter_monday": 1}[key]
    x = easter(today.year) + dt.timedelta(days=shift)
    return (x if x >= today else easter(today.year + 1) + dt.timedelta(days=shift)), False


def holiday_in(text):
    t = fold(text)
    return next((k for k, rx in HOLIDAY_WORDS if re.search(rx, t)), None)


def holiday_due(text, today):
    """For records: 'I go pay after Sallah' -> the day after; 'by Christmas' -> Christmas. ISO date or None."""
    key = holiday_in(text)
    if not key:
        return None
    day, _ = holiday_date(key, today)
    if not day:
        return None
    return (day + dt.timedelta(days=1) if re.search(r"\bafter\b|\bleyin\b|\bbayan\b|\bmgbe .{0,10} gachara\b",
                                                   fold(text)) else day).isoformat()


DATE_Q = re.compile(r"\b(when|wen|what date|which date|which day|what day|how many days|how long (to|till|until|before)"
                    r"|date of|nigba wo|igba wo|ojo wo|ojo melo|ojo meloo|yaushe|wace rana|kwana nawa|olee mgbe|kedu mgbe|"
                    r"ubochi ole|ubochi gini|abobo ubochi)\b")


def pick_date(text, today=None):
    t = fold(text)
    if not DATE_Q.search(t):
        return None
    key = holiday_in(text)
    if key:
        return {"tool": "resolve_date", "holiday": key}
    if re.search(r"\b(month end|end of (the )?month)\b", t) or parse_due(text, today or clock.now().date()):
        return {"tool": "resolve_date", "day": text}
    return None


def _date_words(day, lang):
    import ui_text

    wd = ui_text.t(f"wd_{day.weekday()}", lang) or day.strftime("%A")
    return f"{wd} {day.day} {clock.MONTHS[lang][day.month - 1]}" + (
        f" {day.year}" if day.year != clock.now().year else "")


def run_date(args, text, lang, today=None):
    lang = _L(lang)
    today = today or clock.now().date()
    key = args.get("holiday")
    if key and key not in HOLIDAY_NAMES and key != "sallah":
        key = holiday_in(key)
    if key:
        day, moon = holiday_date(key, today)
        name_key = key
        if key == "sallah" and day:
            name_key = next(k for k in ("eid_fitr", "eid_kabir") if holiday_date(k, today)[0] == day)
        name = HOLIDAY_NAMES[name_key][lang]
        if not day:
            return _say("no_date", lang, name=name)
    else:
        due = parse_due(args.get("day") or text, today)
        if not due and re.search(r"\b(month end|end of (the )?month)\b", fold(args.get("day") or text)):
            nxt = today.replace(day=28) + dt.timedelta(days=4)
            due = (nxt - dt.timedelta(days=nxt.day)).isoformat()
        if not due:
            return None
        day, moon, name = dt.date.fromisoformat(due), False, None
    n = (day - today).days
    if name is None:
        key_say, kw = ("day_is", {"d": _date_words(day, lang), "n": n})
    elif n == 0:
        key_say, kw = ("hol_today", {"name": name})
    elif n == 1:
        key_say, kw = ("hol_tomorrow", {"name": name, "d": _date_words(day, lang)})
    else:
        key_say, kw = ("hol_moon" if moon else "hol_on", {"name": name, "d": _date_words(day, lang), "n": n})
    said = SAY[key_say][lang].format(**kw)
    en_kw = dict(kw, d=_date_words(day, "English"), name=HOLIDAY_NAMES[name_key]["English"] if name else None)
    return _out(said, lang, english=SAY[key_say]["English"].format(**en_kw), tool="resolve_date",
                value=day.isoformat())


# ------------------------------------------------------------------ convert_units: market measures

UNITS = {  # spoken forms -> one name
    "bag": "bag", "bags": "bag", "sack": "bag", "sacks": "bag", "half bag": "half bag", "mudu": "mudu",
    "mudus": "mudu", "derica": "derica", "dericas": "derica", "paint": "paint", "paints": "paint",
    "paint bucket": "paint", "rubber": "paint", "rubbers": "paint", "cup": "cup", "cups": "cup", "olodo": "olodo",
    "tiya": "tiya", "kongo": "kongo", "congo": "kongo", "basket": "basket", "baskets": "basket", "tuber": "tuber",
    "tubers": "tuber", "crate": "crate", "crates": "crate", "carton": "carton", "cartons": "carton",
    "sachet": "sachet", "sachets": "sachet", "pack": "pack", "packs": "pack", "packet": "pack", "packets": "pack",
    "piece": "piece", "pieces": "piece", "egg": "piece", "eggs": "piece", "kg": "kg", "kilo": "kg", "kilos": "kg",
    "kilogram": "kg", "kilograms": "kg", "gram": "g", "grams": "g", "g": "g", "tonne": "tonne", "tonnes": "tonne",
    "ton": "tonne", "tons": "tonne", "litre": "litre", "litres": "litre", "liter": "litre", "liters": "litre",
    "gallon": "gallon", "gallons": "gallon", "keg": "keg", "kegs": "keg", "jerrycan": "keg", "jerrycans": "keg",
    "bottle": "bottle", "bottles": "bottle", "tin": "tin", "tins": "tin", "dozen": "dozen", "dozens": "dozen",
    "bunch": "bunch", "bunches": "bunch", "heap": "heap", "heaps": "heap", "bowl": "bowl", "bowls": "bowl",
    "measure": "measure", "measures": "measure", "roll": "roll", "rolls": "roll", "bundle": "bundle",
    "bundles": "bundle", "yard": "yard", "yards": "yard", "ream": "ream",
}
FIXED_UNITS = {("kg", "g"): 1000, ("tonne", "kg"): 1000, ("dozen", "piece"): 12, ("crate", "piece"): 30,
               ("half bag", "bag"): 0.5}
_U = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
_N = r"(?P<n>\d+(?:\.\d+)?|one|a|an|two|three|four|five|six|ten|half)"
TEACH = re.compile(rf"\b(?:1|one|a|an|every)\s+(?P<a>{_U})(?:\s+of\s+(?P<item>[a-z ]{{2,20}}?))?\s+"
                   rf"(?:is|na|=|get|gets|be|contains|has|dey get|make|makes|equals|carry|carries)\s+"
                   rf"(?P<n>\d+(?:\.\d+)?)\s+(?P<b>{_U})\b")
HOW_MANY = re.compile(rf"\bhow many\s+(?P<b>{_U})\s+(?:(?:are|is|dey|go|fit|can|will)\s+)?(?:\w+\s+)?"
                      rf"(?:in|inside|for|enter|make)\s+{_N}?\s*(?P<a>{_U})(?:\s+of\s+(?P<item>[a-z ]{{2,20}}?))?\b")
PRICE_PER = re.compile(rf"\b(?:if|when)\s+(?:the |a |one |1 )?(?P<a>{_U})(?:\s+of\s+(?P<item>[a-z ]{{2,20}}?))?\s+"
                       rf"(?:is|na|cost|costs|be|sell for|sells for|go for|dey go for)\s+(?P<price>[\d,.]+\s*k?)\b.*?"
                       rf"\bhow much (?:is |be |for |na |go be )?(?P<m>\d+(?:\.\d+)?|one|a|an|two|three|four|five|ten)?\s*"
                       rf"(?P<b>{_U})\b")
PRICE_PER2 = re.compile(rf"\bhow much (?:is |be |for |na |go be )?(?P<m>\d+(?:\.\d+)?|one|a|an|two|three|four|five|ten)?"
                        rf"\s*(?P<b>{_U})(?:\s+of\s+(?P<item2>[a-z ]{{2,20}}?))?\s+(?:if|when)\s+(?:the |a |one |1 )?"
                        rf"(?P<a>{_U})(?:\s+of\s+(?P<item>[a-z ]{{2,20}}?))?\s+(?:is|na|cost|costs|be|sell for|sells for)"
                        rf"\s+(?P<price>[\d,.]+\s*k?)\b")
_WORDN = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "ten": 10, "half": 0.5}


NO_PLURAL = {"mudu", "derica", "kg", "g", "tiya", "kongo", "olodo", "half bag"}


def unit_word(u, n, lang):
    """'3 bags', '120 mudu', '1 cup' (English and Pidgin; the other languages keep the word as said)."""
    if lang not in ("English", "Pidgin") or abs(float(n) - 1) < 1e-9 or u in NO_PLURAL or u.endswith("s"):
        return u
    return {"piece": "pieces", "dozen": "dozen", "bunch": "bunches"}.get(u, u + "s")


def _n(x, default=1.0):
    if not x:
        return default
    return _WORDN.get(x) or float(str(x).replace(",", ""))


def _item(x):
    x = (x or "").strip()
    return x if x and x not in ("it", "am", "them") else None


def _key(item, a, b):
    return f"{fold(item or '*')}|{a}|{b}"


def factor(a, b, item=None):
    """How many b in one a (from what the trader taught, then the fixed ones); None if unknown."""
    if a == b:
        return 1.0
    taught = {}
    for k, v in ledger.recall("unit").items():
        it, x, y = k.split("|")
        taught[(it, x, y)] = float(v)
    for it in ([fold(item)] if item else []) + ["*"]:
        if (it, a, b) in taught:
            return taught[(it, a, b)]
        if (it, b, a) in taught:
            return 1 / taught[(it, b, a)]
    if (a, b) in FIXED_UNITS:
        return FIXED_UNITS[(a, b)]
    if (b, a) in FIXED_UNITS:
        return 1 / FIXED_UNITS[(b, a)]
    for (it, x, y), v in taught.items():          # one step through a shared unit: bag -> paint -> cup
        if it in (fold(item or "*"), "*") and x == a:
            rest = factor(y, b, item) if y != a else None
            if rest:
                return v * rest
    if not item:   # no item said: a conversion taught for exactly one item is the one they mean
        found = {v for (it, x, y), v in taught.items() if (x, y) == (a, b)} | \
                {1 / v for (it, x, y), v in taught.items() if (x, y) == (b, a)}
        if len(found) == 1:
            return found.pop()
    return None


def pick_units(text):
    t = fold(text)
    m = TEACH.search(t)
    if m and not re.search(r"\bhow\b|\?", t):
        return {"tool": "convert_units", "teach": True, "from_unit": UNITS[m["a"]], "to_unit": UNITS[m["b"]],
                "quantity": float(m["n"]), "item": _item(m["item"])}
    m = PRICE_PER.search(t) or PRICE_PER2.search(t)
    if m:
        price = parse_amount(m["price"]) or _n(m["price"].rstrip("k")) * (1000 if m["price"].endswith("k") else 1)
        return {"tool": "convert_units", "from_unit": UNITS[m["a"]], "to_unit": UNITS[m["b"]],
                "quantity": _n(m["m"]), "price": float(price), "item": _item(m["item"])}
    m = HOW_MANY.search(t)
    if m:
        return {"tool": "convert_units", "from_unit": UNITS[m["a"]], "to_unit": UNITS[m["b"]],
                "quantity": _n(m["n"]), "item": _item(m["item"])}
    return None


def run_units(args, text, lang, today=None):
    lang = _L(lang)
    a, b = UNITS.get(args.get("from_unit"), args.get("from_unit")), UNITS.get(args.get("to_unit"), args.get("to_unit"))
    item = _item(args.get("item"))
    if not a or not b:
        return None
    of = f" of {item}" if item else ""
    if args.get("teach"):
        n = float(args["quantity"])
        if n <= 0:
            return None
        ledger.remember("unit", _key(item, a, b), n)
        kw = {"a": a, "of": of, "n": _g(n), "b": unit_word(b, n, lang)}
        return _out(SAY["unit_learned"][lang].format(**kw), lang, english=SAY["unit_learned"]["English"].format(**kw),
                    tool="convert_units")
    f = factor(a, b, item)
    if f is None:
        kw = {"a": a, "of": of, "b": unit_word(b, 2, lang)}
        return _out(SAY["unit_unknown"][lang].format(**kw), lang, english=SAY["unit_unknown"]["English"].format(**kw),
                    tool="convert_units")
    q = float(args.get("quantity") or 1)
    if args.get("price"):           # a bag is ₦45,000 -> one mudu is ₦45,000 ÷ 40
        price = float(args["price"])
        value = round(price / f * q, 2)
        working = (f"{money(price)} ÷ {_g(f)}" + (f" × {_g(q)}" if q != 1 else "") + f" = {money(value)}")
        kw = {"q": _g(q), "b": unit_word(b, q, lang), "of": of, "m": money(value)}
        lead = SAY["unit_price"][lang].format(**kw)
        en = SAY["unit_price"]["English"].format(**dict(kw, b=unit_word(b, q, "English")))
        return _out(f"{lead}\n{working}", lang, spoken=lead, english=en + "\n" + working, tool="convert_units",
                    value=value)
    value = round(q * f, 2)
    kw = {"q": _g(q), "a": unit_word(a, q, lang), "of": of, "n": _g(value), "b": unit_word(b, value, lang)}
    en = dict(kw, a=unit_word(a, q, "English"), b=unit_word(b, value, "English"))
    return _out(SAY["unit_is"][lang].format(**kw), lang, english=SAY["unit_is"]["English"].format(**en),
                tool="convert_units", value=value)


# ------------------------------------------------------------------ reconcile_cash: does my cash match the book?

CASH = re.compile(r"\b(in|for|inside) (my |the )?(hand|drawer|box|bag|pocket|purse|kolo)\b|\bcash (in|for) hand\b"
                  r"|\bmy cash\b|\bcash (wey|that|which) (dey|is|remain)\b|\bmoney (wey|that) (dey|remain) (for |in )?(my )?hand"
                  r"|\blowo mi\b|\bni owo mi\b|\bhannuna\b|\ba hannuna\b|\bn'?aka m\b|\bm n'?aka\b|\bcount(ed)? (my )?(money|cash)\b")
CASH_CUE = re.compile(r"\b(count|counted|check|correct|match|balance|complete|reach|enough|right|missing|short|"
                      r"is it|e (dey )?correct|abi|ka|se|shin|daidai|cika|o zuru|o ziri|o to|o pe)\b|\?")
START = re.compile(r"\b(start|started|begin|began|open|opened|bere|fara|malitere)\b[^\d₦]{0,25}(₦?\s?[\d,.]+\s*k?)")


def pick_cash(text):
    t = fold(text)
    if not (CASH.search(t) and CASH_CUE.search(t)):
        return None
    nums = numbers(text)
    if not nums:
        return None
    s = START.search(text.lower())
    start = parse_amount(s.group(2)) if s else None
    counted = next((v for v, p, pos in nums if not p and not (s and s.start(2) <= pos < s.end(2))), None)
    if counted is None:
        return None
    return {"tool": "reconcile_cash", "counted": float(counted), "started_with": float(start) if start else None}


def run_cash(args, text, lang, today=None):
    lang = _L(lang)
    today = today or clock.now().date()
    d = ledger.day_summary(today)
    if not (d["money_in"] or d["money_out"]):   # credit sales move no cash
        return _say("cash_empty", lang)
    start = float(args.get("started_with") or 0)
    expected = start + d["money_in"] - d["money_out"]
    counted = float(args["counted"])
    diff = round(counted - expected, 2)
    kw = {"exp": money(expected), "mi": money(d["money_in"]), "mo": money(d["money_out"]), "c": money(counted),
          "d": money(abs(diff)), "s": money(start)}
    parts = ["cash_book" if not start else "cash_book_start", "cash_counted",
             "cash_ok" if abs(diff) < 1 else ("cash_missing" if diff < 0 else "cash_extra")]
    said = " ".join(SAY[p][lang].format(**kw) for p in parts)
    working = f"{money(start)} + {money(d['money_in'])} - {money(d['money_out'])} = {money(expected)}" if start else \
        f"{money(d['money_in'])} - {money(d['money_out'])} = {money(expected)}"
    english = " ".join(SAY[p]["English"].format(**kw) for p in parts)
    return _out(f"{said}\n{working}", lang, spoken=said, english=f"{english}\n{working}", tool="reconcile_cash")


# ------------------------------------------------------------------ query_book: a small, checked query language

METRICS = ("sum", "count", "avg", "max", "min")
KINDS = {"sold": ("sale", "credit_sale"), "bought": ("credit_purchase", "expense"), "spent": ("expense", "credit_purchase"),
         "cash_in": ("sale", "payment_received")}
GROUPS = (None, "day", "week", "month", "weekday", "customer", "item")
QB_GROUP = [("week", r"\bweek\b|\bose\b|\bmako\b|\bizu\b"), ("month", r"\bmonth\b|\bosu\b|\bwata\b|\bonwa\b"),
            ("weekday", r"\bday of the week\b|\bweekday\b"), ("day", r"\bday\b|\bdate\b|\bojo\b|\brana\b|\bubochi\b"),
            ("customer", r"\bcustomer\b|\bwho\b|\bperson\b|\bbuyer\b|\btani\b|\bonibaara\b|\bmai siya\b|"
                         r"\bwa ne\b|\bonye\b"),
            ("item", r"\bitem\b|\bgoods\b|\bproduct\b|\bthing\b|\bwetin\b|\bkini\b|\bme\b|\bgini\b")]
QB_TOP = re.compile(r"\b(most|pass|best|highest|biggest|largest|top|ju|julo|ju lo|fi|fi yawa|kacha|karia|mafi)\b")
QB_LOW = re.compile(r"\b(least|lowest|smallest|worst|small pass|kere ju|mafi karanci|kacha nta)\b")
QB_AVG = re.compile(r"\b(average|on average|usually make|normally make|per day|a day|every day|daily|aropin|matsakaici\w*|nkezi)\b")
QB_COUNT = re.compile(r"\bhow many (times|sales|customers|people|entries|records)\b|\bigba melo\b|\bsau nawa\b|"
                      r"\bugboro ole\b")
QB_SINGLE = re.compile(r"\b(biggest|largest|highest|smallest|lowest) (single )?(sale|purchase|expense|spend|transaction|"
                       r"payment)\b")
QB_KIND = [("spent", r"\bspend|\bspent|\bexpense|\bna owo|\bkashe|\bmefuru"),
           ("bought", r"\bbuy\b|\bbought\b|\brestock|\bpurchase|\bra\b|\bsaya\b|\bzuru\b"),
           ("cash_in", r"\b(came|come) in\b|\bcollect|\breceiv"),
           ("sold", r"\bsell|\bsold|\bsale|\bmake money|\bmade|\bta\b|\bsayar|\bciniki|\bere\b|\brere\b")]


def _period(text, today):
    """Month names first ('in September' = that month, this year or the last one), then askbook's periods."""
    import askbook

    t = fold(text)
    for lang_months in (clock.MONTHS["English"], clock.MONTHS["Hausa"], clock.MONTHS["Igbo"], clock.MONTHS["Yoruba"]):
        for i, name in enumerate(lang_months):
            n = re.escape(fold(name))
            if re.search(rf"\b(in|for|of|during|last|this|na|ni|a|n') {n}\b" if fold(name) == "may" else rf"\b{n}\b", t):
                year = today.year if i + 1 <= today.month else today.year - 1
                start = dt.date(year, i + 1, 1)
                end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
                return {"from": start.isoformat(), "to": min(end, today).isoformat(), "name": clock.MONTHS["English"][i]}
    return {"period": askbook.parse_offline(text).get("period") or "all"}


def pick_query(text, today=None):
    t = fold(text)
    today = today or clock.now().date()
    kind = next((k for k, rx in QB_KIND if re.search(rx, t)), None)
    if not kind:
        return None
    spec = {"tool": "query_book", "kind": kind, "metric": "sum", "field": "amount", "group": None, "sort": "desc",
            "limit": 1}
    spec.update(_period(text, today))
    if QB_SINGLE.search(t):
        spec.update(metric="min" if QB_LOW.search(t) else "max")
        return spec
    group = next((g for g, rx in QB_GROUP if re.search(rx, t)), None)
    if group == "customer":
        # "who buy pass" / "which customer…" = the trader's buyers; "who sells cheapest" is about suppliers (not here)
        if re.search(r"\bcheap|\bprice|\bsupplier|\bwholesal", t) or not re.search(
                r"\bcustomer|\bbuyer|\bonibaara|\bmai siya|\bonye ahia|"
                r"\bwho (dey |don |did |has )?(buy|bought|buys|collect|take|took|pay|paid)|"
                r"\btani .{0,15}\bra\b|\bwa ne .{0,15}\bsaya|\bonye .{0,15}\bzuru", t):
            return None
        spec["kind"] = "sold"          # "which customer bought the most" = what the trader sold to them
    if QB_AVG.search(t):
        spec.update(metric="avg", group=group if group in ("day", "week", "month") else "day")
        return spec
    if QB_COUNT.search(t):
        spec.update(metric="count")
        import askbook

        name = askbook.find_name(text, ledger.known_words().get("names"))
        if name:
            spec["customer"] = name
        return spec
    if group and re.search(r"\b(which|what|wetin|wich|who|ewo|wo|tani|wace|wane|wanne|wa|kedu|ole|olee|onye)\b", t) and (QB_TOP.search(t)
                                                                                             or QB_LOW.search(t)):
        if group == "item":
            return None             # "which item sold most": the best-sellers answer already does this
        spec.update(group=group, sort="asc" if QB_LOW.search(t) else "desc")
        return spec
    return None


def _rows(spec, today):
    import askbook

    if spec.get("from"):
        start, end = dt.date.fromisoformat(spec["from"]), dt.date.fromisoformat(spec["to"])
    else:
        start, end = askbook._bounds(spec.get("period") or "all", today)
    types = KINDS[spec["kind"]]
    with ledger.conn() as c:
        rows = [dict(r) for r in c.execute(
            f"SELECT * FROM entries WHERE type IN ({','.join('?' * len(types))}) "
            "AND substr(created_at,1,10) BETWEEN ? AND ?", (*types, start.isoformat(), end.isoformat()))]
    if spec["kind"] == "bought":
        rows = [r for r in rows if r["type"] == "credit_purchase" or ledger.expense_type(r).startswith("Restock")]
    if spec.get("customer"):
        rows = [r for r in rows if r["customer"] and askbook.same_person(spec["customer"], r["customer"])]
    if spec.get("item"):
        rows = [r for r in rows if fold(spec["item"]) in fold(r["item"] or "")]
    return rows, start, end


def _group_key(r, group):
    d = dt.date.fromisoformat(r["created_at"][:10])
    return {"day": d, "week": d - dt.timedelta(days=d.weekday()), "month": d.replace(day=1), "weekday": d.weekday(),
            "customer": r["customer"] or "-", "item": (r["item"] or "-").lower()}[group]


def check_spec(spec):
    """Only the building blocks the code knows; anything else is refused (never raw SQL)."""
    if spec.get("kind") not in KINDS or spec.get("metric") not in METRICS or spec.get("group") not in GROUPS:
        return False
    if spec.get("field", "amount") not in ("amount", "quantity") or spec.get("sort", "desc") not in ("asc", "desc"):
        return False
    lim = spec.get("limit") or 1
    return isinstance(lim, int) and 1 <= lim <= 10


def run_query(spec, text, lang, today=None):
    lang = _L(lang)
    today = today or clock.now().date()
    if not check_spec(spec):
        return None
    rows, start, end = _rows(spec, today)
    if not rows:
        return _say("q_none", lang)
    field = spec.get("field") or "amount"
    what = WHAT[lang][spec["kind"]]
    if spec["metric"] in ("max", "min") and not spec.get("group"):
        r = (max if spec["metric"] == "max" else min)(rows, key=lambda x: x[field] or 0)
        d = dt.date.fromisoformat(r["created_at"][:10])
        kw = {"what": what, "m": money(r["amount"]), "d": _date_words(d, lang),
              "who": f" ({r['customer']})" if r.get("customer") else ""}
        key = "q_biggest" if spec["metric"] == "max" else "q_smallest"
        return _q_out(key, kw, lang, spec)
    if spec["metric"] == "count":
        kw = {"n": len(rows), "what": what, "cw": COUNT_WHAT[lang][spec["kind"]],
              "who": f" ({spec['customer']})" if spec.get("customer") else ""}
        return _q_out("q_count", kw, lang, spec)
    group = spec.get("group")
    if spec["metric"] == "avg":
        group = group or "day"
        sums = {}
        for r in rows:
            sums[_group_key(r, group)] = sums.get(_group_key(r, group), 0) + (r[field] or 0)
        avg = round(sum(sums.values()) / len(sums))
        kw = {"what": what, "m": money(avg), "per": PER[lang][group], "n": len(sums), "g": GROUP_SAY[lang][group]}
        return _q_out("q_avg", kw, lang, spec, working=f"{money(sum(sums.values()))} ÷ {len(sums)} = {money(avg)}")
    if group in ("customer", "item"):
        rows = [r for r in rows if r[group]]      # cash sales with no name don't make a "customer"
        if not rows:
            return _say("q_none", lang)
    sums = {}
    for r in rows:
        k = _group_key(r, group)
        sums[k] = sums.get(k, 0) + (r[field] or 0)
    order = sorted(sums.items(), key=lambda kv: kv[1], reverse=spec.get("sort", "desc") == "desc")
    k, v = order[0]
    kw = {"what": what, "g": GROUP_SAY[lang][group], "label": _label(k, group, lang), "m": money(v),
          "label_en": _label(k, group, "English")}
    key = "q_top" if spec.get("sort", "desc") == "desc" else "q_low"
    return _q_out(key + ("_customer" if group == "customer" else ""), kw, lang, spec)


def _label(k, group, lang):
    import ui_text

    if group == "week":
        return WEEK_OF[lang].format(d=f"{k.day} {clock.MONTHS[lang][k.month - 1]}")
    if group == "month":
        return clock.MONTHS[lang][k.month - 1] + (f" {k.year}" if k.year != clock.now().year else "")
    if group == "day":
        return _date_words(k, lang)
    if group == "weekday":
        return ui_text.t(f"wd_{k}", lang)
    return str(k).title() if group == "item" else str(k)


def _q_out(key, kw, lang, spec, working=None):
    """One template per answer; the average has a sentence per kind in English and Pidgin ("you sell ₦X a day")."""
    def say(lg, args):
        k = f"q_avg_{spec['kind']}" if key == "q_avg" and lg in ("English", "Pidgin") else key
        out = SAY[k][lg].format(**args)
        return out[:1].upper() + out[1:]
    group = spec.get("group") or "day"
    en = dict(kw, what=WHAT["English"][spec["kind"]], cw=COUNT_WHAT["English"][spec["kind"]])
    if "g" in kw:
        en["g"] = GROUP_SAY["English"][group]
    if "per" in kw:
        en["per"] = PER["English"][group]
    if "label" in kw and group in ("week", "month", "day", "weekday"):
        en["label"] = kw.get("label_en", kw["label"])
    said, english = say(lang, kw), say("English", en)
    if working:
        return _out(f"{said}\n{working}", lang, spoken=said, english=f"{english}\n{working}", tool="query_book")
    return _out(said, lang, english=english, tool="query_book")


# ------------------------------------------------------------------ routing

def pick(text, vocab=None, today=None):
    """Code first: which tool (and its fields) the words clearly ask for, or None. Fast and offline."""
    for f in (pick_cash, pick_units):
        got = f(text)
        if got:
            return got
    got = pick_date(text, today)
    if got:
        return got
    got = pick_query(text, today)
    if got:
        return got
    return pick_calculate(text, vocab, today)


RUN = {"calculate": run_calculate, "resolve_date": run_date, "convert_units": run_units,
       "reconcile_cash": run_cash, "query_book": run_query}


def run(choice, text, lang, today=None):
    if not choice or choice.get("tool") not in RUN:
        return None
    out = RUN[choice["tool"]](choice, text, lang, today)
    _event(choice["tool"], out is not None, lang)
    return out


def answer(text, lang="English", today=None, vocab=None):
    """The rules router + the tool, or None (then the rest of the chat brain carries on)."""
    try:
        return run(pick(text, vocab, today), text, lang, today)
    except Exception as e:  # noqa: BLE001 - a tool bug must never break the chat
        print(f"tool failed for {text!r}: {type(e).__name__}: {e}")
        return None


_S, _N0 = {"type": ["string", "null"]}, {"type": ["number", "null"]}
SCHEMA = {   # kept plain (only "tool" is an enum) so every guided-decoding backend accepts it; code checks the rest
    "type": "object",
    "properties": {"tool": {"type": "string", "enum": list(TOOLS) + ["none"]}, "expression": _S, "holiday": _S,
                   "day": _S, "from_unit": _S, "to_unit": _S, "quantity": _N0, "price": _N0, "item": _S,
                   "teach": {"type": ["boolean", "null"]}, "counted": _N0, "started_with": _N0, "kind": _S,
                   "metric": _S, "group": _S, "sort": _S, "period": _S, "customer": _S},
    "required": ["tool"],
}
PICK_PROMPT = """You choose ONE tool for a Nigerian market trader's message (English, Pidgin, Yoruba, Hausa or Igbo)
and fill its fields. Do NOT answer and do NOT do any maths yourself. Reply with JSON only.
Tools:
- calculate: arithmetic. "expression" uses only numbers the trader said or numbers from BOOK below, with + - * /
  and n% (e.g. "45000 - 45000 * 10%", "3 * 45000", "90000 / 4").
- resolve_date: a date question. "holiday" (one of: __HOLIDAYS__) or "day" (the words, e.g. "next Friday").
- convert_units: market measures. from_unit, to_unit, quantity, item; "price" if they give the price of from_unit;
  teach=true when they TELL you a measure ("1 bag of rice is 40 mudu": from_unit bag, to_unit mudu, quantity 40).
- reconcile_cash: they counted their cash. "counted" (the amount), "started_with" (opening cash, if said).
- query_book: a question about their records that needs grouping or an average. kind = sold | bought | spent |
  cash_in; metric = sum | count | avg | max | min; group = day | week | month | weekday | customer | item | null;
  sort = desc (most) | asc (least); period = today | yesterday | this_week | last_week | this_month | last_month |
  this_year | all.
- none: anything else.
BOOK (people who owe the trader, and how much): __BOOK__
Examples:
"If I give Mama Tunde 10% off, how much she go pay?" -> {"tool": "calculate", "expression": "63600 - 63600 * 10%"}
"Ìgbà wo ni Iléyá?" -> {"tool": "resolve_date", "holiday": "eid_kabir"}
"Kudin da ke hannuna 52000, ya yi daidai?" -> {"tool": "reconcile_cash", "counted": 52000}
"Which month I sell pass this year?" -> {"tool": "query_book", "kind": "sold", "metric": "sum", "group": "month",
 "sort": "desc", "period": "this_year"}"""


def ai_pick(text, today=None):
    """N-ATLaS chooses the tool and fills the fields (guided JSON). None if it can't, or says none."""
    import llm

    if not llm.available():
        return None
    book = {d["customer"]: d["balance"] for d in ledger.debtors(today)[:15]}
    prompt = PICK_PROMPT.replace("__HOLIDAYS__", ", ".join(k for k, _ in HOLIDAY_WORDS)).replace(
        "__BOOK__", json.dumps(book))
    try:
        raw, model = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": text}],
                              max_tokens=200, temperature=0.0, timeout=15, schema=SCHEMA)
    except Exception as e:  # noqa: BLE001
        print(f"tool pick failed: {type(e).__name__}: {e}")
        return None
    from extract import _parse_json

    try:
        got = _parse_json(raw)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(got, dict) or got.get("tool") not in TOOLS:
        return None
    got = {k: v for k, v in got.items() if v is not None}
    got["book_numbers"] = list(book.values())
    got["_engine"] = model
    if got["tool"] == "query_book":
        got.setdefault("metric", "sum")
        got.setdefault("field", "amount")
        got.setdefault("sort", "desc")
        got.setdefault("limit", 1)
        got.setdefault("group", None)
        if got.get("period") not in (None, "today", "yesterday", "this_week", "last_week", "this_month", "last_month",
                                     "this_year", "all"):
            got.pop("period")
    return got


def ai_answer(text, lang="English", today=None):
    """For messages nothing else understood: N-ATLaS picks a tool, code runs it. None = nothing fits."""
    try:
        return run(ai_pick(text, today), text, lang, today)
    except Exception as e:  # noqa: BLE001
        print(f"tool (AI) failed for {text!r}: {type(e).__name__}: {e}")
        return None


def unanswered(lang):
    """A question nothing could answer: counted for the team (no words kept), so the top ones become tools."""
    _event("unanswered", True, lang, kind="unanswered")   # ok=True: not an error, a gap to fill


def _event(tool, ok, lang, kind="tool"):
    try:
        import events
        events.log(kind, engine=tool, ok=ok, lang=lang)
    except Exception:  # noqa: BLE001
        pass


def _out(text, lang, spoken=None, english=None, tool=None, value=None):
    out = {"text": text, "spoken": spoken or text, "lang": lang, "english": english if lang != "English" else None,
           "tool": tool}
    if value is not None:
        out["value"] = value      # the number (or date) the code worked out: for the tool tests
    return out


def _say(key, lang, **kw):
    return _out(SAY[key][lang].format(**kw), lang, english=SAY[key]["English"].format(**kw), tool=key)


# ------------------------------------------------------------------ words (5 languages)

WHAT = {"English": {"sold": "sales", "bought": "buying", "spent": "spending", "cash_in": "money in"},
        "Pidgin": {"sold": "sales", "bought": "buying", "spent": "spending", "cash_in": "money wey enter"},
        "Yoruba": {"sold": "ọjà tí o tà", "bought": "ọjà tí o rà", "spent": "owó tí o ná", "cash_in": "owó tó wọlé"},
        "Hausa": {"sold": "ciniki", "bought": "sayayya", "spent": "kashe kuɗi", "cash_in": "kuɗin da suka shigo"},
        "Igbo": {"sold": "ahịa i rere", "bought": "ihe i zụrụ", "spent": "ego i mefuru", "cash_in": "ego batara"}}
GROUP_SAY = {"English": {"day": "day", "week": "week", "month": "month", "weekday": "day of the week",
                         "customer": "customer", "item": "item"},
             "Pidgin": {"day": "day", "week": "week", "month": "month", "weekday": "day for the week",
                        "customer": "customer", "item": "market"},
             "Yoruba": {"day": "ọjọ́", "week": "ọ̀sẹ̀", "month": "oṣù", "weekday": "ọjọ́", "customer": "oníbàárà",
                        "item": "ọjà"},
             "Hausa": {"day": "rana", "week": "mako", "month": "wata", "weekday": "ranar mako", "customer": "mai siya",
                       "item": "kaya"},
             "Igbo": {"day": "ụbọchị", "week": "izu", "month": "ọnwa", "weekday": "ụbọchị", "customer": "onye ahịa",
                      "item": "ngwa ahịa"}}
PER = {"English": {"day": "a day", "week": "a week", "month": "a month"},
       "Pidgin": {"day": "every day", "week": "every week", "month": "every month"},
       "Yoruba": {"day": "lójoojúmọ́", "week": "lọ́sọ̀ọ̀sẹ̀", "month": "lóṣooṣù"},
       "Hausa": {"day": "a kowace rana", "week": "a kowane mako", "month": "a kowane wata"},
       "Igbo": {"day": "kwa ụbọchị", "week": "kwa izu", "month": "kwa ọnwa"}}
COUNT_WHAT = {"English": {"sold": "sales", "bought": "purchases", "spent": "expenses", "cash_in": "payments in"},
              "Pidgin": {"sold": "sales", "bought": "buying", "spent": "spending", "cash_in": "money wey enter"},
              "Yoruba": WHAT["Yoruba"], "Hausa": WHAT["Hausa"], "Igbo": WHAT["Igbo"]}
WEEK_OF = {"English": "the week of {d}", "Pidgin": "the week of {d}", "Yoruba": "ọ̀sẹ̀ {d}",
           "Hausa": "makon {d}", "Igbo": "izu {d}"}
SAY = {
    "calc": {"English": "That comes to {r}.", "Pidgin": "E come be {r}.", "Yoruba": "Ó jẹ́ {r}.",
             "Hausa": "Ya kama {r}.", "Igbo": "Ọ bụ {r}."},
    "calc_who": {"English": "{who} will pay {r}.", "Pidgin": "{who} go pay {r}.", "Yoruba": "{who} yóò san {r}.",
                 "Hausa": "{who} zai biya {r}.", "Igbo": "{who} ga-akwụ {r}."},
    "cant_calc": {"English": "I can't work that out yet. Say the numbers, like: 45,000 minus 10%.",
                  "Pidgin": "I no fit calculate that one yet. Talk the numbers, like: 45,000 minus 10%.",
                  "Yoruba": "Mi ò lè ṣírò ìyẹn báyìí. Ẹ sọ àwọn nọ́ńbà, bíi: 45,000 yọ 10%.",
                  "Hausa": "Ba zan iya lissafa wannan ba yanzu. Faɗi lambobin, kamar: 45,000 a cire 10%.",
                  "Igbo": "Enweghị m ike ịgụkọ nke ahụ ugbu a. Kwuo ọnụọgụ ndị ahụ, dị ka: 45,000 wepụ 10%."},
    "hol_on": {"English": "{name} is on {d}, in {n} days.", "Pidgin": "{name} na {d}, e remain {n} days.",
               "Yoruba": "{name} jẹ́ {d}, ọjọ́ {n} ló kù.", "Hausa": "{name} ranar {d} ne, saura kwana {n}.",
               "Igbo": "{name} bụ {d}, ụbọchị {n} fọdụrụ."},
    "hol_moon": {"English": "{name} is expected on {d}, in about {n} days. The date depends on the moon.",
                 "Pidgin": "{name} fit be {d}, about {n} days remain. Na moon go decide the day.",
                 "Yoruba": "A retí {name} ní {d}, nǹkan bí ọjọ́ {n} ló kù. Òṣùpá ló máa pinnu ọjọ́ náà.",
                 "Hausa": "Ana sa ran {name} ranar {d}, kusan saura kwana {n}. Ganin wata ne zai tabbatar.",
                 "Igbo": "A na-atụ anya {name} na {d}, ihe dị ka ụbọchị {n} fọdụrụ. Ọnwa ga-ekpebi ụbọchị ahụ."},
    "hol_today": {"English": "{name} is today.", "Pidgin": "{name} na today.", "Yoruba": "Òní ni {name}.",
                  "Hausa": "Yau ce {name}.", "Igbo": "Taa bụ {name}."},
    "hol_tomorrow": {"English": "{name} is tomorrow, {d}.", "Pidgin": "{name} na tomorrow, {d}.",
                     "Yoruba": "Ọ̀la ni {name}, {d}.", "Hausa": "Gobe ce {name}, {d}.", "Igbo": "Echi bụ {name}, {d}."},
    "day_is": {"English": "That is {d}, in {n} days.", "Pidgin": "Na {d}, e remain {n} days.",
               "Yoruba": "Ìyẹn ni {d}, ọjọ́ {n} ló kù.", "Hausa": "Wato {d}, saura kwana {n}.",
               "Igbo": "Ọ bụ {d}, ụbọchị {n} fọdụrụ."},
    "no_date": {"English": "I don't have the date for {name} yet.", "Pidgin": "I never get the date for {name} yet.",
                "Yoruba": "Mi ò tíì ní ọjọ́ {name}.", "Hausa": "Ban da ranar {name} tukuna.",
                "Igbo": "Enwebeghị m ụbọchị {name}."},
    "unit_learned": {"English": "Okay, I'll remember: 1 {a}{of} is {n} {b}.",
                     "Pidgin": "Okay, I don hold am: 1 {a}{of} na {n} {b}.",
                     "Yoruba": "Ó dáa, mo ti mọ̀: {a}{of} kan jẹ́ {b} {n}.",
                     "Hausa": "To, na riƙe: {a}{of} ɗaya {b} {n} ne.",
                     "Igbo": "Ọ dị mma, echetala m: otu {a}{of} bụ {b} {n}."},
    "unit_unknown": {"English": "I don't know how many {b} are in 1 {a}{of} yet. Tell me, like: 1 {a} is 40 {b}.",
                     "Pidgin": "I never know how many {b} dey 1 {a}{of}. Tell me, like: 1 {a} na 40 {b}.",
                     "Yoruba": "Mi ò tíì mọ iye {b} tó wà nínú {a}{of} kan. Ẹ sọ fún mi, bíi: 1 {a} is 40 {b}.",
                     "Hausa": "Ban san {b} nawa ne a {a}{of} ɗaya ba tukuna. Faɗa min, kamar: 1 {a} is 40 {b}.",
                     "Igbo": "Amaghị m ole {b} dị n'otu {a}{of}. Gwa m, dị ka: 1 {a} is 40 {b}."},
    "unit_is": {"English": "{q} {a}{of} is {n} {b}.", "Pidgin": "{q} {a}{of} na {n} {b}.",
                "Yoruba": "{a}{of} {q} jẹ́ {b} {n}.", "Hausa": "{a}{of} {q} {b} {n} ne.", "Igbo": "{a}{of} {q} bụ {b} {n}."},
    "unit_price": {"English": "{q} {b}{of} is {m}.", "Pidgin": "{q} {b}{of} na {m}.", "Yoruba": "{b}{of} {q} jẹ́ {m}.",
                   "Hausa": "{b}{of} {q} {m} ne.", "Igbo": "{b}{of} {q} bụ {m}."},
    "cash_empty": {"English": "No money in or out is recorded for today yet, so I can't check your cash.",
                   "Pidgin": "You never record any money wey enter or comot today, so I no fit check your cash.",
                   "Yoruba": "Kò sí ohun tí a kọ sílẹ̀ lónìí, nítorí náà mi ò lè ṣàyẹ̀wò owó rẹ.",
                   "Hausa": "Ba a rubuta komai yau ba, don haka ba zan iya duba kuɗinka ba.",
                   "Igbo": "Ọ dịghị ihe e dere taa, ya mere enweghị m ike ilele ego gị."},
    "cash_book": {"English": "Your book says {exp} should be in your hand today: {mi} came in and {mo} went out.",
                  "Pidgin": "Your book talk say {exp} suppose dey your hand today: {mi} enter, {mo} comot.",
                  "Yoruba": "Ìwé rẹ sọ pé {exp} ló yẹ kó wà lọ́wọ́ rẹ lónìí: {mi} wọlé, {mo} jáde.",
                  "Hausa": "Littafinka ya ce {exp} ya kamata ya kasance a hannunka yau: {mi} ya shigo, {mo} ya fita.",
                  "Igbo": "Akwụkwọ gị kwuru na {exp} kwesịrị ịdị n'aka gị taa: {mi} batara, {mo} pụrụ."},
    "cash_book_start": {"English": "You started with {s}. Your book says {exp} should be in your hand now: "
                                   "{mi} came in and {mo} went out.",
                        "Pidgin": "You start with {s}. Your book talk say {exp} suppose dey your hand now: "
                                  "{mi} enter, {mo} comot.",
                        "Yoruba": "O bẹ̀rẹ̀ pẹ̀lú {s}. Ìwé rẹ sọ pé {exp} ló yẹ kó wà lọ́wọ́ rẹ báyìí: {mi} wọlé, "
                                  "{mo} jáde.",
                        "Hausa": "Ka fara da {s}. Littafinka ya ce {exp} ya kamata ya kasance a hannunka yanzu: "
                                 "{mi} ya shigo, {mo} ya fita.",
                        "Igbo": "I bidoro na {s}. Akwụkwọ gị kwuru na {exp} kwesịrị ịdị n'aka gị ugbu a: {mi} batara, "
                                "{mo} pụrụ."},
    "cash_counted": {"English": "You counted {c}.", "Pidgin": "You count {c}.", "Yoruba": "O ka {c}.",
                     "Hausa": "Ka ƙirga {c}.", "Igbo": "I gụrụ {c}."},
    "cash_ok": {"English": "It matches.", "Pidgin": "E correct.", "Yoruba": "Ó bá a mu.", "Hausa": "Ya yi daidai.",
                "Igbo": "O kwekọrọ."},
    "cash_missing": {"English": "{d} is missing. Maybe a spending wasn't recorded, or some money came by transfer.",
                     "Pidgin": "{d} no dey. Maybe you no record one spending, or some money enter by transfer.",
                     "Yoruba": "{d} kò sí. Bóyá a kò kọ owó kan tí o ná sílẹ̀, tàbí owó kan wọlé nípa transfer.",
                     "Hausa": "{d} ya ɓace. Wataƙila ba a rubuta wani kashe kuɗi ba, ko wasu kuɗi sun shigo ta transfer.",
                     "Igbo": "{d} na-efu. Ma eleghị anya e deghị ego e mefuru, ma ọ bụ ego batara site na transfer."},
    "cash_extra": {"English": "You have {d} more than the book. Maybe a sale wasn't recorded.",
                   "Pidgin": "You get {d} pass wetin the book talk. Maybe you no record one sale.",
                   "Yoruba": "O ní {d} ju ohun tí ìwé sọ lọ. Bóyá a kò kọ ọjà kan tí o tà sílẹ̀.",
                   "Hausa": "Kana da {d} fiye da abin da littafin ya ce. Wataƙila ba a rubuta wani ciniki ba.",
                   "Igbo": "I nwere {d} karịa ihe akwụkwọ kwuru. Ma eleghị anya e deghị otu ahịa."},
    "q_none": {"English": "Your book doesn't have records for that yet.", "Pidgin": "Your book never get record for that.",
               "Yoruba": "Ìwé rẹ kò tíì ní àkọsílẹ̀ fún ìyẹn.", "Hausa": "Littafinka bai da bayanan wannan tukuna.",
               "Igbo": "Akwụkwọ gị enwebeghị ndekọ maka nke ahụ."},
    "q_top": {"English": "Your biggest {g} for {what} was {label}: {m}.",
              "Pidgin": "The {g} wey your {what} pass na {label}: {m}.",
              "Yoruba": "{g} tí {what} pọ̀ jù ni {label}: {m}.", "Hausa": "{g} da {what} ya fi yawa shi ne {label}: {m}.",
              "Igbo": "{g} {what} kachasị bụ {label}: {m}."},
    "q_top_customer": {"English": "Your biggest customer is {label}: {m} in {what}.",
                       "Pidgin": "Your biggest customer na {label}: {m} for {what}.",
                       "Yoruba": "Oníbàárà rẹ tó tóbi jù ni {label}: {m}.",
                       "Hausa": "Babban mai siyanka shi ne {label}: {m}.",
                       "Igbo": "Onye ahịa gị kachasị bụ {label}: {m}."},
    "q_low_customer": {"English": "Your smallest customer is {label}: {m} in {what}.",
                       "Pidgin": "Your smallest customer na {label}: {m} for {what}.",
                       "Yoruba": "Oníbàárà rẹ tó kéré jù ni {label}: {m}.",
                       "Hausa": "Mai siyanka mafi ƙanƙanta shi ne {label}: {m}.",
                       "Igbo": "Onye ahịa gị kacha nta bụ {label}: {m}."},
    "q_low": {"English": "Your smallest {g} for {what} was {label}: {m}.",
              "Pidgin": "The {g} wey your {what} small pass na {label}: {m}.",
              "Yoruba": "{g} tí {what} kéré jù ni {label}: {m}.",
              "Hausa": "{g} da {what} ya fi ƙanƙanta shi ne {label}: {m}.",
              "Igbo": "{g} {what} kacha nta bụ {label}: {m}."},
    "q_avg": {"English": "On average, your {what} is {m} {per} ({n} counted).",
              "Pidgin": "On average, your {what} na {m} {per} ({n} wey I count).",
              "Yoruba": "Ní àròpin, {what} rẹ jẹ́ {m} {per} ({n} ni mo kà).",
              "Hausa": "A matsakaici, {what} naka {m} ne {per} (an ƙirga {n}).",
              "Igbo": "N'nkezi, {what} gị bụ {m} {per} (agụrụ {n})."},
    "q_count": {"English": "You recorded {n} {cw}{who}.", "Pidgin": "You record {n} {cw}{who}.",
                "Yoruba": "O kọ {what} sílẹ̀ ní ìgbà {n}{who}.", "Hausa": "Ka rubuta {what} sau {n}{who}.",
                "Igbo": "I dere {what} ugboro {n}{who}."},
    "q_avg_sold": {"English": "On average, you sell {m} {per} ({n} {g}s counted).",
                   "Pidgin": "On average, you dey sell {m} {per} ({n} {g}s wey I count)."},
    "q_avg_bought": {"English": "On average, you buy goods for {m} {per} ({n} {g}s counted).",
                     "Pidgin": "On average, you dey buy goods of {m} {per} ({n} {g}s wey I count)."},
    "q_avg_spent": {"English": "On average, you spend {m} {per} ({n} {g}s counted).",
                    "Pidgin": "On average, you dey spend {m} {per} ({n} {g}s wey I count)."},
    "q_avg_cash_in": {"English": "On average, {m} comes in {per} ({n} {g}s counted).",
                      "Pidgin": "On average, {m} dey enter {per} ({n} {g}s wey I count)."},
    "q_biggest": {"English": "Your biggest single entry for {what} was {m}{who}, on {d}.",
                  "Pidgin": "The biggest one for your {what} na {m}{who}, on {d}.",
                  "Yoruba": "Èyí tó tóbi jù nínú {what} rẹ ni {m}{who}, ní {d}.",
                  "Hausa": "Mafi girma a {what} naka shi ne {m}{who}, ranar {d}.",
                  "Igbo": "Nke kacha ukwuu na {what} gị bụ {m}{who}, na {d}."},
    "q_smallest": {"English": "Your smallest single entry for {what} was {m}{who}, on {d}.",
                   "Pidgin": "The smallest one for your {what} na {m}{who}, on {d}.",
                   "Yoruba": "Èyí tó kéré jù nínú {what} rẹ ni {m}{who}, ní {d}.",
                   "Hausa": "Mafi ƙanƙanta a {what} naka shi ne {m}{who}, ranar {d}.",
                   "Igbo": "Nke kacha nta na {what} gị bụ {m}{who}, na {d}."},
}
