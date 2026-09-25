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


TEMPLATES = {
    "English": {
        "sale": "You sold {item}for {amount}.",
        "credit_sale": "{customer} owes you {amount}{due}.",
        "payment_received": "{customer} paid you {amount}.",
        "expense": "You spent {amount}{item_for}.",
        "due": ", to pay on {day}", "balance": " {customer} now owes you {balance} in total.",
    },
    "Pidgin": {
        "sale": "You sell {item}for {amount}.",
        "credit_sale": "{customer} owe you {amount}{due}.",
        "payment_received": "{customer} don pay you {amount}.",
        "expense": "You spend {amount}{item_for}.",
        "due": ", e go pay for {day}", "balance": " Total wey {customer} owe you now na {balance}.",
    },
    "Yoruba": {
        "sale": "O ta ọjà ní {amount}.",
        "credit_sale": "{customer} jẹ ọ́ ní {amount}{due}.",
        "payment_received": "{customer} ti san {amount}.",
        "expense": "O ná {amount}.",
        "due": ", yóò san ní {day}", "balance": " Gbogbo gbèsè {customer} báyìí jẹ́ {balance}.",
    },
    "Hausa": {
        # "An ..." (impersonal) avoids guessing the trader's gender; {ya}/{za} follow the customer's (ya/ta, zai/za ta)
        "sale": "An sayar da kaya na {amount}.",
        "credit_sale": "{customer} {ya} ci bashin {amount}{due}.",
        "payment_received": "{customer} {ya} biya {amount}.",
        "expense": "An kashe {amount}.",
        "due": ", {za} biya ranar {day}", "balance": " Jimlar bashin {customer} yanzu {balance}.",
    },
    "Igbo": {
        "sale": "I rere ahịa {amount}.",
        "credit_sale": "{customer} ji gị ụgwọ {amount}{due}.",
        "payment_received": "{customer} akwụọla {amount}.",
        "expense": "I mefuru {amount}.",
        "due": ", ọ ga-akwụ na {day}", "balance": " Ụgwọ {customer} niile ugbu a bụ {balance}.",
    },
}


# "heard" = read back BEFORE saving so the trader can check it; "saved" = after saving.
PREFIX = {
    "English": {"heard": "I heard: ", "saved": "Recorded. ", "ask": " Press save if this is correct."},
    "Pidgin": {"heard": "I hear say: ", "saved": "I don write am. ", "ask": " If e correct, press save."},
    "Yoruba": {"heard": "Mo gbọ́ pé: ", "saved": "Mo ti kọ ọ́ sílẹ̀. ", "ask": " Tí ó bá tọ̀nà, tẹ save."},
    "Hausa": {"heard": "Na ji cewa: ", "saved": "Na rubuta. ", "ask": " Idan daidai ne, danna save."},
    "Igbo": {"heard": "Anụrụ m na: ", "saved": "Edeela m ya. ", "ask": " Ọ bụrụ na ọ dị mma, pịa save."},
}


_FEMALE = ("mama", "iya", "aunty", "auntie", "madam", "hajiya", "hajia", "alhaja", "mrs", "sister", "iyawo", "mallama")


def _female(name):
    """Guess from the title (Mama Tunde, Hajiya Amina). Only Hausa needs it; unknown -> male form (ya/zai)."""
    return bool(name) and name.split()[0].lower().rstrip(".") in _FEMALE


def confirmation_text(rec, language="Pidgin", balance=None, saved=True):
    """Short spoken confirmation for one entry. saved=False reads it back for checking before saving.
    `balance` = the customer's total debt after this entry (only spoken once saved)."""
    t = TEMPLATES.get(language, TEMPLATES["English"])
    pre = PREFIX.get(language, PREFIX["English"])
    day = _day(rec.get("due_date"))
    customer = rec.get("customer") or {"Yoruba": "Oníbàárà", "Hausa": "Abokin ciniki", "Igbo": "Onye ahịa"}.get(
        language, "The customer")
    item = rec.get("item")
    text = t.get(rec.get("type"), t["sale"]).format(
        amount=naira_words(rec.get("amount") or 0), customer=customer,
        item=f"{item} " if item and language in ("English", "Pidgin") else "",
        item_for=f" on {item}" if item and language in ("English", "Pidgin") else "",
        due=t["due"].format(day=day, za="za ta" if _female(rec.get("customer")) else "zai") if day else "",
        ya="ta" if _female(rec.get("customer")) else "ya")
    if not saved:
        return pre["heard"] + text + pre["ask"]
    text = pre["saved"] + text
    if balance and rec.get("customer") and rec.get("type") in ("credit_sale", "payment_received"):
        text += t["balance"].format(customer=customer, balance=naira_words(balance))
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


def _spitch(text, language, fmt):
    from spitch import Spitch

    lang, voice = SPITCH_VOICES.get(language, SPITCH_VOICES["English"])
    client = Spitch()  # reads SPITCH_API_KEY
    kwargs = {"text": text, "voice": voice, "format": fmt}
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


def speak(text, language="Pidgin", fmt="wav"):
    """Return {path, engine} for an audio file of `text`, or None if no voice engine is set up.
    fmt: 'wav'/'mp3' for the web app, 'ogg_opus' for WhatsApp voice notes (Spitch; MMS gives wav -> convert)."""
    engine = backend()
    if not engine:
        return None
    if engine == "spitch":
        return {"path": _spitch(text, language, fmt), "engine": f"spitch:{SPITCH_VOICES.get(language, ('', ''))[1]}"}
    return {"path": _mms_speak(text, language), "engine": f"mms:{MMS_MODELS.get(language)}"}
