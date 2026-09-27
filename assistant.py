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
No investment, tax or legal advice; for loans say a lender decides. At most __N__ sentences.
The trader is looking at: __SCREEN__.
FACTS (from their own book): __FACTS__"""

_cache, _lock = {}, threading.Lock()


def _facts(screen, lang, today=None):
    f = insights.book_facts(today)
    f["this_screen_in_short"] = readaloud.text(screen, lang, written=True) if screen in readaloud.SCREENS else ""
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
    key = (screen, lang)
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

            if llm.available():
                ans, model = _ask_ai(f"Explain this screen to me: what the numbers mean for my business and "
                                     f"one thing I should do next.", screen, lang, facts, sentences=5)
                if ans and _numbers_ok(ans, facts):
                    out = {"text": ans, "spoken": spoken(ans), "engine": f"llm:{model}"}
        except Exception as e:  # noqa: BLE001 - the plain summary is always there
            print(f"assistant explain fell back: {type(e).__name__}: {e}")
        _cache[key] = (time.time(), out)
        return out


def answer(question, screen, lang="English", state=None, today=None, shop="my shop"):
    """A spoken question -> {text, lang, engine[, pending, choices, message, link]}."""
    import converse
    from extract import fold, parse_amount

    t = fold(question)
    # records, reminders and yes/no go through the same chat brain (so "Mama Tunde paid 5k" works here too)
    if (converse.REMIND.search(t) or converse.YES.match(t) or converse.NO.match(t)
            or (parse_amount(question) is not None and converse.EVENT.search(t) and not converse.QUESTION.search(t))):
        r = converse.reply(question, state if state is not None else converse.new_state(), today=today, shop=shop)
        return dict(r, engine="chat", pending=bool((state or {}).get("pending")))
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
