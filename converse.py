"""One conversation, any of our languages, one book.

    Trader: "Mama Tunde dey owe me forty-five thousand."   -> draft record, "say yes to save"
    Trader: "Yes"                                           -> saved, new balance
    Trader: "Ṣé mo ní gbèsè lọ́wọ́ Alhaji?"                  -> answered in Yoruba from the same book
    Trader: "Remind her tomorrow"                           -> "her" = Mama Tunde; reminder set, message ready

Each message is routed (yes/no to a draft, reminder, question, new record) by simple rules; the AI only reads the
record or the question (extract.py / askbook.py); every number comes from the book. The language can change on
every message: each reply follows the language of the message it answers. `reply()` does not depend on the web
page, so the WhatsApp bot can use it as it is.
⚠️ Yoruba / Hausa / Igbo sentences need a native-speaker check.
"""
import datetime as dt
import re

import askbook
import insights
import ledger
import tts
from extract import extract, fold, parse_amount, parse_due

LANGS = askbook.LANGS

YES = re.compile(r"^\s*(yes|yeah|yep|ok|okay|save|save am|save it|correct|na so|e correct|sure|ehn|ee+h?|eh|"
                 r"beeni|o to|o dara|to|haka ne|eh to|i|ee|o di mma|ozi|confirm)\W*$")
NO = re.compile(r"^\s*(no|nope|cancel|no be so|leave am|forget am|rara|ko to|a'?a|ba haka ba|mba|o bughi ya)\W*$")
REMIND = re.compile(r"\bremind\b|\bran .{0,40}\bleti\b|\bleti\b|\btunatar\b|\btuna wa\b|\bcheta(ra)?\b|\bchetara\b")
QUESTION = re.compile(r"\?|\bhow (much|many)\b|\bwho\b|\bwhat\b|\bwetin\b|\babi\b|\bdo i\b|\bdid\b|\bse\b|\bmelo\b|"
                      r"\belo\b|\bnawa\b|\bshin\b|\bole\b|\bkedu\b|\bani\b|\bna who\b")
PRONOUN = re.compile(r"\b(she|he|her|him|am|them|dem|that person|ita|shi|ya)\b")
TOMORROW_LOCAL = re.compile(r"\b(ola|lola|ni ola)\b")
# something happened (a record), in English/Pidgin, Yoruba, Hausa, Igbo
EVENT = re.compile(r"\b(sell|sold|owe|owes|pay|paid|buy|bought|spend|spent|collect|took|carry|give|gave|mo ta|ti san|"
                   r"sayar|biya|saya|rere|kwuru|zutara|ji m)\b")

