"""Generate a HARD test set: ~180 trader phrases in 5 languages with the traps that break bookkeeping AI.

python eval/make_hard_cases.py            # writes eval/cases_hard.jsonl (same output every time: fixed seed)
python eval/make_hard_cases.py --seed 7 --out eval/cases_fresh.jsonl   # a FRESH draw to check fixes didn't just
                                          # memorise cases_hard (same templates, new names/amounts/combinations)
python eval/run_eval.py --cases eval/cases_hard.jsonl --sleep 1.5

Each case has: id, lang, category, text, type, amount, customer (+ due_weekday when a weekday is said,
+ flag=true when the right behaviour is to ASK the trader, not to guess).

Categories (the traps):
  basic          one clean phrase per entry type
  amount_format  45k, ₦45,000, N45,000, "45 thousand", "45,000 naira", 1.2m
  words          amount said in English words ("forty-five thousand naira"), as speech-to-text writes it
  local_numbers  amount said in Yoruba / Hausa / Igbo number words (Hausa "dubu biyar" = 5,000)
  unit_price     "3 bags at 15k each" -> the TOTAL is 45,000
  negation       "she has not paid me" is a debt, not a payment (the words "paid me" are a trap)
  part_payment   "paid 20k out of the 45k, 25k remains" -> payment of 20,000
  no_amount      no money said -> amount must be empty, not invented
  distractor     other numbers in the sentence: phone numbers, dates ("the 15th")
  self_correct   "10k... no, 12k" -> 12,000
  code_switch    local language mixed with English / Pidgin
  asr_noise      as speech-to-text writes it: no tone marks, no punctuation, lower case, filler words
  flag           genuinely unclear (two entries in one note, "4 5") -> the AI should ask (low confidence / note)

⚠️ Yoruba, Hausa and Igbo sentences were written by a non-native speaker from templates. Every case in those
languages has "check": "native" until a native speaker confirms it: then delete that key.
"""
import json
import os
import random
import re
import sys
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tts import naira_words  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "cases_hard.jsonl")
rng = random.Random(27092026)

NAMES = [("Mama Tunde", "f"), ("Iya Bisi", "f"), ("Alhaji Musa", "m"), ("Oga Emeka", "m"), ("Aunty Kemi", "f"),
         ("Mallam Sani", "m"), ("Madam Ngozi", "f"), ("Baba Sola", "m"), ("Hajiya Amina", "f"), ("Uncle Chidi", "m")]
DAYS = {"english": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "yoruba": ["Ajé", "Ìṣẹ́gun", "Ọjọ́rú", "Ọjọ́bọ̀", "Ẹtì", "Àbámẹ́ta", "Àìkú"],
        "hausa": ["Litinin", "Talata", "Laraba", "Alhamis", "Juma'a", "Asabar", "Lahadi"],
        "igbo": ["Mọnde", "Tiuzdee", "Wenezdee", "Tọzdee", "Fraịdee", "Satọdee", "Sọndee"]}
DAYS["pidgin"] = DAYS["english"]
ITEMS = {"english": ["bags of rice", "cartons of indomie", "crates of eggs", "paints of beans", "bags of garri"],
         "pidgin": ["bag rice", "carton indomie", "crate egg", "paint beans", "bag garri"],
         "yoruba": ["àpò ìrẹsì", "káàtọ̀nù indomie", "àpò ẹ̀wà", "àpò gaàrí"],
         "hausa": ["buhun shinkafa", "katan indomie", "buhun wake", "buhun garri"],
         "igbo": ["akpa osikapa", "katọn indomie", "akpa agwa", "akpa garri"]}
# Local number words (⚠️ native check). Hausa/Igbo are regular (dubu/puku = thousand); Yoruba uses modern counting.
LOCAL_NUMBERS = {
    "yoruba": {2000: "ẹgbàá", 5000: "ẹgbẹ̀rún márùn-ún", 10000: "ẹgbẹ̀rún mẹ́wàá", 20000: "ẹgbẹ̀rún ogún"},
    "hausa": {2000: "dubu biyu", 5000: "dubu biyar", 10000: "dubu goma", 20000: "dubu ashirin", 50000: "dubu hamsin"},
    "igbo": {2000: "puku abụọ", 5000: "puku ise", 10000: "puku iri", 20000: "puku iri abụọ", 50000: "puku iri ise"},
}
FILLERS = {"english": ["um", "so", "okay"], "pidgin": ["ehn", "abeg", "sha"], "yoruba": ["ẹ̀n", "ṣé", "o"],
           "hausa": ["to", "wai", "dai"], "igbo": ["ehn", "ngwa", "kwa"]}
AMOUNTS = [2500, 3500, 7500, 12000, 18500, 20000, 27000, 45000, 60000, 150000]
FORMATS = ["plain", "comma", "k", "N", "naira_sign", "naira_word", "thousand"]


