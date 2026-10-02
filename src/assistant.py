"""🎙️ Ask TradeVoice: a voice assistant on every screen. Opening it explains the screen out loud in simple words;
then the trader asks anything by voice (Intron hears, the AI on our Brev GPU answers, Spitch speaks).

Numbers are never invented: exact questions ("how much rice did I sell?") are added up from the book (askbook.py);
explanations come from the AI but every number in them must be in the book's facts, else we say the plain
screen summary (readaloud.py) instead. ⚠️ Yoruba / Hausa / Igbo wording needs a native-speaker check.
"""
import json
import re
import threading
import time

import askbook
import insights
import ledger
import readaloud

SCREENS = {"today": "Book (today's sales, spending and money that came in)",
           "owes": "Customers (who owes the trader, who the trader owes, who is late)",
           "insights": "Insights (next 7 days forecast, busiest day, best sellers)",
           "profile": "Record score (a 0-100 score from the trader's own records, for a lender or cooperative)",
           "talk": "Chat"}

PROMPT = """You are TradeVoice, a kind helper for a Nigerian market trader who may not read well. You are speaking
out loud, so write the way a friendly person talks: short sentences, simple everyday words, no lists, no symbols
except ₦. Answer ONLY in __LANG__ (Nigerian Pidgin if __LANG__ is Pidgin). Use ONLY the numbers in the FACTS; never
invent a number, a name or a date. If the facts don't have the answer, say you don't have that record yet.
No investment or legal advice; for loans say a lender decides. For tax, you may repeat TAX_FACTS in simple words,
but never say how much tax they owe or whether they must pay: say their state revenue service decides. At most __N__ sentences.
The trader is looking at: __SCREEN__.
FACTS (from their own book): __FACTS__"""

_cache, _lock = {}, threading.Lock()


def _facts(screen, lang, today=None):
    f = insights.book_facts(today)
    f["this_screen_in_short"] = readaloud.text(screen, lang, written=True) if screen in readaloud.SCREENS else ""
    if screen in ("profile", "talk"):
        import tax

        f["TAX_FACTS"] = [x["text"] for x in tax.facts("English")] + [tax.check("English")]
    return f


def spoken(text):
    """Amounts in words for the voice ("₦16,800" -> "sixteen thousand, eight hundred naira")."""
    from tts import naira_words, number_words

    text = re.sub(r"₦\s?(\d[\d,]*(?:\.\d+)?)", lambda m: naira_words(float(m.group(1).replace(",", ""))), text or "")
    return re.sub(r"\b\d[\d,]{2,}\b", lambda m: number_words(float(m.group(0).replace(",", ""))), text)


def _numbers_ok(answer, facts):
    """Every number of 3+ digits in the answer must be somewhere in the facts (with or without commas)."""
    blob = re.sub(r"[,\s]", "", json.dumps(facts, default=str))
    said = re.findall(r"\d[\d,]{2,}", answer or "")
    return all(re.sub(r",", "", n).lstrip("0") in blob for n in said)


def _ask_ai(question, screen, lang, facts, sentences=4):
    import llm

    prompt = (PROMPT.replace("__LANG__", lang).replace("__N__", str(sentences))
              .replace("__SCREEN__", SCREENS.get(screen, screen)).replace("__FACTS__", json.dumps(facts, default=str)))
    text, model = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": question}],
                           max_tokens=350, temperature=0.2, timeout=25)
    return text.strip(), model


def free(question, lang, today=None):
    """A free question answered by the AI in `lang`, or None (no AI, or it said a number the book doesn't have)."""
    try:
        import llm

        if not llm.available():
            return None
        facts = insights.book_facts(today)
        ans, _ = _ask_ai(question, "talk", lang, facts, sentences=3)
        return ans if ans and _numbers_ok(ans, facts) else None
    except Exception as e:  # noqa: BLE001
        print(f"assistant free fell back: {type(e).__name__}: {e}")
        return None