SAY = {
    "heard": {"English": "I heard: {s} Say *yes* to save, or tell me what to change.",
              "Pidgin": "I hear say: {s} Talk *yes* make I save am, or tell me wetin to change.",
              "Yoruba": "Ohun tí mo gbọ́: {s} Sọ *bẹ́ẹ̀ni* kí n kọ ọ́ sílẹ̀, tàbí sọ ohun tí kò tọ̀nà.",
              "Hausa": "Abin da na ji: {s} Ka ce *eh* in adana, ko ka faɗi abin da za a gyara.",
              "Igbo": "Ihe m nụrụ: {s} Kwuo *ee* ka m chekwaa ya, ma ọ bụ gwa m ihe m ga-agbanwe."},
    "how_much": {"English": "How much was it?", "Pidgin": "Na how much?", "Yoruba": "Èló ni?",
                 "Hausa": "Nawa ne?", "Igbo": "Ego ole?"},
    "saved": {"English": "Saved ✅ {s}", "Pidgin": "I don save am ✅ {s}", "Yoruba": "Mo ti kọ ọ́ sílẹ̀ ✅ {s}",
              "Hausa": "An adana ✅ {s}", "Igbo": "Echekwala m ya ✅ {s}"},
    "balance": {"English": " Now {who} owes you {m} in total.", "Pidgin": " Now {who} dey owe you {m} total.",
                "Yoruba": " Lápapọ̀, {who} jẹ ọ́ ní {m} báyìí.", "Hausa": " Yanzu jimlar bashin {who}: {m}.",
                "Igbo": " Ugbu a {who} ji gị {m} n'ozuzu."},
    "i_owe": {"English": " You now owe {who} {m} in total.", "Pidgin": " Now you dey owe {who} {m} total.",
              "Yoruba": " Lápapọ̀, o jẹ {who} ní {m} báyìí.", "Hausa": " Yanzu jimlar bashin {who} a kanka: {m}.",
              "Igbo": " Ugbu a i ji {who} {m} n'ozuzu."},
    "cancelled": {"English": "OK, I didn't save it.", "Pidgin": "No wahala, I no save am.",
                  "Yoruba": "Ó dáa, mi ò kọ ọ́ sílẹ̀.", "Hausa": "To, ban adana ba.", "Igbo": "Ọ dị mma, echekwaghị m ya."},
    "nothing_pending": {"English": "There is nothing waiting to be saved.", "Pidgin": "Nothing dey wait to save.",
                        "Yoruba": "Kò sí nǹkan tó ń dúró de ìkọsílẹ̀.", "Hausa": "Babu abin da ke jiran adanawa.",
                        "Igbo": "Ọ dịghị ihe na-eche ka e chekwaa ya."},
    "remind_set": {"English": "OK 👍 {when} I'll remind you to collect {m} from {who}.",
                   "Pidgin": "No wahala 👍 {when} I go remind you to collect {m} from {who}.",
                   "Yoruba": "Ó dáa 👍 {when} màá rán ọ létí láti gba {m} lọ́wọ́ {who}.",
                   "Hausa": "To 👍 {when} zan tunatar da kai ka karɓi {m} daga {who}.",
                   "Igbo": "Ọ dị mma 👍 {when} m ga-echetara gị ịnata {m} n'aka {who}."},
    "remind_none": {"English": "{who} doesn't owe you anything now. 🎉", "Pidgin": "{who} no dey owe you anything now. 🎉",
                    "Yoruba": "{who} kò jẹ ọ́ ní nǹkankan báyìí. 🎉", "Hausa": "{who} ba shi da bashinka yanzu. 🎉",
                    "Igbo": "{who} ejighị gị ụgwọ ugbu a. 🎉"},
    "remind_who": {"English": "Who should I remind you about?", "Pidgin": "Na who I go remind you about?",
                   "Yoruba": "Ta ni kí n rán ọ létí nípa rẹ̀?", "Hausa": "Wa zan tunatar da kai game da shi?",
                   "Igbo": "Onye ka m ga-echetara gị maka ya?"},
    "due": {"English": "📌 Today: collect {m} from {who}.", "Pidgin": "📌 Today: collect {m} from {who}.",
            "Yoruba": "📌 Lónìí: gba {m} lọ́wọ́ {who}.", "Hausa": "📌 Yau: karɓi {m} daga {who}.",
            "Igbo": "📌 Taa: nata {m} n'aka {who}."},
    "not_sure": {"English": "Sorry, I didn't get that. Tell me a sale, a debt, or ask about your book.",
                 "Pidgin": "Abeg, I no understand. Tell me wetin you sell, who owe you, or ask me about your book.",
                 "Yoruba": "Má bínú, kò yé mi. Sọ ọjà tí o tà, gbèsè, tàbí béèrè nípa ìwé rẹ.",
                 "Hausa": "Yi haƙuri, ban gane ba. Faɗi abin da ka sayar, bashi, ko ka tambayi littafinka.",
                 "Igbo": "Ndo, aghọtaghị m. Gwa m ihe i rere, ụgwọ, ma ọ bụ jụọ maka akwụkwọ gị."},
}
SAY["which"] = {"English": "Which {n}? You have more than one.", "Pidgin": "Which {n}? You get pass one.",
                "Yoruba": "{n} wo? O ní ju ẹyọ kan lọ.", "Hausa": "Wanne {n}? Kana da fiye da ɗaya.",
                "Igbo": "{n} ole? I nwere karịa otu."}
