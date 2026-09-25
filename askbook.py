"""Ask your book in your own language: "Ìrẹsì mélòó ni mo tà lóṣù yìí?" -> exact numbers from the book.

The AI (or offline word lists) only turns the question into a SEARCH {what, item, customer, period, language};
the numbers are added up here in plain Python, and the answer is built from templates, so nothing is invented.
⚠️ Yoruba / Hausa / Igbo words and sentences need a native-speaker check.
"""
import datetime as dt
import json
import os
import re

import ledger
from extract import _parse_json, fold

LANGS = ("English", "Pidgin", "Yoruba", "Hausa", "Igbo")
PERIODS = ("today", "yesterday", "this_week", "last_week", "this_month", "last_month", "this_year", "all")

# item -> words people say for it (English, Pidgin, yo, ha, ig; no tone marks). First local word is used in answers.
ITEM_WORDS = {
    "rice": {"en": ["rice"], "Yoruba": ["iresi"], "Hausa": ["shinkafa"], "Igbo": ["osikapa", "osikapa"]},
    "beans": {"en": ["beans"], "Yoruba": ["ewa"], "Hausa": ["wake"], "Igbo": ["agwa"]},
    "garri": {"en": ["garri", "gari"], "Yoruba": ["gaari", "garri"], "Hausa": ["garri"], "Igbo": ["garri"]},
    "indomie": {"en": ["indomie", "noodles"], "Yoruba": ["indomie"], "Hausa": ["indomie"], "Igbo": ["indomie"]},
    "eggs": {"en": ["egg", "eggs"], "Yoruba": ["eyin"], "Hausa": ["kwai"], "Igbo": ["akwa"]},
    "yam": {"en": ["yam", "yams"], "Yoruba": ["isu"], "Hausa": ["doya"], "Igbo": ["ji"]},
    "palm oil": {"en": ["palm oil", "red oil"], "Yoruba": ["epo pupa"], "Hausa": ["man ja", "manja"],
                 "Igbo": ["mmanu nkwu"]},
    "tomato": {"en": ["tomato", "tomatoes"], "Yoruba": ["tomati"], "Hausa": ["tumatir"], "Igbo": ["tomato"]},
    "pepper": {"en": ["pepper"], "Yoruba": ["ata"], "Hausa": ["barkono"], "Igbo": ["ose"]},
}
LOCAL_ITEM = {"Yoruba": {"rice": "ìrẹsì", "beans": "ẹ̀wà", "eggs": "ẹyin", "yam": "iṣu", "palm oil": "epo pupa",
                         "pepper": "ata"},
              "Hausa": {"rice": "shinkafa", "beans": "wake", "eggs": "kwai", "yam": "doya", "palm oil": "man ja",
                        "pepper": "barkono", "tomato": "tumatir"},
              "Igbo": {"rice": "osikapa", "beans": "agwa", "eggs": "akwa", "yam": "ji", "palm oil": "mmanụ nkwụ",
                       "pepper": "ose"}}