def explain(screen, lang="English", today=None):
    """What this screen means for the trader, spoken. Cached a minute so the text and the voice match."""
    key = (ledger.book_path(), screen, lang)  # one cache per trader's book
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < 60:
            return hit[1]
        facts = _facts(screen, lang, today)
        plain = facts["this_screen_in_short"] or readaloud.text("today", lang, written=True)
        out = {"text": plain, "spoken": readaloud.text(screen if screen in readaloud.SCREENS else "today", lang),
               "engine": "rules"}
        try:
            import llm

            # Yoruba / Hausa / Igbo: our checked sentences read better than the AI's (a 14B model's Yoruba is weak)
            if llm.available() and lang not in ("Yoruba", "Hausa", "Igbo"):
                ans, model = _ask_ai(f"Explain this screen to me: what the numbers mean for my business and "
                                     f"one thing I should do next.", screen, lang, facts, sentences=5)
                if ans and _numbers_ok(ans, facts):
                    out = {"text": ans, "spoken": spoken(ans), "engine": f"llm:{model}"}
        except Exception as e:  # noqa: BLE001 - the plain summary is always there
            print(f"assistant explain fell back: {type(e).__name__}: {e}")
        _cache[key] = (time.time(), out)
        return out


# Questions the book answers exactly (no AI): the example questions on each screen, in the five languages.
INTENTS = [
    ("cheapest", r"cheap|best price|lowest price|which supplier|who (dey )?sell .{0,20}(less|lower)|where (i|to) (go )?buy|"
                 r"wo ni o din|mafi arha|kacha ọnụ ala|onye na-ere .{0,10}ọnụ ala"),
    ("margin", r"\bmargins?\b|profit (on|for|per|from)|most profit|gain (on|for|per)|wetin i dey gain|which item .{0,20}(profit|gain)|"
               r"ere lori|riba (a kan|daga)|uru (na|n')"),
    ("owed_total", r"(how much|wetin|what)\b.{0,30}\b(owed|owe|owing|debts?|credit)\b.{0,25}\b(total|altogether|in all|all together|everything|everybody|everyone|all of them)\b|"
                   r"\btotal\b.{0,20}\b(owed|owe|owing|debts?|credit)\b|\b(all|everybody|everyone).{0,10}\bowe(s|d)? me\b.{0,15}(how much|total)"),
    ("owe_most", r"owes? (me )?(the )?most|owe (me )?pass|biggest debt|highest debt|who (dey )?owe me pass|ju lo|fi yawa|kacha"),
    ("late", r"\b(who|which).{0,20}\b(late|overdue)\b|\blate (people|customers)|don pass (date|time)|ti pe|jinkiri|egbu oge"),
    ("i_owe", r"what do i (need to |have to )?pay|who do i owe|wetin i (go |dey )?pay|i owe who|my debts?\b|mo je|ana bina|a m ji"),
    ("best", r"(sell|sold|sale).{0,12}(most|pass)|best.?sell|wetin sell pass|what sold most|ta ju|fi sayarwa|kacha ere"),
    ("busy", r"busiest|busy day|which day.{0,20}(busy|best|most)|day wey (market|sell) (dey )?(move|pass)|ojo wo|wace rana|ubochi ole"),
    ("raise", r"(raise|improve|increase|better|go up|boost).{0,15}score|score.{0,15}(higher|up|better)"),
    ("score", r"(my|record|credit) score|score (be|am)|ami mi|makina|akara m"),
]
SAYS = {
    "owed_total": {"English": "People owe you {m} in total, {n}: {list}.",
                   "Pidgin": "People dey owe you {m} for total, {n}: {list}.",
                   "Yoruba": "Gbogbo gbèsè tí wọ́n jẹ ọ́ jẹ́ {m}, {n}: {list}.",
                   "Hausa": "Jimlar bashin da ake binka {m} ne, {n}: {list}.",
                   "Igbo": "Ngụkọta ụgwọ ndị mmadụ ji gị bụ {m}, {n}: {list}."},
    "owed_none": {"English": "Nobody owes you money now.", "Pidgin": "Nobody dey owe you now.",
                  "Yoruba": "Kò sí ẹni tó jẹ ọ́ lówó báyìí.", "Hausa": "Babu wanda ake binsa bashi yanzu.",
                  "Igbo": "Ọ dịghị onye ji gị ụgwọ ugbu a."},
    "margin_one": {"English": "{item}: you sell at {sell} and buy at {buy} per {unit}, so {m} for you on each {unit} ({pct}%).",
                   "Pidgin": "{item}: you dey sell {sell}, you dey buy {buy} per {unit}, so {m} dey enter your pocket for each {unit} ({pct}%).",
                   "Yoruba": "{item}: o ń tà á ní {sell}, o ń rà á ní {buy} fún {unit} kan; èrè {m} lórí {unit} kọ̀ọ̀kan ({pct}%).",
                   "Hausa": "{item}: kana sayarwa {sell}, kana saya {buy} kowane {unit}; riba {m} a kan kowane {unit} ({pct}%).",
                   "Igbo": "{item}: ị na-ere ya {sell}, ị na-azụ ya {buy} otu {unit}; uru {m} n'otu {unit} ọ bụla ({pct}%)."},
    "margin_top": {"English": "Most profit per item: {list}.", "Pidgin": "Item wey dey give you pass: {list}.",
                   "Yoruba": "Èrè tó pọ̀ jù lórí ọjà: {list}.", "Hausa": "Kayan da suka fi riba: {list}.", "Igbo": "Ihe na-enye uru kacha: {list}."},
    "margin_none": {"English": "To see margins, say how many you buy and sell: \"I buy 10 bags rice 120k\", \"I sold 2 bags rice 30k\".",
                    "Pidgin": "Make I fit show your gain, talk how many you buy and sell: \"I buy 10 bags rice 120k\", \"I sell 2 bags rice 30k\".",
                    "Yoruba": "Kí n tó lè fi èrè hàn, sọ iye tí o rà àti tí o tà: \"Mo ra àpò ìrẹsì 10 ní 120k\".",
                    "Hausa": "Don in nuna riba, faɗi yawan da ka saya da wanda ka sayar: \"Na sayi buhun shinkafa 10 kan 120k\".",
                    "Igbo": "Ka m gosi uru, kwuo ole ị zụrụ na ole ị rere: \"Azụrụ m akpa osikapa 10 na 120k\"."},
    "cheap_one": {"English": "{item}: {list}. Cheapest is {best}.", "Pidgin": "{item}: {list}. The cheapest na {best}.",
                  "Yoruba": "{item}: {list}. Ẹni tó din jù ni {best}.", "Hausa": "{item}: {list}. Mafi arha shi ne {best}.",
                  "Igbo": "{item}: {list}. Onye kacha ọnụ ala bụ {best}."},
    "cheap_none": {"English": "To compare suppliers, say who you bought from and how many: \"I buy 10 bags rice from Alhaji Sani 120k\".",
                   "Pidgin": "Make I compare suppliers, talk who you buy from and how many: \"I buy 10 bags rice from Alhaji Sani 120k\".",
                   "Yoruba": "Kí n tó fi àwọn olùtajà wé ara wọn, sọ ẹni tí o rà lọ́wọ́ rẹ̀ àti iye: \"Mo ra àpò ìrẹsì 10 lọ́wọ́ Alhaji Sani\".",
                   "Hausa": "Don in kwatanta masu sayarwa, faɗi wanda ka saya daga gare shi da yawa: \"Na sayi buhun shinkafa 10 daga Alhaji Sani\".",
                   "Igbo": "Ka m tụnyere ndị na-ere, kwuo onye ị zụtara n'aka ya na ole: \"Azụrụ m akpa osikapa 10 n'aka Alhaji Sani\"."},
    "owe_most": {"English": "{name} owes you the most: {m}.", "Pidgin": "{name} dey owe you pass: {m}.",
                 "Yoruba": "{name} ló jẹ ọ́ jù: {m}.", "Hausa": "{name} ne ke da bashinka mafi yawa: {m}.",
                 "Igbo": "{name} ji gị ụgwọ kacha: {m}."},
    "late": {"English": "Late: {list}.", "Pidgin": "Dem wey don pass date: {list}.", "Yoruba": "Àwọn tó ti pẹ́: {list}.",
             "Hausa": "Waɗanda suka makara: {list}.", "Igbo": "Ndị egbuola oge: {list}."},
    "late_none": {"English": "Nobody is late. Well done.", "Pidgin": "Nobody late. Well done.", "Yoruba": "Kò sí ẹni tó pẹ́.",
                  "Hausa": "Babu wanda ya makara.", "Igbo": "Ọ dịghị onye egbuola oge."},
    "i_owe": {"English": "You owe: {list}.", "Pidgin": "You dey owe: {list}.", "Yoruba": "O jẹ: {list}.",
              "Hausa": "Ana binka bashi: {list}.", "Igbo": "Ị ji ụgwọ: {list}."},
    "i_owe_none": {"English": "You don't owe anybody.", "Pidgin": "You no owe anybody.", "Yoruba": "O kò jẹ ẹnikẹ́ni.",
                   "Hausa": "Ba ka bin kowa bashi.", "Igbo": "Ị jighị onye ọ bụla ụgwọ."},
    "best": {"English": "Your best seller in the last 7 days is {item} ({m}).", "Pidgin": "Wetin sell pass for last 7 days na {item} ({m}).",
             "Yoruba": "Ohun tó tà jù ní ọjọ́ méje sẹ́yìn ni {item} ({m}).", "Hausa": "Abin da ya fi sayuwa a kwanaki 7 shi ne {item} ({m}).",
             "Igbo": "Ihe kacha ree n'ụbọchị 7 gara aga bụ {item} ({m})."},
    "busy": {"English": "Your busiest day is usually {d}.", "Pidgin": "Your market dey move pass on {d}.",
             "Yoruba": "Ọjọ́ tí ọjà rẹ ń tà jù ni {d}.", "Hausa": "Ranar da kasuwarka ta fi ci ita ce {d}.",
             "Igbo": "Ụbọchị ahịa gị na-aga nke ọma bụ {d}."},
    "score": {"English": "Your record score is {s} out of 100 ({band}).", "Pidgin": "Your record score na {s} over 100 ({band}).",
              "Yoruba": "Àmì àkọsílẹ̀ rẹ jẹ́ {s} nínú 100 ({band}).", "Hausa": "Makin bayananka {s} ne cikin 100 ({band}).",
              "Igbo": "Akara ndekọ gị bụ {s} n'ime 100 ({band})."},
    "raise": {"English": "To raise your score: {tip}", "Pidgin": "To make your score go up: {tip}",
              "Yoruba": "Láti gbé àmì rẹ sókè: {tip}", "Hausa": "Don ka ƙara makinka: {tip}", "Igbo": "Iji bulie akara gị: {tip}"},
    "empty": {"English": "Your book doesn't have that yet.", "Pidgin": "Your book never get am yet.",
              "Yoruba": "Ìwé rẹ kò tíì ní èyí.", "Hausa": "Littafinka bai da wannan tukuna.", "Igbo": "Akwụkwọ gị enwebeghị nke a."},
}
TIPS = {"Record-keeping consistency": "record every day you open, even small sales.",
        "Profitability": "write down every cost too, so your real profit shows.",
        "Debt collection": "collect what customers owe on the promised day (use the reminder with the pay link).",
        "History length": "keep recording: a longer history counts."}