SAY["new_customer"] = {"English": "New customer", "Pidgin": "New customer", "Yoruba": "Oníbàárà tuntun",
                       "Hausa": "Sabon abokin ciniki", "Igbo": "Onye ahịa ọhụrụ"}
SAY["owes"] = {"English": "owes {m}", "Pidgin": "dey owe {m}", "Yoruba": "jẹ {m}", "Hausa": "bashi {m}",
               "Igbo": "ji {m}"}
SAY["last"] = {"English": "last {d}", "Pidgin": "last {d}", "Yoruba": "{d}", "Hausa": "{d}", "Igbo": "{d}"}

WHEN = {"today": {"English": "Today,", "Pidgin": "Today,", "Yoruba": "Lónìí,", "Hausa": "Yau,", "Igbo": "Taa,"},
        "tomorrow": {"English": "Tomorrow,", "Pidgin": "Tomorrow,", "Yoruba": "Lọ́la,", "Hausa": "Gobe,",
                     "Igbo": "Echi,"},
        "day": {"English": "On {d},", "Pidgin": "On {d},", "Yoruba": "Ní {d},", "Hausa": "Ran {d},", "Igbo": "N'{d},"}}


def new_state():
    return {"pending": None, "pending_text": "", "last_customer": None, "people": [], "lang": "English"}


def _mention(state, name):
    """Remember who we talked about, newest first (for "her", "him", "am")."""
    if name:
        state["last_customer"] = name
        people = [p for p in state.setdefault("people", []) if ledger.customer_key(p) != ledger.customer_key(name)]
        state["people"] = [name] + people[:9]


def _pronoun_person(text, state, owes_me=False, today=None):
    """"her" = the last woman we talked about, "him" = the last man, "am/them" = the last person.
    owes_me: only people who owe the trader (for reminders)."""
    t = fold(text)
    if not PRONOUN.search(t):
        return None
    people = state.get("people") or ([state["last_customer"]] if state.get("last_customer") else [])
    if re.search(r"\b(she|her|ita)\b", t):
        people = [p for p in people if tts._female(p)]
    elif re.search(r"\b(he|him|shi)\b", t):
        people = [p for p in people if not tts._female(p)]
    if owes_me:
        owing = {ledger.customer_key(d["customer"]) for d in ledger.debtors(today)}
        people = [p for p in people if ledger.customer_key(p) in owing]
    return people[0] if people else None


def _money(x):
    return f"₦{x:,.0f}"


def _lang(text, state):
    lang = askbook.guess_language(text)
    # a bare "yes"/"ok"/"45k" says nothing about language: keep the one we were talking in
    if len(fold(text).split()) <= 2 and lang in ("English", "Pidgin"):
        return state.get("lang") or lang
    return lang


def _known_name(text, state, vocab, owes_me=False, today=None):
    """Who the message is about: a name from the book (full or part), else "her/him/am" = the last person."""
    name = askbook.find_name(text, vocab.get("names"))
    if name:
        return name
    return _pronoun_person(text, state, owes_me=owes_me, today=today)


def _full_name(asked, people):
    """"Alhaji" -> "Alhaji Sani" when only one person in `people` fits."""
    fits = [p["customer"] for p in people if askbook.same_person(asked, p["customer"])]
    return fits[0] if len(fits) == 1 else asked


def _out(text, lang, spoken=None, english=None):
    return {"text": text, "spoken": spoken or text, "lang": lang,
            "english": english if lang != "English" else None}


# ---------------------------------------------------------------- the four kinds of message

