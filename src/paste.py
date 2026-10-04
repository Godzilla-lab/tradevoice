"""A list pasted into the chat ("Chinedu ₦15,000 Aisha ₦45,000 …", one per line or all on one line) -> lines the
trader checks before anything is saved, the same way as a photo of a notebook page (photo.row shape, then
/api/save_rows). Read by code only: no AI, so it works while N-ATLaS sleeps, and code adds the total."""
import re
import statistics

import ledger
from extract import _AMOUNT_RE, _SUFFIX, fold

# words a list's title can have ("# Name Amount owed", "Customers / Balance"): dropped before the first name
HEADER = {"#", "name", "names", "customer", "customers", "amount", "amounts", "owed", "owing", "owe", "owes", "balance",
          "balances", "debt", "debts", "debtors", "list", "of", "my", "the", "paid", "payment", "payments", "sold", "sale",
          "sales", "spent", "expense", "expenses", "total", "naira", "money", "who", "people", "gbese", "bashi", "ugwo",
          "orukọ", "oruko", "suna", "aha", "and", "&", "/", "|", "-", ":"}
KIND_WORDS = [("payment_received", {"paid", "payment", "payments", "san", "biya", "kwuru"}),
              ("sale", {"sold", "sale", "sales", "ta", "sayar", "ere"}),
              ("expense", {"spent", "expense", "expenses", "kashe", "na"}),
              ("credit_sale", {"owed", "owing", "owe", "owes", "debt", "debts", "debtors", "balance", "balances", "gbese",
                               "bashi", "ugwo"})]
# a name never has these: "Mama Tunde took rice 20k and beans 5k" is a record, "add 5000 and 7500" is a sum
NOT_IN_NAME = {"and", "took", "take", "owe", "owes", "paid", "pay", "sold", "sell", "bought", "buy", "spent", "spend",
               "add", "plus", "minus", "times", "for", "on", "credit", "each", "how", "much", "what", "is", "was", "i",
               "me", "you", "she", "he", "we", "they", "bags", "bag", "of", "at", "by", "to", "from", "with", "today"}
BIG = 1_000_000

SAY = {
    "found": {
        "credit_sale": {"English": "I found {n} people who owe you, {m} in all. Check them before I save.",
                        "Pidgin": "I see {n} people wey dey owe you, {m} all together. Check dem before I save.",
                        "Yoruba": "Mo rí ènìyàn {n} tó jẹ ọ́ lówó, {m} lápapọ̀. Ṣàyẹ̀wò wọn kí n tó kọ wọ́n sílẹ̀.",
                        "Hausa": "Na ga mutum {n} da ke da bashinka, {m} gaba ɗaya. Duba su kafin in adana.",
                        "Igbo": "Ahụrụ m mmadụ {n} ji gị ụgwọ, {m} n'ozuzu. Lelee ha tupu m chekwaa."},
        "payment_received": {"English": "I found {n} people who paid you, {m} in all. Check them before I save.",
                             "Pidgin": "I see {n} people wey pay you, {m} all together. Check dem before I save.",
                             "Yoruba": "Mo rí ènìyàn {n} tó san owó fún ọ, {m} lápapọ̀. Ṣàyẹ̀wò wọn kí n tó kọ wọ́n sílẹ̀.",
                             "Hausa": "Na ga mutum {n} da suka biya ka, {m} gaba ɗaya. Duba su kafin in adana.",
                             "Igbo": "Ahụrụ m mmadụ {n} kwụrụ gị ụgwọ, {m} n'ozuzu. Lelee ha tupu m chekwaa."},
        "sale": {"English": "I found {n} sales, {m} in all. Check them before I save.",
                 "Pidgin": "I see {n} sales, {m} all together. Check dem before I save.",
                 "Yoruba": "Mo rí ọjà {n} tí o tà, {m} lápapọ̀. Ṣàyẹ̀wò wọn kí n tó kọ wọ́n sílẹ̀.",
                 "Hausa": "Na ga sayarwa {n}, {m} gaba ɗaya. Duba su kafin in adana.",
                 "Igbo": "Ahụrụ m ahịa {n}, {m} n'ozuzu. Lelee ha tupu m chekwaa."},
        "expense": {"English": "I found {n} things you spent on, {m} in all. Check them before I save.",
                    "Pidgin": "I see {n} things wey you spend money on, {m} all together. Check dem before I save.",
                    "Yoruba": "Mo rí nǹkan {n} tí o náwó lé, {m} lápapọ̀. Ṣàyẹ̀wò wọn kí n tó kọ wọ́n sílẹ̀.",
                    "Hausa": "Na ga abubuwa {n} da ka kashe kuɗi a kai, {m} gaba ɗaya. Duba su kafin in adana.",
                    "Igbo": "Ahụrụ m ihe {n} i mefuru ego na ya, {m} n'ozuzu. Lelee ha tupu m chekwaa."}},
    "look": {"English": "Not ticked, please look:", "Pidgin": "I no tick dis ones, abeg look am:",
             "Yoruba": "Mi ò fi àmì sí ìwọ̀nyí, jọ̀ọ́ wò wọ́n:", "Hausa": "Ban yi wa waɗannan alama ba, don Allah ka duba:",
             "Igbo": "Etinyeghị m akara na ndị a, biko lelee ha:"},
    "twice": {"English": "{who} is on the list twice.", "Pidgin": "{who} dey the list two times.",
              "Yoruba": "{who} wà nínú àkọsílẹ̀ lẹ́ẹ̀mejì.", "Hausa": "{who} yana cikin jerin sau biyu.",
              "Igbo": "{who} dị na ndepụta ahụ ugboro abụọ."},
    "big": {"English": "{who}: {m} is much bigger than the others.", "Pidgin": "{who}: {m} big pass the others well well.",
            "Yoruba": "{who}: {m} tóbi jù àwọn yòókù lọ gan-an.", "Hausa": "{who}: {m} ya fi sauran girma sosai.",
            "Igbo": "{who}: {m} buru ibu karịa ndị ọzọ nke ukwuu."},
    "owes": {"English": "{who} already owes you {b}; ticking adds {m}.",
             "Pidgin": "{who} don already dey owe you {b}; if you tick am, I go add {m}.",
             "Yoruba": "{who} ti jẹ ọ́ ní {b} tẹ́lẹ̀; tí o bá fi àmì sí i, màá fi {m} kún un.",
             "Hausa": "{who} yana da bashinka na {b} tuni; idan ka yi alama, zan ƙara {m}.",
             "Igbo": "{who} ejirila gị {b}; ọ bụrụ na i tinye akara, m ga-agbakwunye {m}."},
}