def book_answer(question, lang="English", today=None):
    """The exact answer from the book for the example questions, or None."""
    from extract import fold

    t = fold(question)
    intent = next((k for k, rx in INTENTS if re.search(rx, t)), None)
    if not intent:
        return None
    say = lambda k, **kw: SAYS[k].get(lang, SAYS[k]["English"]).format(**kw)  # noqa: E731
    money = lambda x: f"₦{x:,.0f}"  # noqa: E731
    if intent == "owed_total":   # code adds it up; the three biggest named, "and N more" for the rest
        d = sorted(ledger.debtors(today), key=lambda x: -x["balance"])
        if not d:
            return say("owed_none")
        people = {"English": "{k} people", "Pidgin": "{k} people", "Yoruba": "ènìyàn {k}", "Hausa": "mutum {k}",
                  "Igbo": "mmadụ {k}"}.get(lang, "{k} people").format(k=len(d)) if len(d) > 1 else \
            {"English": "1 person", "Pidgin": "1 person", "Yoruba": "ènìyàn 1", "Hausa": "mutum 1", "Igbo": "mmadụ 1"}.get(lang, "1 person")
        names = ", ".join(f"{x['customer']} {money(x['balance'])}" for x in d[:3])
        more = {"English": " and {k} more", "Pidgin": " and {k} more", "Yoruba": " àti {k} mìíràn", "Hausa": " da {k} kuma",
                "Igbo": " na {k} ọzọ"}.get(lang, " and {k} more").format(k=len(d) - 3) if len(d) > 3 else ""
        return say("owed_total", m=money(sum(x["balance"] for x in d)), n=people, list=names + more)
    if intent == "owe_most":
        d = sorted(ledger.debtors(today), key=lambda x: -x["balance"])
        return say("owe_most", name=d[0]["customer"], m=money(d[0]["balance"])) if d else say("empty")
    if intent == "late":
        d = [x for x in ledger.debtors(today) if x.get("overdue")]
        return say("late", list=", ".join(f"{x['customer']} {money(x['balance'])}" for x in d)) if d else say("late_none")
    if intent == "i_owe":
        d = ledger.creditors(today)
        return say("i_owe", list=", ".join(f"{x['customer']} {money(x['balance'])}" for x in d)) if d else say("i_owe_none")
    if intent == "margin":
        ms = insights.margins(today=today)
        if not ms:
            return say("margin_none")
        one = next((m for m in ms if re.search(rf"\b{re.escape(m['item'])}s?\b", t)), None)
        if one:
            return say("margin_one", item=one["item"].title(), sell=money(one["sell"]), buy=money(one["buy"]),
                       unit=one["unit"] or "one", m=money(one["margin"]), pct=one["pct"])
        return say("margin_top", list=", ".join(f"{m['item']} {money(m['margin'])}/{m['unit'] or 'one'}" for m in ms[:3]))
    if intent == "cheapest":
        ss = insights.suppliers(today=today)
        one = next((x for x in ss if re.search(rf"\b{re.escape(x['item'])}s?\b", t)), None) or (ss[0] if ss else None)
        if not one:
            return say("cheap_none")
        return say("cheap_one", item=one["item"].title(),
                   list=", ".join(f"{o['supplier']} {money(o['price'])}/{one['unit'] or 'one'}" for o in one["offers"][:3]),
                   best=one["offers"][0]["supplier"])
    if intent == "best":
        top = insights.top_items(days=7, today=today, n=1)
        return say("best", item=top[0]["item"], m=money(top[0]["revenue"])) if top else say("empty")
    if intent == "busy":
        f = insights.forecast(today)
        return say("busy", d=f["busiest_day"]) if f else say("empty")
    p = ledger.credit_profile(today)
    if not p:
        return say("empty")
    if intent == "score":
        return say("score", s=p["score"], band=p["band"])
    weakest = min(p["parts"].items(), key=lambda kv: kv[1][0] / kv[1][1])[0]
    return say("raise", tip=TIPS.get(weakest, "keep recording every day."))