def _choices(matches, name, lang, today):
    """Buttons to tell same-name customers apart by what matters: balance and last activity."""
    out = []
    for m in matches[:4]:
        s = ledger.customer_summary(m["id"], today) or {}
        bits = [m["name"], SAY["owes"][lang].format(m=_money(s.get("owes_me", 0)))]
        if s.get("last_at"):
            bits.append(SAY["last"][lang].format(d=dt.date.fromisoformat(s["last_at"][:10]).strftime("%d %b").lstrip("0")))
        if s.get("phone"):
            bits.append(s["phone"])
        out.append((f"cust:{m['id']}", " · ".join(bits)))
    out.append(("cust:new", f"+ {SAY['new_customer'][lang]}: {name}"))
    return out


def _ask_which(state, name, matches, lang, today, purpose, text=""):
    state["choose"] = {"ids": [m["id"] for m in matches], "name": name, "for": purpose, "text": text}
    out = _out(SAY["which"][lang].format(n=name), lang, english=SAY["which"]["English"].format(n=name))
    out["choices"] = _choices(matches, name, lang, today)
    return out


def _chosen(t, state):
    """'cust:12' / 'cust:new' / '1' / '2' / 'new' -> customer id, 'new', or None."""
    ids = state["choose"]["ids"]
    m = re.match(r"^cust:(\d+|new)$", t) or re.match(r"^(\d)$", t) or re.match(r"^(new|\+.*)$", t)
    if not m:
        return None
    v = m.group(1)
    if v == "new" or v.startswith("+"):
        return "new"
    if t.startswith("cust:"):
        return int(v) if int(v) in ids else None
    return ids[int(v) - 1] if 1 <= int(v) <= len(ids) else None


def _pick_customer(rec, state, lang, today, text):
    """Link a draft to ONE customer: same name twice -> ask; one -> that one; none -> new customer on save."""
    name = rec.get("customer")
    if not name or rec.get("customer_id"):
        return None
    matches = ledger.find_customers(name)
    exact = [m for m in matches if ledger.customer_key(m["name"]) == ledger.customer_key(name)]
    pool = exact or matches
    if len(pool) > 1:
        return _ask_which(state, name, pool, lang, today, "record", text)
    if len(pool) == 1:
        rec["customer_id"], rec["customer"] = pool[0]["id"], pool[0]["name"]
    return None


def _confirm(state, today):
    rec = state["pending"]
    if rec.pop("_create", False) or (rec.get("customer") and not rec.get("customer_id")):
        rec["customer_id"] = (ledger.create_customer(rec["customer"]) if rec.get("_new_forced")
                              else ledger.resolve_customer(rec["customer"]))
    rec.pop("_new_forced", None)
    ledger.add_entry(rec, raw_text=state.get("pending_text", ""), engine=rec.pop("_engine", "chat"))
    state["pending"], lang = None, state["lang"]
    theirs = mine = None
    if rec.get("customer"):
        theirs, mine = ledger.balance_with(today=today, customer_id=rec.get("customer_id"))
        _mention(state, rec["customer"])
    sentence = tts.entry_sentence(rec, lang, money=_money)
    extra = extra_en = ""
    if rec["type"] in ("credit_sale", "payment_received") and theirs and theirs != rec["amount"]:
        extra = SAY["balance"][lang].format(who=rec["customer"], m=_money(theirs))
        extra_en = SAY["balance"]["English"].format(who=rec["customer"], m=_money(theirs))
    if rec["type"] in ("credit_purchase", "payment_made") and mine and mine != rec["amount"]:
        extra = SAY["i_owe"][lang].format(who=rec["customer"], m=_money(mine))
        extra_en = SAY["i_owe"]["English"].format(who=rec["customer"], m=_money(mine))
    bal = theirs if rec["type"] in ("credit_sale", "payment_received") else mine
    return _out(SAY["saved"][lang].format(s=sentence) + extra, lang,
                spoken=tts.confirmation_text(rec, lang, balance=bal, saved=True),
                english=SAY["saved"]["English"].format(s=tts.entry_sentence(rec, "English", money=_money)) + extra_en)