# period words (folded) per period; checked longest-first
PERIOD_WORDS = {
    "yesterday": ["yesterday", "yestade", "lana", "jiya", "unyahu", "nyahu"],
    "today": ["today", "todey", "lonii", "loni", "yau", "taa"],
    "last_week": ["last week", "ose to koja", "ose to kọja", "makon jiya", "satin da ya wuce", "izu gara aga",
                  "izu gara"],
    "this_week": ["this week", "dis week", "lose yii", "lose yi", "ose yii", "ose yi", "ose yi", "wannan mako", "wannan makon", "makon nan",
                  "satin nan", "izu a", "izu nka"],
    "last_month": ["last month", "osu to koja", "watan jiya", "watan da ya wuce", "onwa gara aga", "onwa gara"],
    "this_month": ["this month", "dis month", "losu yii", "losu yi", "osu yii", "osu yi", "wannan wata", "wannan watan", "watan nan",
                   "onwa a", "onwa nka"],
    "this_year": ["this year", "dis year", "lodun yii", "odun yii", "odun yi", "bana", "shekarar nan", "afo a", "afo nka"],
}
# what the trader asks about (folded words). "saya" (ha) = buy but "sayar" = sell: order matters.
WHAT_WORDS = [
    # yo "èrè … mo jẹ" = profit I made (not "mo jẹ" = I owe): checked first
    ("profit", [r"\bere (melo+|elo+)\b", r"\bje ere\b", r"\bjere\b"]),
    ("i_owe", [r"\b(i|we) (still )?(dey )?owe\b", r"\bwho i owe\b", r"\bmo je\b", r"\bina da bashi"]),
    ("owed_to_me", [r"\bowe me\b", r"\bwho owe\b", r"\bdey owe me\b", r"\bje mi\b", r"\bgbese\b", r"\bbashi\b",
                    r"\bugwo\b", r"\bji m\b"]),
    ("profit", [r"\bprofit\b", r"\bgain\b", r"\b(make|made|making)\b", r"\bremain for me\b", r"\bjere\b",
                r"\bere mi\b", r"\briba\b", r"\buru\b"]),
    ("cash_in", [r"\b(came|come|coming) in\b", r"\bcash in\b", r"\bmoney (i )?(collect|collected|receive|received)\b",
                 r"\breceived\b", r"\benter my hand\b", r"\bowo to wole\b", r"\bkudin da (ya )?shigo\b",
                 r"\bego batara\b"]),
    ("sold", [r"\bsell\b", r"\bsold\b", r"\bsales?\b", r"\bta\b", r"\bsayar\b", r"\bere\b", r"\brere\b"]),
    ("bought", [r"\bbuy\b", r"\bbought\b", r"\brestock\b", r"\bra\b", r"\bsaya\b", r"\bsayo\b", r"\bzutara\b",
                r"\bzuru\b", r"\bgotara\b"]),
    ("spent", [r"\bspend\b", r"\bspent\b", r"\bexpense", r"\bna\b(?= owo)", r"\bkashe\b", r"\bmefuru\b"]),
]
LANG_HINTS = {"Yoruba": ["mo", "melo", "elo", "loni", "yii", "ni", "ta", "iresi", "ose", "osu", "gbese"],
              "Hausa": ["nawa", "na", "yau", "wannan", "sayar", "shinkafa", "mako", "wata", "bashi", "nake"],
              "Igbo": ["m", "ole", "taa", "rere", "ere", "ahia", "osikapa", "izu", "onwa", "ugwo", "ka"],
              "Pidgin": ["wetin", "dey", "don", "abeg", "how many i", "wey", "na im", "dis", "sell pass"]}

QUERY_PROMPT = """A Nigerian market trader asks a question about their own record book, in English, Pidgin, Yoruba,
Hausa or Igbo. Do NOT answer it. Turn it into this JSON search and nothing else:
{"kind": "query" or "other", "what": "sold" | "bought" | "spent" | "profit" | "cash_in" | "owed_to_me" | "i_owe",
 "item": one of the book's items below, or null, "customer": one of the book's names below, or null,
 "period": "today" | "yesterday" | "this_week" | "last_week" | "this_month" | "last_month" | "this_year" | "all",
 "language": "English" | "Pidgin" | "Yoruba" | "Hausa" | "Igbo"}
Use "kind": "other" for questions that are not about amounts or counts in the book (e.g. forecasts, advice).
Map local item words to the book's item (ìrẹsì / shinkafa / osikapa = rice; ẹ̀wà / wake / agwa = beans ...).
"what": sold = sales (ta / sayar / ere; also "Did Mama Tunde buy…" = what the trader sold to her); bought = goods the
trader bought (ra / saya / zụrụ); spent = all money spent; profit = "profit / what did I make / èrè / riba / uru";
cash_in = money that actually came in (cash sales + debts paid back).
No period said -> "all".
Items in this trader's book: __ITEMS__
Names in this trader's book: __NAMES__"""


def _bounds(period, today):
    monday = today - dt.timedelta(days=today.weekday())
    first = today.replace(day=1)
    last_month_end = first - dt.timedelta(days=1)
    return {"today": (today, today), "yesterday": (today - dt.timedelta(days=1),) * 2,
            "this_week": (monday, today), "last_week": (monday - dt.timedelta(days=7), monday - dt.timedelta(days=1)),
            "this_month": (first, today), "last_month": (last_month_end.replace(day=1), last_month_end),
            "this_year": (today.replace(month=1, day=1), today),
            "all": (dt.date(2000, 1, 1), today)}.get(period, (dt.date(2000, 1, 1), today))


def guess_language(question):
    t = fold(question)
    words = set(re.findall(r"[a-z']+", t))
    score = {lang: sum(1 for h in hints if (h in words if " " not in h else h in t))
             for lang, hints in LANG_HINTS.items()}
    best = max(score, key=score.get)
    return best if score[best] >= 2 else ("Pidgin" if score["Pidgin"] else "English")


