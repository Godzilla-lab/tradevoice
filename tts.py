"""Voice replies for traders who can't read: turn a saved entry into a short spoken confirmation.

Engines (first one available wins, or force with TTS_BACKEND=intron|spitch|mms|off):
- intron : Intron Sahara TTS (infer.voice.intron.io/tts/v1/generate), native Yoruba/Hausa/Igbo voices and Nigerian
           English (also used for Pidgin). Same INTRON_API_KEY as the hearing. If it fails, Spitch, then MMS, take over.
- spitch : Spitch (Nigerian) API, voices for English, Pidgin, Yoruba, Hausa, Igbo. `pip install spitch`, SPITCH_API_KEY.
- mms    : Meta MMS-TTS on our own CPU/GPU (Yoruba, Hausa, English; no Igbo). `pip install -r requirements-tts.txt`.
           Licence CC-BY-NC: fine for the hackathon demo, NOT for a commercial product.

Amounts are always spoken as ENGLISH words ("forty-five thousand naira"): no engine reads digits reliably in
Yoruba/Hausa/Igbo, and traders commonly say prices in English anyway.
⚠️ The Yoruba/Hausa/Igbo sentences below were written by a non-native speaker: have native speakers check them.
"""
import os
import re
import time
import tempfile

REPLY_LANGS = ["Pidgin", "English", "Yoruba", "Hausa", "Igbo"]

# Spitch voice names (from Spitch's SDK/docs, via research; check in their dashboard). Pidgin is chosen by voice.
SPITCH_VOICES = {"English": ("en", "lucy"), "Pidgin": (None, "ufoma"), "Yoruba": ("yo", "sade"),
                 "Hausa": ("ha", "amina"), "Igbo": ("ig", "ngozi")}
# Intron: spoken language + accent are two fields. Accents are overridable (INTRON_ACCENT_YORUBA=...) because Intron's
# accent list isn't public; a rejected accent is retried without one.
INTRON_VOICES = {"English": ("en", "nigerian"), "Pidgin": ("en", "nigerian"), "Yoruba": ("yo", "yoruba"),
                 "Hausa": ("ha", "hausa"), "Igbo": ("ig", "igbo")}
