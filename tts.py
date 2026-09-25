"""Voice replies for traders who can't read: turn a saved entry into a short spoken confirmation.

Engines (first one available wins, or force with TTS_BACKEND=spitch|mms|off):
- spitch : Spitch (Nigerian) API, voices for English, Pidgin, Yoruba, Hausa, Igbo. `pip install spitch`, SPITCH_API_KEY.
- mms    : Meta MMS-TTS on our own CPU/GPU (Yoruba, Hausa, English; no Igbo). `pip install -r requirements-tts.txt`.
           Licence CC-BY-NC: fine for the hackathon demo, NOT for a commercial product.

Amounts are always spoken as ENGLISH words ("forty-five thousand naira"): no engine reads digits reliably in
Yoruba/Hausa/Igbo, and traders commonly say prices in English anyway.
⚠️ The Yoruba/Hausa/Igbo sentences below were written by a non-native speaker: have native speakers check them.
"""
import os
import tempfile

REPLY_LANGS = ["Pidgin", "English", "Yoruba", "Hausa", "Igbo"]

# Spitch voice names (from Spitch's SDK/docs, via research; check in their dashboard). Pidgin is chosen by voice.
SPITCH_VOICES = {"English": ("en", "lucy"), "Pidgin": (None, "ufoma"), "Yoruba": ("yo", "sade"),
                 "Hausa": ("ha", "amina"), "Igbo": ("ig", "ngozi")}
MMS_MODELS = {"English": "facebook/mms-tts-eng", "Pidgin": "facebook/mms-tts-eng",
              "Yoruba": "facebook/mms-tts-yor", "Hausa": "facebook/mms-tts-hau"}