def parse_offline(question, vocab=None):
    t = fold(question)
    hits = [(len(w), p) for p, ws in PERIOD_WORDS.items() for w in ws if re.search(rf"\b{re.escape(w)}\b", t)]
    period = max(hits)[1] if hits else "all"  # longest phrase wins: "watan jiya" (last month) beats "jiya"
    what = next((w for w, pats in WHAT_WORDS if any(re.search(p, t) for p in pats)), None)
    item = None
    for canon, per_lang in ITEM_WORDS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", t) for ws in per_lang.values() for w in ws):
            item = canon
            break
    for it in (vocab or {}).get("items") or []:  # the trader's own item names
        if item is None and it and re.search(rf"\b{re.escape(fold(it))}\b", t):
            item = it
    customer = next((n for n in (vocab or {}).get("names") or [] if fold(n) in t), None)
    if customer and what == "bought" and re.search(rf"{re.escape(fold(customer))}\s+(buy|bought|take|took|collect)", t):
        what = "sold"  # "Did Mama Tunde buy…" = what I sold TO her
    how_many = re.search(r"\bhow (many|much)\b|\bmelo\b|\belo\b|\bnawa\b|\bole\b|\bego ole\b|\bhow e be\b", t)
    if re.search(r"\bpass\b|\bbest\b|\bmost\b|\bnext week\b|\bforecast\b", t):
        return {"kind": "other", "what": what or "sold", "item": item, "customer": customer, "period": period,
                "language": guess_language(question)}  # best sellers / forecast: answered by insights.ask
    asks_sales = what == "sold" and (period != "all" or re.search(r"\bwetin\b|\bwhat\b|\bkini\b|\bme\b", t))
    kind = "query" if (item or customer or what in ("bought", "spent", "i_owe", "owed_to_me", "profit", "cash_in")
                       or how_many
                       or asks_sales) else "other"
    return {"kind": kind, "what": what or "sold", "item": item, "customer": customer, "period": period,
            "language": guess_language(question)}


def parse(question, vocab=None):
    """Question -> search dict. AI when available (better with mixed/other phrasing), else word lists."""
    offline = parse_offline(question, vocab)
    if not os.getenv("NVIDIA_API_KEY"):
        return offline, "rules"
    try:
        import llm

        prompt = (QUERY_PROMPT.replace("__ITEMS__", ", ".join((vocab or {}).get("items") or []) or "none")
                  .replace("__NAMES__", ", ".join((vocab or {}).get("names") or []) or "none"))
        out, model = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": question}],
                              max_tokens=300, timeout=int(os.getenv("LLM_TIMEOUT", "20")))
        q = _parse_json(out)
        q = {"kind": q.get("kind") if q.get("kind") in ("query", "other") else offline["kind"],
             "what": q.get("what") if q.get("what") in dict(WHAT_WORDS) else offline["what"],
             "item": q.get("item") or offline["item"], "customer": q.get("customer") or offline["customer"],
             "period": q.get("period") if q.get("period") in PERIODS else offline["period"],
             "language": q.get("language") if q.get("language") in LANGS else offline["language"]}
        return q, f"llm:{model}"
    except Exception:  # noqa: BLE001 - the word lists still work
        return offline, "rules (AI unavailable)"


def run(q, today=None):
    """Add up the book for a search. Returns numbers only."""
    today = today or dt.date.today()
    if q["what"] in ("owed_to_me", "i_owe"):
        people = ledger.debtors(today) if q["what"] == "owed_to_me" else ledger.creditors(today)
        if q.get("customer"):
            people = [p for p in people if ledger.customer_key(p["customer"]) == ledger.customer_key(q["customer"])]
        return {"people": [(p["customer"], p["balance"]) for p in people],
                "money": sum(p["balance"] for p in people)}
    if q["what"] in ("profit", "cash_in"):
        start, end = _bounds(q["period"], today)
        s = ledger.period_summary(start, end)
        if q["what"] == "profit":
            return {"money": s["profit"], "sales": s["sales"], "spent": s["expenses"], "entries": s["entries"],
                    "start": start, "end": end}
        return {"money": s["cash_sales"] + s["payments_received"], "cash": s["cash_sales"],
                "debts": s["payments_received"], "entries": s["entries"], "start": start, "end": end}
    types = {"sold": ("sale", "credit_sale"), "bought": ("credit_purchase", "expense"),
             "spent": ("expense", "credit_purchase")}[q["what"]]
    start, end = _bounds(q["period"], today)
    with ledger.conn() as c:
        rows = [dict(r) for r in c.execute(
            f"SELECT * FROM entries WHERE type IN ({','.join('?' * len(types))}) "
            "AND substr(created_at,1,10) BETWEEN ? AND ?", (*types, start.isoformat(), end.isoformat()))]
    if q["what"] == "bought":  # goods only: skip transport, rent, levies...
        rows = [r for r in rows if r["type"] == "credit_purchase" or ledger.expense_type(r).startswith("Restock")]
    if q.get("item"):
        words = [fold(q["item"])] + [w for ws in ITEM_WORDS.get(q["item"], {}).values() for w in ws]
        rows = [r for r in rows if any(w in fold(f"{r['item'] or ''} {r['raw_text'] or ''}") for w in words)]
    if q.get("customer"):
        rows = [r for r in rows if ledger.customer_key(r["customer"]) == ledger.customer_key(q["customer"])]
    units = {}
    for r in rows:
        if r["quantity"]:
            u = (r["unit"] or "").rstrip("s") or "piece"
            units[u] = units.get(u, 0) + r["quantity"]
    return {"money": sum(r["amount"] for r in rows), "entries": len(rows), "units": units,
            "no_qty": sum(1 for r in rows if not r["quantity"]), "start": start, "end": end}