def fmt(v, style):
    k = f"{v / 1000:g}"
    return {"plain": str(v), "comma": f"{v:,}", "k": f"{k}k", "N": f"N{v:,}", "naira_sign": f"₦{v:,}",
            "naira_word": f"{v:,} naira", "thousand": f"{k} thousand", "m": f"{v / 1e6:g}m"}[style]


def noisy(text, lang):
    """What speech-to-text output tends to look like: no tone marks or punctuation, lower case, fillers."""
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"(?<=\d),(?=\d)", "", t)          # 45,000 -> 45000
    t = t.replace(",", " , ")                      # remember clause breaks: a filler goes there, not inside a name
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)       # drop full stops, keep 7.5k
    t = re.sub(r"[^\w\s'₦.,-]", " ", t)
    words = t.split()
    words.insert(words.index(",") if "," in words else len(words), rng.choice(FILLERS[lang]))
    return rng.choice(FILLERS[lang]) + " " + " ".join(w for w in words if w != ",")


# Templates per language: category -> list of (type, text, amount_rule). Slots:
# {n} name, {he}/{him}/{his} pronouns (en/pcm), {hp} Hausa ya/ta, {q} quantity, {i} item, {a} amount, {d} day,
# {u} unit price, {part}/{total}/{rem} part payment, {w} amount in words, {old} wrong amount before correction.
# amount_rule: "a" (the amount), "qu" (q*u), "part", None (no amount), "w", "local"
T = {
    "english": {
        "basic": [("credit_sale", "Sold {q} {i} to {n} for {a}, {he} will pay on {d}", "a"),
                  ("sale", "Sold {q} {i} for {a} cash", "a"),
                  ("payment_received", "{n} paid back {a} that {he} owed me", "a"),
                  ("expense", "Paid {a} for transport to the market today", "a")],
        "words": [("credit_sale", "sold {q} {i} to {n} {w} {he} will pay on {d}", "w"),
                  ("expense", "i paid {w} for market levy", "w")],
        "unit_price": [("credit_sale", "Sold {q} {i} to {n} at {u} each, {he} will pay on {d}", "qu"),
                       ("sale", "Sold {q} {i}, {u} each, customer paid cash", "qu")],
        "negation": [("credit_sale", "Gave {n} {q} {i} worth {a}, {he} has not paid me yet", "a"),
                     ("credit_sale", "{n} took {q} {i} for {a} but {he} didn't pay me", "a")],
        "part_payment": [("payment_received", "{n} paid {part} out of the {total} {he} owes, {rem} remaining", "part"),
                         ("payment_received", "{n} brought {part} today, balance is {rem}", "part")],
        "no_amount": [("credit_sale", "{n} took {q} {i}, {he} will pay on {d}", None),
                      ("payment_received", "{n} has paid everything {he} owed me", None)],
        "distractor": [("payment_received", "{n} paid back {a}, {his} number is 08034567812", "a"),
                       ("credit_sale", "Sold {q} {i} to {n} for {a}, {he} will pay on the 15th", "a")],
        "self_correct": [("sale", "Sold {q} {i} for {old}, sorry no, {a}", "a")],
        "flag": [("credit_sale", "Sold {q} {i} to {n} for 90k, {he} paid 50k, remaining 40k", "flag"),
                 ("sale", "Sold {q} {i} for four five", "flag")],
    },
    "pidgin": {
        "basic": [("credit_sale", "I sell {q} {i} give {n} {a}, {he} go pay {d}", "a"),
                  ("sale", "I sell {q} {i} {a}, dem pay cash", "a"),
                  ("payment_received", "{n} don pay {a} wey {he} owe me", "a"),
                  ("expense", "I pay {a} for motor go market", "a")],
        "words": [("credit_sale", "i sell {q} {i} give {n} {w} {he} go pay {d}", "w"),
                  ("payment_received", "{n} don bring {w} for the money wey {he} owe", "w")],
        "unit_price": [("credit_sale", "I sell {q} {i} give {n}, {u} each, {he} go pay {d}", "qu"),
                       ("sale", "{q} {i} comot today, {u} each, dem pay cash", "qu")],
        "negation": [("credit_sale", "{n} carry {q} {i} {a}, {he} never pay me", "a"),
                     ("credit_sale", "{n} take {q} {i} {a}, {he} no pay yet", "a")],
        "part_payment": [("payment_received", "{n} pay {part} out of the {total} wey {he} owe, remain {rem}", "part"),
                         ("payment_received", "{n} bring {part} today, e remain {rem}", "part")],
        "no_amount": [("credit_sale", "{n} carry {q} {i}, {he} go pay {d}", None),
                      ("payment_received", "{n} don pay all the money wey {he} owe", None)],
        "distractor": [("payment_received", "{n} don pay {a}, {his} number na 08034567812", "a"),
                       ("credit_sale", "{n} carry {q} {i} {a}, {he} go pay on the 15th", "a")],
        "self_correct": [("sale", "I sell {q} {i} {old}, no no, na {a}", "a")],
        "flag": [("credit_sale", "{n} carry {q} {i} 90k, {he} pay 50k, remain 40k", "flag")],
    },
    "yoruba": {
        "basic": [("credit_sale", "Mo ta {i} {q} fún {n} ní {a}, gbèsè ni, yóò san lọ́jọ́ {d}", "a"),
                  ("sale", "Mo ta {i} {q} ní {a}", "a"),
                  ("payment_received", "{n} ti san {a} tí ó jẹ mí", "a"),
                  ("expense", "Mo san {a} owó ọkọ̀ lọ sí ọjà", "a")],
        "local_numbers": [("sale", "Mo ta {i} {q} ní {L}", "local"),
                          ("payment_received", "{n} ti san {L} tí ó jẹ mí", "local")],
        "unit_price": [("credit_sale", "Mo ta {i} {q} fún {n}, {u} ọ̀kọ̀ọ̀kan, gbèsè ni", "qu")],
        "negation": [("credit_sale", "Mo ta {i} {q} fún {n} ní {a}, kò tíì san owó náà", "a")],
        "part_payment": [("payment_received", "{n} ti san {part} nínú {total} tí ó jẹ mí, ó ku {rem}", "part")],
        "no_amount": [("credit_sale", "Mo ta {i} {q} fún {n}, gbèsè ni, yóò san lọ́jọ́ {d}", None)],
        "distractor": [("payment_received", "{n} ti san {a}, nọ́mbà rẹ̀ ni 08034567812", "a")],
        "code_switch": [("credit_sale", "Mo sell {i} {q} fún {n} {a}, {he} go pay lọ́jọ́ {d}", "a"),
                        ("payment_received", "{n} ti pay {a} tí ó owe mi", "a")],
    },
    "hausa": {
        "basic": [("credit_sale", "Na sayar da {i} {q} ga {n} {a}, bashi ne, za {hp} biya ranar {d}", "a"),
                  ("sale", "Na sayar da {i} {q} a {a}", "a"),
                  ("payment_received", "{n} {hp} biya {a} na bashin {hp_own}", "a"),
                  ("expense", "Na biya {a} kudin mota zuwa kasuwa", "a")],
        "local_numbers": [("sale", "Na sayar da {i} {q} a naira {L}", "local"),
                          ("payment_received", "{n} {hp} biya naira {L} na bashin {hp_own}", "local")],
        "unit_price": [("credit_sale", "Na sayar da {i} {q} ga {n}, kowanne {u}, bashi ne", "qu")],
        "negation": [("credit_sale", "Na sayar da {i} {q} ga {n} {a}, {hp_neg} biya ba tukuna", "a")],
        "part_payment": [("payment_received", "{n} {hp} biya {part} daga cikin {total} na bashin {hp_own}, saura {rem}",
                          "part")],
        "no_amount": [("credit_sale", "Na sayar da {i} {q} ga {n}, bashi ne, za {hp} biya ranar {d}", None)],
        "distractor": [("payment_received", "{n} {hp} biya {a} na bashin {hp_own}, lambar wayarsa 08034567812", "a")],
        "code_switch": [("credit_sale", "Na sell {i} {q} ga {n} {a}, za {hp} pay ranar {d}", "a"),
                        ("payment_received", "{n} don pay {a} na bashin {hp_own}", "a")],
    },
    "igbo": {
        "basic": [("credit_sale", "Ere m {i} {q} nye {n} {a}, ọ ji m ụgwọ, ọ ga-akwụ na {d}", "a"),
                  ("sale", "Ere m {i} {q} na {a}", "a"),
                  ("payment_received", "{n} akwụọla {a} nke ọ ji m", "a"),
                  ("expense", "Akwụrụ m {a} maka ụgbọ ala gaa ahịa", "a")],
        "local_numbers": [("sale", "Ere m {i} {q} na naira {L}", "local"),
                          ("payment_received", "{n} akwụọla naira {L} nke ọ ji m", "local")],
        "unit_price": [("credit_sale", "Ere m {i} {q} nye {n}, otu ọ bụla {u}, ọ ji m ụgwọ", "qu")],
        "negation": [("credit_sale", "Ere m {i} {q} nye {n} {a}, ọ kwụbeghị m ego ahụ", "a")],
        "part_payment": [("payment_received", "{n} akwụọla {part} n'ime {total} ọ ji m, ọ fọdụrụ {rem}", "part")],
        "no_amount": [("credit_sale", "Ere m {i} {q} nye {n}, ọ ji m ụgwọ, ọ ga-akwụ na {d}", None)],
        "distractor": [("payment_received", "{n} akwụọla {a} nke ọ ji m, nọmba ekwentị ya bụ 08034567812", "a")],
        "code_switch": [("credit_sale", "Ere m {i} {q} give {n} {a}, {he} go pay {d}", "a"),
                        ("payment_received", "{n} don pay {a} nke ọ ji m", "a")],
    },
}
# how many phrases to draw per template, per category
REPEAT = {"basic": 2, "amount_format": 1, "words": 2, "local_numbers": 2, "unit_price": 2, "negation": 2,
          "part_payment": 2, "no_amount": 2, "distractor": 1, "self_correct": 2, "code_switch": 2, "flag": 1}