INTRON_URL = os.getenv("INTRON_TTS_URL", "https://infer.voice.intron.io").rstrip("/")
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
        if parts and n < 100:  # 216,050 -> "two hundred and sixteen thousand and fifty"
            return ", ".join(parts) + " and " + _under_1000(n)
        parts.append(_under_1000(n))
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
        "credit_purchase": "You will pay {customer} {amount}{due}.",
        "payment_made": "You have paid {customer} {amount}. Well done!",
        "i_owe": " All together, you still owe {customer} {balance}.",
        "i_cleared": " You don't owe {customer} anything again. Your name is clean!",
    },
    "Pidgin": {
        "sale": "You don sell {item}for {amount}. Market dey move!",
        "credit_sale": "{customer} go pay you {amount}{due}.",
        "payment_received": "{customer} don pay you {amount}. Correct!",
        "expense": "You spend {amount}{item_for}.",
        "due": ", for {day}", "balance": " Now, {she} still dey owe you {balance}.",
        "cleared": " {She} no dey owe you again. E don clear!",
        "credit_purchase": "You go pay {customer} {amount}{due}.",
        "payment_made": "You don pay {customer} {amount}. Correct!",
        "i_owe": " Now, you still dey owe {customer} {balance}.",
        "i_cleared": " You no dey owe {customer} again. Your name clean!",
    },
    "Yoruba": {
        "sale": "O ta ọjà ní {amount}. Ọjà ń tà!",
        "credit_sale": "{customer} jẹ ọ́ ní {amount}{due}.",
        "payment_received": "{customer} ti san {amount}. Ó dáa!",
        "expense": "O ná {amount}.",
        "due": ", yóò san ní {day}", "balance": " Gbogbo gbèsè {customer} báyìí jẹ́ {balance}.",
        "cleared": " {customer} kò jẹ ọ́ ní gbèsè mọ́.",
        "credit_purchase": "O jẹ {customer} ní {amount}{due}.",
        "payment_made": "O ti san {amount} fún {customer}. Ó dáa!",
        "i_owe": " Gbogbo gbèsè tí o jẹ {customer} báyìí jẹ́ {balance}.",
        "i_cleared": " O kò jẹ {customer} ní gbèsè mọ́.",
    },
    "Hausa": {
        # "An ..." (impersonal) avoids guessing the trader's gender
        "sale": "An sayar da kaya na {amount}. Kasuwa na tafiya!",
        "credit_sale": "{customer} {ya} ci bashin {amount}{due}.",
        "payment_received": "{customer} {ya} biya {amount}. Madalla!",
        "expense": "An kashe {amount}.",
        "due": ", {za} biya ranar {day}", "balance": " Yanzu, jimlar bashin {customer} {balance} ne.",
        "cleared": " {customer} ba {ya} da sauran bashi.",
        "credit_purchase": "An karɓi kaya bashi daga {customer}, na {amount}{due}.",
        "payment_made": "An biya {customer} {amount}. Madalla!",
        "i_owe": " Yanzu, jimlar bashin {customer} {balance} ne.",
        "i_cleared": " An gama biyan bashin {customer}.",
    },
    "Igbo": {
        "sale": "I rere ahịa {amount}. Ahịa na-aga!",
        "credit_sale": "{customer} ji gị ụgwọ {amount}{due}.",
        "payment_received": "{customer} akwụọla {amount}. Ọ dị mma!",
        "expense": "I mefuru {amount}.",
        "due": ", ọ ga-akwụ na {day}", "balance": " Ugbu a, ụgwọ {customer} niile bụ {balance}.",
        "cleared": " {customer} anaghị ji gị ụgwọ ọzọ.",
        "credit_purchase": "I ji {customer} ụgwọ {amount}{due}.",
        "payment_made": "I kwụọla {customer} {amount}. Ọ dị mma!",
        "i_owe": " Ugbu a, ụgwọ niile i ji {customer} bụ {balance}.",
        "i_cleared": " I jighị {customer} ụgwọ ọzọ.",
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


def entry_sentence(rec, language="Pidgin", money=None):
    """The core sentence for one entry ("Mama Tunde go pay you forty-five thousand naira, for Friday.").
    money: how to write amounts (default: English words, for speaking)."""
    return _sentence(rec, language, money or naira_words)[0]


def _sentence(rec, language, money):
    t = TEMPLATES.get(language, TEMPLATES["English"])
    day = _day(rec.get("due_date"))
    customer = rec.get("customer") or (
        {"Yoruba": "Oníbàárà", "Hausa": "Abokin ciniki", "Igbo": "Onye ahịa", "Pidgin": "Your customer"}.get(
            language, "Your customer") if rec.get("type") not in ("credit_purchase", "payment_made") else
        {"Yoruba": "olùtajà rẹ", "Hausa": "mai kawo maka kaya", "Igbo": "onye na-ere gị ngwá",
         "Pidgin": "your supplier"}.get(language, "your supplier"))
    female = _female(rec.get("customer"))
    item = rec.get("item")
    slots = dict(amount=money(rec.get("amount") or 0), customer=customer,
                 item=f"{item} " if item and language in ("English", "Pidgin") else "",
                 item_for=f" on {item}" if item and language in ("English", "Pidgin") else "",
                 she="she" if female else "he", She="She" if female else "He", ya="ta" if female else "ya", za="za ta" if female else "zai")
    due = t["due"].format(day=day, **slots) if day else ""
    if rec.get("type") == "credit_purchase":  # "due" phrases say "SHE will pay"; for the trader's own debt use "on <day>"
        due = {"English": f", on {day}", "Pidgin": f", for {day}"}.get(language, f" ({day})") if day else ""
    return t.get(rec.get("type"), t["sale"]).format(due=due, **slots), t, slots


def confirmation_text(rec, language="Pidgin", balance=None, saved=True, rng=None):
    """Short spoken confirmation for one entry. saved=False reads it back for checking before saving.
    `balance` = the customer's total debt after this entry (only spoken once saved). rng: for repeatable tests."""
    import random

    pick = (rng or random).choice
    pre = PREFIX.get(language, PREFIX["English"])
    text, t, slots = _sentence(rec, language, naira_words)
    if not saved:
        return pick(pre["heard"]) + text + pick(pre["ask"])
    text = pick(pre["saved"]) + text
    if rec.get("customer") and rec.get("type") in ("credit_purchase", "payment_made") and balance is not None:
        if balance > 0 and float(balance) == float(rec.get("amount") or 0):
            pass  # first debt with this supplier: the total is the amount just said
        else:
            text += (t["i_owe"].format(balance=naira_words(balance), **slots) if balance > 0 else
                     t["i_cleared"].format(**slots) if rec.get("type") == "payment_made" else "")
    elif rec.get("customer") and rec.get("type") in ("credit_sale", "payment_received") and balance is not None:
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
    if forced in ("intron", "") and os.getenv("INTRON_API_KEY"):
        return "intron"
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


def _spitch(text, language, fmt, voice_override=None, speed=None, with_code=True):
    from spitch import Spitch

    lang, voice = SPITCH_VOICES.get(language, SPITCH_VOICES["English"])
    voice = voice_override or os.getenv(f"TTS_VOICE_{language.upper()}", voice)  # e.g. TTS_VOICE_YORUBA=funmi
    client = Spitch()  # reads SPITCH_API_KEY
    kwargs = {"text": text, "voice": voice, "format": fmt}
    speed = speed or float(os.getenv("TTS_SPEED", "0") or 0)  # 1.0 = Spitch default; try 0.9-1.1
    if speed:
        kwargs["speed"] = speed
    if lang and with_code:
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


def speakable(text):
    """What a voice can say: no emoji, no *bold*/_italic_ marks, no link, ₦ -> naira."""
    import re

    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"₦\s?", "naira ", text)
    text = re.sub(r"[*_~`#>|•👉👇]", " ", text)
    text = "".join(c for c in text if not (0x1F000 <= ord(c) <= 0x1FAFF or 0x2600 <= ord(c) <= 0x27BF or ord(c) in (0xFE0F, 0x200D)))
    return re.sub(r"\s+", " ", text).strip()


