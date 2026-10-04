"""Notebook photo -> draft rows -> the trader ticks/fixes -> saved. Shared by the web app and the WhatsApp bot."""
import ledger
from extract import TYPES, extract_many

LABEL = {"sale": "Sold", "credit_sale": "Sold on credit", "payment_received": "Paid me back",
         "expense": "Spent", "credit_purchase": "Bought on credit", "payment_made": "↩️ I paid back"}


def read(path):
    """Photo file -> {rows, lines, engine, brain, ms}. Raises if no vision model is set up."""
    from vision import read_notebook

    res = read_notebook(path)
    if not res["text"]:
        return {"rows": [], "lines": "", "engine": res["engine"]}
    import re

    m = re.match(r"\s*NOT_A_RECORD\s*:?\s*(.*)", res["text"], re.I | re.S)
    if m:   # the vision model says it isn't a book page or receipt (an advert, a person…): say what it is
        what = re.sub(r"[^\w\s,'-]", "", m.group(1).splitlines()[0] if m.group(1) else "").strip()[:60]
        return {"rows": [], "lines": "", "engine": res["engine"], "not_record": what or "something else"}
    recs, meta = extract_many(res["text"])
    return {"rows": [row(r) for r in recs], "lines": res["text"], "engine": res["engine"],
            "brain": meta["engine"], "ms": res["latency_ms"] + meta["latency_ms"]}


def _written(line):
    """The photo line as written in the book (the reader adds "=> English meaning" after it)."""
    return (line or "").split("=>")[0].strip()


def _meaning(line):
    m = (line or "").partition("=>")[2].strip()
    return "" if m.lower() in ("", "none", "n/a", "-") else m


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
            "quantity": r.get("quantity"), "unit": r.get("unit") or "", "line": _written(r.get("line")),
            "meaning": _meaning(r.get("line")),
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
    """Numbered list for WhatsApp: '1. Sold on credit · Mama Tunde · ₦45,000' (a line it won't save says *Skip*)."""
    out = []
    for n, r in enumerate(rows, 1):
        amt = f"₦{float(r['amount']):,.0f}" if r.get("amount") not in (None, "") else "₦?"
        bits = [LABEL.get(r["type"], r["type"]), r.get("item"), r.get("customer"), amt]
        line = f"{n}. {'' if r.get('save') else '*Skip* '}" + " · ".join(b for b in bits if b)
        if r.get("checks"):
            line += f"\n    Check: {'; '.join(r['checks'])}"
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------- a list pasted into the chat
LIST_SAY = {
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
    "missed": {"English": "These amounts are in your message but not in any line: {m}. Add them by hand if they count.",
               "Pidgin": "Dis amounts dey your message but e no dey any line: {m}. Add dem yourself if dem count.",
               "Yoruba": "Àwọn iye yìí wà nínú ọ̀rọ̀ rẹ ṣùgbọ́n wọn kò sí nínú ìlà kankan: {m}. Fi wọ́n kún un tí wọ́n bá kà.",
               "Hausa": "Waɗannan kuɗaɗen suna cikin saƙonka amma ba su cikin wani layi: {m}. Ka ƙara su idan suna da muhimmanci.",
               "Igbo": "Ego ndị a dị n'ozi gị mana ha adịghị n'ahịrị ọ bụla: {m}. Tinye ha n'onwe gị ma ha dị mkpa."},
    "checkit": {"English": "{who}: {why}", "Pidgin": "{who}: {why}", "Yoruba": "{who}: {why}", "Hausa": "{who}: {why}",
                "Igbo": "{who}: {why}"},
    "cant": {"English": "I can't read a long list right now. Try again in a minute, or send a few at a time.",
             "Pidgin": "I no fit read long list now. Try again small time, or send am small small.",
             "Yoruba": "Mi ò lè ka àkọsílẹ̀ gígùn báyìí. Tún gbìyànjú lẹ́yìn ìṣẹ́jú kan, tàbí fi díẹ̀ ránṣẹ́ lẹ́ẹ̀kan.",
             "Hausa": "Ba zan iya karanta dogon jeri yanzu ba. Sake gwadawa bayan minti ɗaya, ko ka aika kaɗan-kaɗan.",
             "Igbo": "Enweghị m ike ịgụ ogologo ndepụta ugbu a. Nwaa ọzọ mgbe nkeji gachara, ma ọ bụ zipu ole na ole."},
}

LIST_BIG = 1_000_000


def _naira(x):
    return f"₦{x:,.0f}"


def list_rows(recs, kind_book=True):
    """N-ATLaS's records from a pasted list -> lines to check (row() shape). Code marks the ones to look at (not
    ticked): a check from the reader (amount or name not in the message), the same name twice, an amount far bigger
    than the others, someone who already owes (ticking adds to it). Each check is (key, words)."""
    import statistics

    amounts = [r["amount"] for r in recs if r.get("amount")]
    middle = statistics.median(amounts) if amounts else 0
    owing = {ledger.customer_key(d["customer"]): d["balance"] for d in ledger.debtors()}
    rows, seen = [], set()
    for r in recs:
        who, v = r.get("customer") or "", r.get("amount")
        key = ledger.customer_key(who) if who else None
        if r.get("note"):
            why = ("checkit", {"who": who or r.get("item") or "?", "why": r["note"]})
        elif v is None:
            why = ("checkit", {"who": who or "?", "why": "No amount."})
        elif key and key in seen:
            why = ("twice", {"who": who})
        elif v >= LIST_BIG and v > 10 * middle:
            why = ("big", {"who": who or r.get("item") or "?", "m": _naira(v)})
        elif key and r["type"] == "credit_sale" and owing.get(key):
            why = ("owes", {"who": who, "b": _naira(owing[key]), "m": _naira(v)})
        else:
            why = None
        if key:
            seen.add(key)
        rows.append({"save": why is None, "type": r["type"], "amount": v, "customer": who, "due_date": "",
                     "item": r.get("item") or "", "quantity": None, "unit": "", "line": r.get("line") or "",
                     "meaning": "", "checks": [why] if why else []})
    return rows


def list_summary(rows, missed, lang="English"):
    """'I found 42 people who owe you, ₦2,571,500 in all. Check them before I save.' (code adds the total), then the
    lines not ticked and why, then any amount in the message that no line used."""
    lang = lang if lang in LIST_SAY["look"] else "English"
    kinds = [r["type"] for r in rows]
    kind = max(set(kinds), key=kinds.count)
    kind = kind if kind in LIST_SAY["found"] else "credit_sale"
    out = LIST_SAY["found"][kind][lang].format(n=len(rows), m=_naira(sum(r["amount"] or 0 for r in rows)))
    whys = [LIST_SAY[k][lang].format(**kw) for r in rows for k, kw in r["checks"]]
    if whys:
        out += "\n" + LIST_SAY["look"][lang] + "\n" + "\n".join(whys)
    if missed:
        out += "\n" + LIST_SAY["missed"][lang].format(m=", ".join(_naira(v) for v in missed))
    return out


def plain_checks(rows, lang="English"):
    """Before the rows leave the server: each check as words (the line check and WhatsApp show them)."""
    lang = lang if lang in LIST_SAY["look"] else "English"
    return [dict(r, checks=[LIST_SAY[k][lang].format(**kw) for k, kw in r["checks"]]) for r in rows]