PERIOD_SAY = {
    "English": {"today": "Today", "yesterday": "Yesterday", "this_week": "This week", "last_week": "Last week",
                "this_month": "This month", "last_month": "Last month", "this_year": "This year", "all": "So far"},
    "Pidgin": {"today": "Today", "yesterday": "Yesterday", "this_week": "This week", "last_week": "Last week",
               "this_month": "This month", "last_month": "Last month", "this_year": "This year",
               "all": "Since you start"},
    "Yoruba": {"today": "Lónìí", "yesterday": "Lánàá", "this_week": "Ní ọ̀sẹ̀ yìí", "last_week": "Ní ọ̀sẹ̀ tó kọjá",
               "this_month": "Ní oṣù yìí", "last_month": "Ní oṣù tó kọjá", "this_year": "Ní ọdún yìí",
               "all": "Títí di ìsinsìnyí"},
    "Hausa": {"today": "Yau", "yesterday": "Jiya", "this_week": "A wannan makon", "last_week": "A makon jiya",
              "this_month": "A wannan watan", "last_month": "A watan jiya", "this_year": "A bana",
              "all": "Zuwa yanzu"},
    "Igbo": {"today": "Taa", "yesterday": "Ụnyaahụ", "this_week": "N'izu a", "last_week": "N'izu gara aga",
             "this_month": "N'ọnwa a", "last_month": "N'ọnwa gara aga", "this_year": "N'afọ a", "all": "Ruo ugbu a"},
}
VERB = {  # {p} period, {what} item/quantity, {m} money, {n} entries
    "sold": {"English": "{p}, you sold {what} for {m} ({n}).", "Pidgin": "{p}, you don sell {what} for {m} ({n}).",
             "Yoruba": "{p}, o ta {what} ní {m}.", "Hausa": "{p}, an sayar da {what} na {m}.",
             "Igbo": "{p}, i rere {what} na {m}."},
    "bought": {"English": "{p}, you bought {what} for {m}.", "Pidgin": "{p}, you don buy {what} for {m}.",
               "Yoruba": "{p}, o ra {what} ní {m}.", "Hausa": "{p}, an saya {what} na {m}.",
               "Igbo": "{p}, i zụrụ {what} na {m}."},
    "spent": {"English": "{p}, you spent {m}{on}.", "Pidgin": "{p}, you don spend {m}{on}.",
              "Yoruba": "{p}, o ná {m}{on}.", "Hausa": "{p}, an kashe {m}{on}.", "Igbo": "{p}, i mefuru {m}{on}."},
}
NOTHING = {"English": "I don't see any record of that {p}.", "Pidgin": "I no see any record for that one {p}.",
           "Yoruba": "Kò sí àkọsílẹ̀ kankan fún ìyẹn {p}.", "Hausa": "Babu wani rikodi na hakan {p}.",
           "Igbo": "Ahụghị m ihe edere maka nke ahụ {p}."}
OWED = {"owed_to_me": {"English": "{who} owes you {m}.", "Pidgin": "{who} dey owe you {m}.",
                       "Yoruba": "{who} jẹ ọ́ ní {m}.", "Hausa": "{who}: bashin {m}.", "Igbo": "{who} ji gị {m}."},
        "i_owe": {"English": "You owe {who} {m}.", "Pidgin": "You dey owe {who} {m}.",
                  "Yoruba": "O jẹ {who} ní {m}.", "Hausa": "Bashin {who}: {m}.", "Igbo": "I ji {who} {m}."},
        "none": {"English": "Nobody.", "Pidgin": "Nobody.", "Yoruba": "Kò sí ẹnikẹ́ni.", "Hausa": "Babu kowa.",
                 "Igbo": "Onweghị onye."}}