def draw(lang, cat, typ, text, rule, style=None):
    name, g = rng.choice(NAMES)
    day_i = rng.randrange(7)
    q = rng.randint(2, 5)
    u = rng.choice([2500, 7500, 15000, 18000, 45000])
    total = rng.choice([30000, 45000, 60000, 80000])
    part = total // rng.choice([2, 3]) // 1000 * 1000
    a = rng.choice(AMOUNTS)
    local_value = rng.choice(sorted(LOCAL_NUMBERS.get(lang, {2000: ""})))
    style = style or ("plain" if lang in ("yoruba", "hausa", "igbo") else rng.choice(["k", "comma", "plain"]))
    if style == "m":
        a = 1200000
    slots = {"n": name, "q": q, "i": rng.choice(ITEMS[lang]), "d": DAYS[lang][day_i], "a": fmt(a, style),
             "u": fmt(u, rng.choice(["k", "comma"])), "part": fmt(part, "k"), "total": fmt(total, "k"),
             "rem": fmt(total - part, "k"), "w": naira_words(a), "old": fmt(a - 1000 if a > 3000 else a + 500, "k"),
             "L": LOCAL_NUMBERS.get(lang, {}).get(local_value, ""),
             "he": "she" if g == "f" else "he", "his": "her" if g == "f" else "his",
             "hp": "ta" if g == "f" else "ya", "hp_own": "ta" if g == "f" else "sa",
             "hp_neg": "ba ta" if g == "f" else "bai"}
    out = text.format(**slots)
    if text[0] == "{":
        out = out[0].upper() + out[1:]
    amount = {"a": a, "w": a, "qu": q * u, "part": part, "local": local_value, None: None}.get(rule)
    case = {"lang": lang, "category": cat, "text": out, "type": typ, "amount": amount,
            "customer": name if "{n}" in text else None}
    if "{d}" in text and typ == "credit_sale":
        case["due_weekday"] = DAYS["english"][day_i]
    if rule == "flag":
        case.update(amount=None, flag=True)
    if lang in ("yoruba", "hausa", "igbo"):
        case["check"] = "native"
    return case