def _chunks(text, size=240):
    """Short pieces at sentence ends (long texts are where local-language voices fail)."""
    import re

    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if cur and len(cur) + len(sent) + 1 > size:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    return out + ([cur] if cur else [])


def _join_wavs(paths):
    import wave

    out = _tmp(".wav")
    with wave.open(out, "wb") as w:
        for i, p in enumerate(paths):
            with wave.open(p, "rb") as r:
                if i == 0:
                    w.setparams(r.getparams())
                w.writeframes(r.readframes(r.getnframes()))
    for p in paths:
        os.remove(p)
    return out


def _spitch_safe(text, language, fmt, voice, speed):
    """Spitch, made sturdy: clean text, short pieces, and one retry without the language code. Errors are printed
    (the web app otherwise just stays silent)."""
    text = speakable(text)
    if not text:
        raise RuntimeError("nothing to say")
    parts = _chunks(text) if fmt == "wav" else [text]
    paths = []
    for part in parts:
        try:
            paths.append(_spitch(part, language, fmt, voice, speed))
        except Exception as e:  # noqa: BLE001
            print(f"voice failed ({language}, {voice}, {len(part)} chars): {type(e).__name__}: {e}")
            try:  # some voices reject the language code; the voice already fixes the language
                paths.append(_spitch(part, language, fmt, voice, speed, with_code=False))
            except Exception as e2:  # noqa: BLE001
                print(f"voice failed again without language code: {type(e2).__name__}: {e2}")
                raise
    return paths[0] if len(paths) == 1 else _join_wavs(paths)


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


_INTRON_MAX = {"chars": 240}   # Intron's per-request text limit is learned from its own error message


def _intron_one(text, language, accent=True):
    import requests

    lang, acc = INTRON_VOICES[language]
    body = {"text": text, "voice_language": lang, "voice_gender": os.getenv("INTRON_GENDER", "female")}
    if accent:
        body["voice_accent"] = os.getenv(f"INTRON_ACCENT_{language.upper()}", acc)
    head = {"Authorization": f"Bearer {os.environ['INTRON_API_KEY']}"}
    for _ in range(2):
        r = requests.post(f"{INTRON_URL}/tts/v1/generate", json=body, headers=head, timeout=60)
        if r.status_code != 429:
            break
        time.sleep(min(float(r.headers.get("retry-after") or 2), 10))
    try:
        j = r.json()
    except ValueError:
        j = {}
    data = j.get("data") or {}
    if r.status_code == 503 and (data.get("text_id") or j.get("text_id")):
        tid, end = data.get("text_id") or j.get("text_id"), time.time() + 40
        while time.time() < end and data.get("processing_status") not in ("TTS_TEXT_AUDIO_GENERATED",
                                                                          "TTS_TEXT_AUDIO_PROCESSING_FAILED"):
            time.sleep(1)
            data = (requests.get(f"{INTRON_URL}/tts/v1/status/{tid}", headers=head, timeout=20).json() or {}).get("data") or {}
    elif r.status_code != 200:
        msg = str(j.get("message") or r.text)[:200]
        m = re.search(r"max limit of (\d+) characters", msg)
        if m:
            raise _TooLong(int(m.group(1)))
        if r.status_code == 400 and accent and "accent" in msg.lower():
            return _intron_one(text, language, accent=False)
        raise RuntimeError(f"Intron voice HTTP {r.status_code}: {msg}")
    if data.get("processing_status") != "TTS_TEXT_AUDIO_GENERATED" or not data.get("audio_path"):
        raise RuntimeError(f"Intron voice not ready ({data.get('processing_status') or 'no audio'})")
    audio = requests.get(data["audio_path"], timeout=60)
    audio.raise_for_status()
    kind = ".wav" if audio.content[:4] == b"RIFF" else ".ogg" if audio.content[:4] == b"OggS" else ".mp3"
    path = _tmp(kind)
    with open(path, "wb") as f:
        f.write(audio.content)
    return path