PROFIT = {"English": "{p}, you sold {s} and spent {x}. Sales minus spending: {m}.",
          "Pidgin": "{p}, you sell {s}, you spend {x}. Wetin remain na {m}.",
          "Yoruba": "{p}, o ta ọjà ní {s}, o ná {x}. Èrè jẹ́ {m}.",
          "Hausa": "{p}, an sayar na {s}, an kashe {x}. Riba: {m}.",
          "Igbo": "{p}, i rere {s}, i mefuru {x}. Uru bụ {m}."}
CASH_IN = {"English": "{p}, money that came in: {m} ({c} cash sales + {d} debts paid back).",
           "Pidgin": "{p}, money wey enter your hand na {m} ({c} cash sales, {d} from people wey pay their debt).",
           "Yoruba": "{p}, owó tó wọlé jẹ́ {m} ({c} owó ọjà, {d} gbèsè tí wọ́n san).",
           "Hausa": "{p}, kuɗin da ya shigo {m} ({c} na sayarwa, {d} na bashin da aka biya).",
           "Igbo": "{p}, ego batara bụ {m} ({c} site n'ahịa, {d} ụgwọ a kwụrụ)."}


def answer(q, res, spoken=False):
    """Build the reply from the numbers. spoken=True writes amounts in words for the voice reply."""
    from tts import naira_words, number_words

    lang = q["language"] if q["language"] in LANGS else "English"
    money = ((lambda x: ("minus " if x < 0 else "") + naira_words(abs(x))) if spoken
             else (lambda x: f"-₦{abs(x):,.0f}" if x < 0 else f"₦{x:,.0f}"))
    count = (lambda x: number_words(x)) if spoken else (lambda x: f"{x:g}")
    if q["what"] in ("owed_to_me", "i_owe"):
        if not res["people"]:
            return OWED["none"][lang]
        return " ".join(OWED[q["what"]][lang].format(who=w, m=money(b)) for w, b in res["people"][:5])
    p = PERIOD_SAY[lang][q["period"]]
    if not res["entries"]:
        return NOTHING[lang].format(p=p.lower() if lang in ("English", "Pidgin") else f"({p})")
    if q["what"] == "profit":
        return PROFIT[lang].format(p=p, s=money(res["sales"]), x=money(res["spent"]), m=money(res["money"]))
    if q["what"] == "cash_in":
        return CASH_IN[lang].format(p=p, m=money(res["money"]), c=money(res["cash"]), d=money(res["debts"]))
    item = q.get("item")
    name = LOCAL_ITEM.get(lang, {}).get(item, item) if item else None
    qty = ", ".join(f"{count(v)} {u}{'s' if v != 1 and lang in ('English', 'Pidgin') else ''}"
                    for u, v in res["units"].items())
    if lang in ("English", "Pidgin"):
        what = (f"{qty} of {name}" if qty and name else qty or name or "goods")
    else:
        what = (f"{name} ({qty})" if qty and name else name or qty or {"Yoruba": "ọjà", "Hausa": "kaya",
                                                                          "Igbo": "ngwá ahịa"}[lang])
    on = f" on {name}" if name and lang in ("English", "Pidgin") else (f" ({name})" if name else "")
    n = f"{res['entries']} sale" + ("s" if res["entries"] != 1 else "")
    text = VERB[q["what"]][lang].format(p=p, what=what, m=money(res["money"]), n=n, on=on)
    if q.get("customer") and lang in ("English", "Pidgin"):
        text = text.rstrip(".") + f", to {q['customer']}."
    return text


def ask_book(question, today=None, language=None):
    """Return (answer text, spoken text, language, search, engine) or None if it's not a book-number question.
    language: answer in this language (e.g. the one the trader picked for voice); default = the question's."""
    vocab = ledger.known_words()
    q, engine = parse(question, vocab)
    if q["kind"] != "query":
        return None
    if language in LANGS:
        q["language"] = language
    res = run(q, today)
    return answer(q, res), answer(q, res, spoken=True), q["language"], q, engine


if __name__ == "__main__":
    import sys

    print(json.dumps(ask_book(" ".join(sys.argv[1:]) or "How many bags of rice did I sell this week?"),
                     default=str, ensure_ascii=False, indent=1))