def _money(x):
    return f"₦{x:,.0f}"


def _amounts(text):
    """Every amount in the text with where it is: [(start, end, value)]. Small bare numbers ("2 bags") are not."""
    out = []
    for m in _AMOUNT_RE.finditer(text):
        v = float(m.group("num").replace(",", "")) * _SUFFIX.get((m.group("suf") or "").lower(), 1)
        if v >= 100 or m.group("suf") or m.group("cur"):
            out.append((m.start(), m.end(), v))
    return out


def _words(chunk):
    chunk = re.sub(r"^\s*\d{1,3}\s*[.)]\s+", " ", chunk)          # "1. Chinedu" / "2) Aisha"
    return [w for w in re.split(r"[\s,;:|•*=\-–]+", chunk.replace("\n", " ")) if w]


def read_list(text):
    """Rows like photo.row(), or None when the text isn't a list of names with amounts."""
    text = text or ""
    spans = _amounts(text)
    if len(spans) < 3:
        return None
    pairs, header, prev = [], [], 0
    for i, (s, e, v) in enumerate(spans):
        words = _words(text[prev:s])
        if i == 0:   # the title before the first name
            while words and fold(words[0]).strip("#") in HEADER | {""}:
                header.append(fold(words.pop(0)).strip("#"))
        if not 1 <= len(words) <= 4 or any(fold(w) in NOT_IN_NAME or not re.match(r"[^\W\d_]", w) for w in words):
            return None
        pairs.append((" ".join(w if w[:1].isupper() else w.title() for w in words), v, text[prev:e].strip()))
        prev = e
    if len(_words(text[prev:])) > 4:   # a sentence after the numbers: not a list
        return None
    kind = next((k for k, ws in KIND_WORDS if ws & set(header)), "credit_sale")
    middle = statistics.median(v for _, v, _ in pairs)
    owing = {fold(d["customer"]): d["balance"] for d in ledger.debtors()} if kind == "credit_sale" else {}
    rows, seen = [], {}
    for name, v, line in pairs:
        why = None
        key = fold(name)
        if key in seen:
            why = ("twice", {"who": name})
        elif v >= BIG and v > 10 * middle:
            why = ("big", {"who": name, "m": _money(v)})
        elif owing.get(key):
            why = ("owes", {"who": name, "b": _money(owing[key]), "m": _money(v)})
        seen[key] = True
        rows.append({"save": why is None, "type": kind, "amount": v, "customer": name, "due_date": "", "item": "",
                     "quantity": None, "unit": "", "line": line, "meaning": "", "checks": [why] if why else []})
    return rows


def summary(rows, lang="English"):
    """'I found 42 people who owe you, ₦2,571,500 in all. Check them before I save.' + the lines not ticked, why."""
    lang = lang if lang in SAY["look"] else "English"
    kind = rows[0]["type"]
    out = SAY["found"][kind][lang].format(n=len(rows), m=_money(sum(r["amount"] for r in rows)))
    whys = [SAY[k][lang].format(**kw) for r in rows for k, kw in r["checks"]]
    if whys:
        out += "\n" + SAY["look"][lang] + "\n" + "\n".join(whys)
    return out


def for_saving(rows):
    """The checks become plain words before the rows leave the server (the line check and WhatsApp show them)."""
    return [dict(r, checks=[SAY[k]["English"].format(**kw) for k, kw in r["checks"]]) for r in rows]