def main():
    import argparse

    global OUT, rng
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=27092026)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    OUT, rng = args.out, random.Random(args.seed)
    cases = []
    for lang, cats in T.items():
        for cat, templates in cats.items():
            for typ, text, rule in templates:
                for _ in range(REPEAT[cat]):
                    cases.append(draw(lang, cat, typ, text, rule))
        # amount formats: the same credit/sale phrases with every way of writing money
        for style in FORMATS + ["m"]:
            typ, text, rule = rng.choice(cats["basic"][:2])
            cases.append(draw(lang, "amount_format", typ, text, rule, style=style))
        # speech-to-text style copies of the clean phrases
        for c in [c for c in cases if c["lang"] == lang and c["category"] == "basic"][::2] + \
                 [c for c in cases if c["lang"] == lang and c["category"] in ("negation", "part_payment")][:2]:
            cases.append(dict(c, category="asr_noise", text=noisy(c["text"], lang)))
    # drop exact duplicates, then number them
    seen, uniq = set(), []
    for c in cases:
        if c["text"] not in seen:
            seen.add(c["text"])
            uniq.append(c)
    counters = {}
    with open(OUT, "w", encoding="utf-8") as f:
        for c in uniq:
            key = f"{c['lang'][:2]}-{c['category']}"
            counters[key] = counters.get(key, 0) + 1
            f.write(json.dumps({"id": f"{key}-{counters[key]}", **c}, ensure_ascii=False) + "\n")
    by_lang = {}
    for c in uniq:
        by_lang[c["lang"]] = by_lang.get(c["lang"], 0) + 1
    print(f"Wrote {len(uniq)} cases to {OUT}: " + ", ".join(f"{k} {v}" for k, v in by_lang.items()))


if __name__ == "__main__":
    main()