def answer(question, screen, lang="English", state=None, today=None, shop="my shop"):
    """A spoken question -> {text, lang, engine[, pending, choices, message, link]}."""
    import converse
    from extract import fold, parse_amount

    t = fold(question)
    # records, reminders and yes/no go through the same chat brain (so "Mama Tunde paid 5k" works here too)
    if (converse.REMIND.search(t) or converse.TAX.search(t) or converse.YES.match(t) or converse.NO.match(t)
            or (parse_amount(question) is not None and converse.EVENT.search(t) and not converse.QUESTION.search(t))):
        if state is None:
            state = dict(converse.new_state(), prefer=lang)
        r = converse.reply(question, state, today=today, shop=shop)
        return dict(r, engine="chat", pending=bool((state or {}).get("pending")))
    fixed = book_answer(question, lang, today)
    if fixed:  # the example questions: answered straight from the book
        return {"text": fixed, "spoken": spoken(fixed), "lang": lang, "engine": "book:exact"}
    exact = askbook.ask_book(question, today, language=lang)
    if exact:  # counts and totals: added up from the book, not guessed
        return {"text": exact[0], "spoken": exact[1], "lang": lang, "engine": f"book:{exact[4]}"}
    facts = _facts(screen, lang, today)
    try:
        import llm

        if llm.available():
            ans, model = _ask_ai(question, screen, lang, facts)
            if ans and _numbers_ok(ans, facts):
                return {"text": ans, "spoken": spoken(ans), "lang": lang, "engine": f"llm:{model}"}
    except Exception as e:  # noqa: BLE001
        print(f"assistant answer fell back: {type(e).__name__}: {e}")
    a = insights.ask_offline(question, facts)
    return {"text": a, "spoken": spoken(a), "lang": "English" if lang not in ("Pidgin",) else lang, "engine": "rules"}