class _TooLong(Exception):
    def __init__(self, n):
        super().__init__(n)
        self.n = n


def _pieces(text, size):
    out = []
    for part in _chunks(text, size):
        while len(part) > size:  # one very long sentence: cut at a space
            cut = part.rfind(" ", 0, size) if " " in part[:size] else size
            out.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            out.append(part)
    return out


def _intron_speak(text, language):
    if language not in INTRON_VOICES:
        raise RuntimeError(f"Intron has no {language} voice")
    text = speakable(text)
    if not text:
        raise RuntimeError("nothing to say")
    for _ in range(2):
        try:
            paths = []
            for part in _pieces(text, _INTRON_MAX["chars"]):
                paths.append(_intron_one(part, language))
            break
        except _TooLong as e:
            for p in paths:
                os.remove(p)
            _INTRON_MAX["chars"] = max(40, e.n - 5)
    else:
        raise RuntimeError("Intron kept refusing the text as too long")
    if len(paths) == 1:
        return paths[0]
    if all(p.endswith(".wav") for p in paths):
        return _join_wavs(paths)
    raise RuntimeError("Intron sent a long reply in pieces that can't be joined (not WAV)")


def speak(text, language="Pidgin", fmt="wav", voice=None, speed=None):
    """Return {path, engine} for an audio file of `text`, or None if no voice engine is set up.
    Order: Intron -> Spitch -> free MMS voices; an engine that fails for credit/key reasons rests for 10 minutes.
    fmt: 'wav'/'mp3' for the web app, 'ogg_opus' for WhatsApp voice notes (Spitch only; others give wav -> convert)."""
    engine = backend()
    if not engine:
        return None
    errors = []
    if engine == "intron" and time.time() >= _INTRON_DOWN["until"]:
        try:
            return {"path": _intron_speak(text, language), "engine": f"intron:{INTRON_VOICES[language][0]}"}
        except Exception as e:  # noqa: BLE001
            print(f"Intron voice failed ({language}): {type(e).__name__}: {e}")
            errors.append(f"Intron: {e}")
            if any(w in str(e).lower() for w in ("401", "402", "403", "credit", "quota", "unauthori", "forbidden")):
                _INTRON_DOWN["until"], _INTRON_DOWN["why"] = time.time() + 600, str(e)[:200]
    spitch_ok = bool(os.getenv("SPITCH_API_KEY")) and os.getenv("TTS_BACKEND", "").lower() in ("", "spitch", "intron")
    if spitch_ok and time.time() >= _SPITCH_DOWN["until"]:
        v = voice or os.getenv(f"TTS_VOICE_{language.upper()}") or SPITCH_VOICES.get(language, ("", ""))[1]
        try:
            return {"path": _spitch_safe(text, language, fmt, v, speed),
                    "engine": f"spitch:{v}" + (f"@{speed}" if speed else "")}
        except Exception as e:  # noqa: BLE001
            msg = str(e).lower()
            errors.append(f"Spitch: {e}"[:200])
            if any(w in msg for w in ("402", "credit", "quota", "401", "unauthori", "forbidden", "403")):
                # out of credits / key refused: stop asking Spitch for 10 minutes
                _SPITCH_DOWN["until"], _SPITCH_DOWN["why"] = time.time() + 600, str(e)[:200]
                print(f"Spitch unavailable ({str(e)[:120]}); trying the free MMS voices for 10 minutes")
            elif not errors[:-1] and engine == "spitch":
                raise
    if language in MMS_MODELS and _mms_ok():
        return {"path": _mms_speak(speakable(text), language), "engine": f"mms:{MMS_MODELS.get(language)}"}
    if engine == "mms":
        return None
    why = "; ".join(errors) or _INTRON_DOWN["why"] or _SPITCH_DOWN["why"] or "error"
    raise RuntimeError(f"No voice worked for {language} ({why})"
                       + ("" if _mms_ok() else " (pip install transformers torch for the free MMS backup voices)"))


_INTRON_DOWN = {"until": 0.0, "why": ""}
_SPITCH_DOWN = {"until": 0.0, "why": ""}


def _mms_ok():
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401

        return True
    except ImportError:
        return False