def _record(text, lang, state, vocab, today):
    rec, meta = extract(text, today=today, vocab=vocab)
    if not rec.get("customer"):
        rec["customer"] = _pronoun_person(text, state, today=today)  # "she don pay 10k" = who we talked about
    rec["_engine"] = meta.get("engine", "chat")
    state["pending"], state["pending_text"] = rec, text
    _mention(state, rec.get("customer"))
    ask = _pick_customer(rec, state, lang, today, text)
    if ask:
        return ask
    if rec.get("amount") in (None, ""):
        return _out(SAY["how_much"][lang], lang, english=SAY["how_much"]["English"])
    return _heard(rec, lang, note=rec.get("note"))


def _heard(rec, lang, note=None):
    written = SAY["heard"][lang].format(s=tts.entry_sentence(rec, lang, money=_money))
    if note:
        written += f"\n⚠️ {note}"
    return _out(written, lang, spoken=tts.confirmation_text(rec, lang, saved=False),
                english=SAY["heard"]["English"].format(s=tts.entry_sentence(rec, "English", money=_money)))


def _when(text, today):
    if TOMORROW_LOCAL.search(fold(text)):
        return today + dt.timedelta(days=1)
    due = parse_due(text, today)
    return dt.date.fromisoformat(due) if due else today


def _when_say(day, today, lang):
    if day == today:
        return WHEN["today"][lang]
    if day == today + dt.timedelta(days=1):
        return WHEN["tomorrow"][lang]
    return WHEN["day"][lang].format(d=day.strftime("%A %d %b").replace(" 0", " "))


def _remind(text, lang, state, vocab, today, shop, forced_id=None):
    who = _known_name(text, state, vocab, owes_me=True, today=today) or state.get("last_customer")
    if not who:
        return _out(SAY["remind_who"][lang], lang, english=SAY["remind_who"]["English"])
    debtors = ledger.debtors(today)
    if forced_id:
        d = next((x for x in debtors if x["customer_id"] == forced_id), None)
        who = d["customer"] if d else who
    else:
        who = _full_name(who, debtors)
        same = [x for x in debtors if askbook.same_person(who, x["customer"])]
        if len({x["customer_id"] for x in same}) > 1:
            return _ask_which(state, who, [ledger.get_customer(x["customer_id"]) for x in same], lang, today,
                              "remind", text)
        d = same[0] if same else None
    _mention(state, who)
    if not d:
        return _out(SAY["remind_none"][lang].format(who=who), lang,
                    english=SAY["remind_none"]["English"].format(who=who))
    day = _when(text, today)
    their_lang = next((l for l in insights.TEMPLATES if re.search(rf"\bin {l.lower()}\b", fold(text))),
                      lang if lang in insights.TEMPLATES else "Pidgin")
    ledger.add_reminder(d["customer"], day.isoformat(), their_lang, customer_id=d["customer_id"])
    msg, link = insights.reminder(d["customer"], their_lang, shop, today=today, customer_id=d["customer_id"])
    if d.get("customer_id"):  # the draft also shows in this customer's conversation
        ledger.add_message(d["customer_id"], msg, sender="tradevoice", kind="reminder", status="draft")
    said = SAY["remind_set"][lang].format(when=_when_say(day, today, lang), m=_money(d["balance"]), who=d["customer"])
    en = SAY["remind_set"]["English"].format(when=_when_say(day, today, "English"), m=_money(d["balance"]),
                                             who=d["customer"])
    spoken = SAY["remind_set"][lang].format(when=_when_say(day, today, lang), m=tts.naira_words(d["balance"]),
                                            who=d["customer"])
    out = _out(said, lang, spoken=spoken, english=en)
    out["message"], out["link"] = msg, link
    return out


