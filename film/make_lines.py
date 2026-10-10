"""The film's spoken lines, written by the app's own code (src/tts.py), so every voice says exactly what TradeVoice
says. Writes film/lines.json, which film/voices.py turns into Spitch voice clips on the server.
Run: python film/make_lines.py
"""
import datetime as dt
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import tts  # noqa: E402

# the record in the film (made-up customer): 2 bags of rice to Iya Bisi on credit, to pay on Friday
today = dt.date.today()
friday = today + dt.timedelta(days=(4 - today.weekday()) % 7 or 7)
REC = {"type": "credit_sale", "customer": "Iya Bisi", "item": "rice", "quantity": 2, "unit": "bag",
       "amount": 60000, "due_date": friday.isoformat()}


def naira(a):
    return f"₦{int(a):,}"


# Spitch voices (docs.spitch.app/concepts/voices): the four main voices first, then one to compare by ear
VOICES = {"en": ["lucy", "lina"], "yo": ["sade", "funmi"], "ha": ["amina", "zainab"], "ig": ["ngozi", "amara"],
          "pcm": ["ufoma"]}
SPEEDS = [1.0, 0.92]
LANG = {"English": "en", "Yoruba": "yo", "Hausa": "ha", "Igbo": "ig", "Pidgin": "pcm"}

en_entry = tts.entry_sentence(REC, "English", money=naira).replace(", on ", " on ")   # "Iya Bisi will pay you ₦60,000 on Friday."
lines = []


def add(line_id, lang, text, sub, shot):
    code = LANG[lang]
    lines.append({"id": line_id, "shot": shot, "language": lang,
                  "spitch_language": "en" if code == "pcm" else code,   # Spitch has no Pidgin code: the voice carries it
                  "text": tts.speakable(text, lang), "subtitle": sub,
                  "voices": VOICES[code], "speeds": SPEEDS})


# shot 4, live talk: what TradeVoice says back before saving, then the first words after "yes"
ask = tts.live_ask(tts.confirmation_text(REC, "Yoruba", saved=False, rng=random.Random(0)), "Yoruba")
add("yo_ask", "Yoruba", ask, f"{en_entry} Should I save it?", "speak")
saved = tts.confirmation_text(REC, "Yoruba", balance=REC["amount"], saved=True, rng=random.Random(0))
first = tts.first_and_rest(saved)[0]
add("yo_saved", "Yoruba", first, {"Ó ti wọ ìwé.": "It's in the book.", "Mo ti kọ ọ́ sílẹ̀.": "I've written it down."}.get(first, ""), "speak")

# shot 5, four voices, one book: the same record in each voice
for lang in ("English", "Yoruba", "Hausa", "Igbo", "Pidgin"):
    add(f"four_{LANG[lang]}", lang, tts.entry_sentence(REC, lang), en_entry, "four_voices")

# shot 5 option for a tighter cut: the first words of the saved reply in each voice (live talk says these first)
SAVED_EN = {"Done.": "Done.", "Okay, written down.": "Okay, written down.", "Got it.": "Got it.",
            "Mo ti kọ ọ́ sílẹ̀.": "I've written it down.", "Ó ti wọ ìwé.": "It's in the book.",
            "To, na rubuta.": "Okay, I've written it down.", "Shikenan, na rubuta.": "That's it, I've written it down.",
            "Edeela m ya.": "I've written it down.", "O banyela n'akwụkwọ.": "It's in the book."}
for lang, pick in (("English", "Okay, written down. "), ("Yoruba", "Mo ti kọ ọ́ sílẹ̀. "),
                   ("Hausa", "Shikenan, na rubuta. "), ("Igbo", "Edeela m ya. ")):
    assert pick in tts.PREFIX[lang]["saved"], (lang, pick)   # only words the app really says
    add(f"saved_{LANG[lang]}", lang, pick.strip(), SAVED_EN[pick.strip()], "four_voices")

# end card
add("tagline", "English", "TradeVoice. Records that speak your language.", "", "end")

out = {"record": REC, "note": "Made by film/make_lines.py from src/tts.py. Yoruba, Hausa and Igbo lines need the "
       "native-speaker check before the film is published.", "lines": lines}
with open(os.path.join(HERE, "lines.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
for ln in lines:
    print(f"{ln['id']:<10} {ln['language']:<8} {ln['text']}")