# ------------------------------------------------------------------ amounts in English words

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _under_1000(n):
    words = []
    if n >= 100:
        words += [_ONES[n // 100], "hundred"]
        n %= 100
        if n:
            words.append("and")
    if n >= 20:
        words.append(_TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else ""))
    elif n or not words:
        words.append(_ONES[n])
    return " ".join(words)


def number_words(n):
    """45000 -> 'forty-five thousand'; 1250000 -> 'one million, two hundred and fifty thousand'."""
    n = int(round(float(n)))
    if n == 0:
        return "zero"
    parts = []
    for value, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")):
        if n >= value:
            parts.append(f"{_under_1000(n // value)} {name}")
            n %= value
    if n:
        parts.append(("and " if parts and n < 100 else "") + _under_1000(n))
    return ", ".join(parts)


def naira_words(amount):
    return f"{number_words(amount)} naira"


# ------------------------------------------------------------------ what to say

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _day(due):
    if not due:
        return None
    import datetime as dt

    try:
        return _DAYS[dt.date.fromisoformat(str(due)).weekday()]
    except ValueError:
        return None


# Tone: a friendly market helper who respects the trader, not a bank. Short sentences; commas give the voice
# natural pauses; a few openers are rotated so it doesn't sound like a machine repeating itself.
# {she}/{her} (English/Pidgin) and {ya}/{za} (Hausa) follow the customer's title (Mama/Iya/Aunty -> she).
TEMPLATES = {
    "English": {
        "sale": "You sold {item}for {amount}. Nice one!",
        "credit_sale": "{customer} will pay you {amount}{due}.",
        "payment_received": "{customer} has paid you {amount}. Good news!",
        "expense": "You spent {amount}{item_for}.",
        "due": ", on {day}", "balance": " All together, {she} is still owing you {balance}.",
        "cleared": " {She} is not owing you anything again.",
    },
    "Pidgin": {
        "sale": "You don sell {item}for {amount}. Market dey move!",
        "credit_sale": "{customer} go pay you {amount}{due}.",
        "payment_received": "{customer} don pay you {amount}. Correct!",
        "expense": "You spend {amount}{item_for}.",
        "due": ", for {day}", "balance": " Now, {she} still dey owe you {balance}.",
        "cleared": " {She} no dey owe you again. E don clear!",
    },
    "Yoruba": {
        "sale": "O ta ọjà ní {amount}. Ọjà ń tà!",
        "credit_sale": "{customer} jẹ ọ́ ní {amount}{due}.",
        "payment_received": "{customer} ti san {amount}. Ó dáa!",
        "expense": "O ná {amount}.",
        "due": ", yóò san ní {day}", "balance": " Gbogbo gbèsè {customer} báyìí jẹ́ {balance}.",
        "cleared": " {customer} kò jẹ ọ́ ní gbèsè mọ́.",
    },
    "Hausa": {
        # "An ..." (impersonal) avoids guessing the trader's gender
        "sale": "An sayar da kaya na {amount}. Kasuwa na tafiya!",
        "credit_sale": "{customer} {ya} ci bashin {amount}{due}.",
        "payment_received": "{customer} {ya} biya {amount}. Madalla!",
        "expense": "An kashe {amount}.",
        "due": ", {za} biya ranar {day}", "balance": " Yanzu, jimlar bashin {customer} {balance} ne.",
        "cleared": " {customer} ba {ya} da sauran bashi.",
    },
    "Igbo": {
        "sale": "I rere ahịa {amount}. Ahịa na-aga!",
        "credit_sale": "{customer} ji gị ụgwọ {amount}{due}.",
        "payment_received": "{customer} akwụọla {amount}. Ọ dị mma!",
        "expense": "I mefuru {amount}.",
        "due": ", ọ ga-akwụ na {day}", "balance": " Ugbu a, ụgwọ {customer} niile bụ {balance}.",
        "cleared": " {customer} anaghị ji gị ụgwọ ọzọ.",
    },
}


# "heard" = read back BEFORE saving so the trader can check it; "saved" = after saving. Openers are rotated.
PREFIX = {
    "English": {"heard": ["Okay, I heard: ", "Alright, so: "], "saved": ["Done! ", "Okay, written down. ",
                                                                        "Got it! "],
                "ask": [" Is that correct? Press save."]},
    "Pidgin": {"heard": ["Ehen, I hear say: ", "Okay o, na this one: "],
               "saved": ["I don write am! ", "E don enter book! ", "Sharp sharp, I don write am. "],
               "ask": [" Na so? If e correct, press save."]},
    "Yoruba": {"heard": ["Ó dáa, mo gbọ́ pé: "], "saved": ["Mo ti kọ ọ́ sílẹ̀! ", "Ó ti wọ ìwé! "],
               "ask": [" Ṣé bẹ́ẹ̀ ni? Tí ó bá tọ̀nà, tẹ save."]},
    "Hausa": {"heard": ["To, na ji cewa: "], "saved": ["To, na rubuta! ", "Shikenan, na rubuta. "],
              "ask": [" Haka ne? Idan daidai ne, danna save."]},
    "Igbo": {"heard": ["Ọ dị mma, anụrụ m na: "], "saved": ["Edeela m ya! ", "O banyela n'akwụkwọ! "],
             "ask": [" Ọ bụ otu a? Ọ bụrụ na ọ dị mma, pịa save."]},
}

_FEMALE = ("mama", "iya", "aunty", "auntie", "madam", "hajiya", "hajia", "alhaja", "mrs", "sister", "iyawo", "mallama")


def _female(name):
    """Guess from the title (Mama Tunde, Hajiya Amina); unknown -> 'he' forms (English/Pidgin/Hausa)."""
    return bool(name) and name.split()[0].lower().rstrip(".") in _FEMALE


def confirmation_text(rec, language="Pidgin", balance=None, saved=True, rng=None):
    """Short spoken confirmation for one entry. saved=False reads it back for checking before saving.
    `balance` = the customer's total debt after this entry (only spoken once saved). rng: for repeatable tests."""
    import random

    pick = (rng or random).choice
    t = TEMPLATES.get(language, TEMPLATES["English"])
    pre = PREFIX.get(language, PREFIX["English"])
    day = _day(rec.get("due_date"))
    customer = rec.get("customer") or {"Yoruba": "Oníbàárà", "Hausa": "Abokin ciniki", "Igbo": "Onye ahịa",
                                       "Pidgin": "Your customer"}.get(language, "Your customer")
    female = _female(rec.get("customer"))
    item = rec.get("item")
    slots = dict(amount=naira_words(rec.get("amount") or 0), customer=customer,
                 item=f"{item} " if item and language in ("English", "Pidgin") else "",
                 item_for=f" on {item}" if item and language in ("English", "Pidgin") else "",
                 she="she" if female else "he", She="She" if female else "He", ya="ta" if female else "ya", za="za ta" if female else "zai")
    text = t.get(rec.get("type"), t["sale"]).format(due=t["due"].format(day=day, **slots) if day else "", **slots)
    if not saved:
        return pick(pre["heard"]) + text + pick(pre["ask"])
    text = pick(pre["saved"]) + text
    if rec.get("customer") and rec.get("type") in ("credit_sale", "payment_received") and balance is not None:
        if balance > 0:
            text += t["balance"].format(balance=naira_words(balance), **slots)
        elif rec.get("type") == "payment_received":
            text += t["cleared"].format(**slots)
    return text


# ------------------------------------------------------------------ engines

_mms = {}


def backend():
    forced = os.getenv("TTS_BACKEND", "").lower()
    if forced in ("off", "none", "0"):
        return None
    if forced in ("spitch", "") and os.getenv("SPITCH_API_KEY"):
        try:
            import spitch  # noqa: F401

            return "spitch"
        except ImportError:
            if forced == "spitch":
                raise
    if forced in ("mms", ""):
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401

            return "mms"
        except ImportError:
            if forced == "mms":
                raise
    return None


def _tmp(suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return path


def _spitch(text, language, fmt, voice_override=None, speed=None):
    from spitch import Spitch

    lang, voice = SPITCH_VOICES.get(language, SPITCH_VOICES["English"])
    voice = voice_override or os.getenv(f"TTS_VOICE_{language.upper()}", voice)  # e.g. TTS_VOICE_YORUBA=funmi
    client = Spitch()  # reads SPITCH_API_KEY
    kwargs = {"text": text, "voice": voice, "format": fmt}
    speed = speed or float(os.getenv("TTS_SPEED", "0") or 0)  # 1.0 = Spitch default; try 0.9-1.1
    if speed:
        kwargs["speed"] = speed
    if lang:
        kwargs["language"] = lang
    resp = client.speech.generate(**kwargs)
    path = _tmp({"ogg_opus": ".ogg", "mp3": ".mp3"}.get(fmt, ".wav"))
    if hasattr(resp, "write_to_file"):
        resp.write_to_file(path)
    else:  # older/newer SDKs: raw bytes or .read()
        data = resp.read() if hasattr(resp, "read") else (resp.content if hasattr(resp, "content") else resp)
        with open(path, "wb") as f:
            f.write(data)
    return path


def _mms_speak(text, language):
    import numpy as np
    import torch
    import wave
    from transformers import AutoTokenizer, VitsModel

    name = MMS_MODELS.get(language)
    if not name:
        raise RuntimeError(f"MMS has no {language} voice; use Spitch for {language}")
    if name not in _mms:
        _mms[name] = (VitsModel.from_pretrained(name), AutoTokenizer.from_pretrained(name))
    model, tok = _mms[name]
    with torch.no_grad():
        audio = model(**tok(text, return_tensors="pt")).waveform[0].numpy()
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    path = _tmp(".wav")
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(model.config.sampling_rate)
        w.writeframes(pcm)
    return path


def speak(text, language="Pidgin", fmt="wav", voice=None, speed=None):
    """Return {path, engine} for an audio file of `text`, or None if no voice engine is set up.
    fmt: 'wav'/'mp3' for the web app, 'ogg_opus' for WhatsApp voice notes (Spitch; MMS gives wav -> convert)."""
    engine = backend()
    if not engine:
        return None
    if engine == "spitch":
        v = voice or os.getenv(f"TTS_VOICE_{language.upper()}") or SPITCH_VOICES.get(language, ("", ""))[1]
        return {"path": _spitch(text, language, fmt, v, speed), "engine": f"spitch:{v}" + (f"@{speed}" if speed else "")}
    return {"path": _mms_speak(text, language), "engine": f"mms:{MMS_MODELS.get(language)}"}