def _question(text, lang, state, vocab, today):
    q, engine = askbook.parse(text, vocab)
    if q["kind"] != "query":
        return None
    if not q.get("customer"):
        q["customer"] = _pronoun_person(text, state, today=today)  # "how much she owe now?"
    if q.get("customer") and q["what"] in ("owed_to_me", "i_owe"):
        people = ledger.debtors(today) if q["what"] == "owed_to_me" else ledger.creditors(today)
        q["customer"] = _full_name(q["customer"], people)
    _mention(state, q.get("customer"))
    q["language"] = lang
    res = askbook.run(q, today)
    en = dict(q, language="English")
    out = _out(askbook.answer(q, res), lang, spoken=askbook.answer(q, res, spoken=True),
               english=askbook.answer(en, res))
    out["engine"] = engine
    return out


# ---------------------------------------------------------------- entry point

def reply(text, state=None, today=None, shop="your shop"):
    """One message in -> one reply out: {text, spoken, lang, english, [message, link]}. `state` is updated."""
    state = state if state is not None else new_state()
    today = today or dt.date.today()
    text = (text or "").strip()
    lang = _lang(text, state)
    state["lang"] = lang
    t = fold(text)
    vocab = ledger.known_words()
    pending = state.get("pending")

    if state.get("choose"):  # answer to "Which Feranmi?"
        pick, ch = _chosen(t, state), state["choose"]
        state["choose"] = None  # answered, or they moved on to something else
        if pick is not None:
            if ch["for"] == "remind":
                return _remind(ch["text"], lang, state, vocab, today, shop,
                               forced_id=None if pick == "new" else pick)
            if pending:
                if pick == "new":
                    pending["_create"], pending["_new_forced"], pending["customer_id"] = True, True, None
                else:
                    cu = ledger.get_customer(pick)
                    pending["customer_id"], pending["customer"] = pick, cu["name"]
                if pending.get("amount") in (None, ""):
                    return _out(SAY["how_much"][lang], lang, english=SAY["how_much"]["English"])
                return _heard(pending, lang)
    if YES.match(t):
        if pending and pending.get("amount") not in (None, ""):
            return _confirm(state, today)
        return _out(SAY["nothing_pending"][lang], lang, english=SAY["nothing_pending"]["English"])
    if NO.match(t):
        state["pending"] = None
        return _out(SAY["cancelled"][lang], lang, english=SAY["cancelled"]["English"])
    if pending and pending.get("amount") in (None, "") and parse_amount(text) and len(t.split()) <= 4:
        pending["amount"] = parse_amount(text)  # answer to "How much?"
        return _heard(pending, lang)
    if REMIND.search(t):
        return _remind(text, lang, state, vocab, today, shop)
    amount = parse_amount(text)
    if QUESTION.search(t) or (amount is None and not EVENT.search(t)):
        out = _question(text, lang, state, vocab, today)
        if out:
            return out
    if amount is not None or EVENT.search(t):
        return _record(text, lang, state, vocab, today)
    answer, engine = insights.ask(text)
    if engine == "rules" and not answer:
        return _out(SAY["not_sure"][lang], lang, english=SAY["not_sure"]["English"])
    return _out(answer, lang)


def due_today(lang="English", today=None):
    """"📌 Today: collect ₦63,600 from Mama Tunde." for every reminder that is due."""
    lang = lang if lang in LANGS else "English"
    return [SAY["due"][lang].format(m=_money(r["balance"]), who=r["customer"])
            for r in ledger.reminders(today, due_only=True)]


if __name__ == "__main__":
    s = new_state()
    for line in ("Mama Tunde dey owe me forty-five thousand", "yes", "Ṣé mo ní gbèsè lọ́wọ́ Alhaji?",
                 "Remind Mama Tunde tomorrow"):
        r = reply(line, s)
        print(f"> {line}\n  {r['text']}" + (f"\n  ({r['english']})" if r.get("english") else "")
              + (f"\n  ✉️ {r['message']}" if r.get("message") else ""))
