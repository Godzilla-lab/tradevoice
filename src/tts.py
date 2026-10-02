"""Voice replies for traders who can't read: turn a saved entry into a short spoken confirmation.

ONE engine (team decision 2 Oct): Intron Sahara TTS (infer.voice.intron.io/tts/v1/generate), native Yoruba, Hausa
and Igbo voices and Nigerian English (also used for Pidgin), INTRON_API_KEY. N-ATLaS has no voice model (its terms:
"four ASR models and one Text LLM"), so Intron only SPEAKS the reply our code wrote; N-ATLaS hears and understands.
Spitch and Meta MMS were removed. If Intron fails or runs out of credit, the trader gets the reply as text (never a
broken voice note). TTS_BACKEND=off turns voice off. Same sentence + language again = cached audio, no new credit.

Amounts are always spoken as ENGLISH words ("forty-five thousand naira"): no engine reads digits reliably in
Yoruba/Hausa/Igbo, and traders commonly say prices in English anyway.
⚠️ The Yoruba/Hausa/Igbo sentences below were written by a non-native speaker: have native speakers check them.
"""
import os
import re
import time
import tempfile

REPLY_LANGS = ["English", "Yoruba", "Hausa", "Igbo"]   # no Pidgin choice since 2 Oct

# Intron: spoken language + accent are two fields (docs.voice.intron.io/docs/tts/supported-languages-and-accents).
# English replies are read by Intron's Nigerian Pidgin voice (pcm + pidgin): it sounds like the market, and Intron has
# no "nigerian" English accent any more. INTRON_ENGLISH_VOICE=en switches back to an accented English voice.
_EN = ("en", "hausa") if os.getenv("INTRON_ENGLISH_VOICE", "pcm").lower() == "en" else ("pcm", "pidgin")
INTRON_VOICES = {"English": _EN, "Pidgin": _EN, "Yoruba": ("yo", "yoruba"), "Hausa": ("ha", "hausa"),
                 "Igbo": ("ig", "igbo")}
INTRON_URL = os.getenv("INTRON_TTS_URL", "https://infer.voice.intron.io").rstrip("/")

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

# in a live voice conversation there is no Save button to press: the question is asked out loud, answered with yes/no
ASK_LIVE = {"English": " Should I save it?", "Pidgin": " Make I save am?", "Yoruba": " Ṣé kí n kọ ọ́ sílẹ̀?",
            "Hausa": " In rubuta?", "Igbo": " Ka m dee ya?"}


def live_ask(spoken, language="English"):
    """The read-back for the live conversation, short so it is said sooner: "Okay, I heard: <record>. Is that
    correct? Press save." becomes "<record>. Should I save it?" (the trader just said it; a warning stays first)."""
    pre = PREFIX.get(language, PREFIX["English"])
    for ask in pre["ask"]:
        if spoken and spoken.endswith(ask):
            body = spoken[: -len(ask)]
            for opener in pre["heard"]:
                if opener in body:
                    head, tail = body.split(opener, 1)
                    body = head + tail[:1].upper() + tail[1:]
                    break
            return body + ASK_LIVE.get(language, ASK_LIVE["English"])
    return spoken


_FEMALE = ("mama", "iya", "aunty", "auntie", "madam", "hajiya", "hajia", "alhaja", "mrs", "sister", "iyawo", "mallama")


def _female(name):
    """Guess from the title (Mama Tunde, Hajiya Amina); unknown -> 'he' forms (English/Pidgin/Hausa)."""
    return bool(name) and name.split()[0].lower().rstrip(".") in _FEMALE


def entry_sentence(rec, language="English", money=None):
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


def confirmation_text(rec, language="English", balance=None, saved=True, rng=None):
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

def backend():
    forced = os.getenv("TTS_BACKEND", "").lower()
    if forced in ("off", "none", "0"):
        return None
    return "intron" if os.getenv("INTRON_API_KEY") else None


def _tmp(suffix):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
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








_INTRON_MAX = {"chars": 240}   # Intron's per-request text limit is learned from its own error message
# Intron requires an accent and its names change between releases: when one is refused, try the next likely one and
# remember the one Intron accepted (INTRON_ACCENT_ENGLISH=... in .env always goes first)
ACCENT_TRIES = {"en": ["hausa", "yoruba", "igbo", "nigerian"], "pcm": ["pidgin"],
                "yo": ["yoruba"], "ha": ["hausa"], "ig": ["igbo"]}
_GOOD_ACCENT = {}


class _BadAccent(Exception):
    pass


def _intron_one(text, language):
    lang, acc = INTRON_VOICES[language]
    first = os.getenv(f"INTRON_ACCENT_{language.upper()}") or _GOOD_ACCENT.get(language) or acc
    tries = [first] + [a for a in ACCENT_TRIES.get(lang, []) if a != first]
    refused = None
    for a in tries:
        try:
            path = _intron_try(text, language, lang, a)
            _GOOD_ACCENT[language] = a
            return path
        except _BadAccent as e:
            refused = refused or str(e)   # Intron's own first message says what was wrong
    raise RuntimeError(f"Intron refused every {language} accent tried ({', '.join(tries)}): {refused}")


def _intron_try(text, language, lang, accent):
    import requests

    body = {"text": text, "voice_language": lang, "voice_gender": os.getenv("INTRON_GENDER", "female"),
            "voice_accent": accent}
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
            time.sleep(0.4)   # short replies are usually ready in well under a second
            data = (requests.get(f"{INTRON_URL}/tts/v1/status/{tid}", headers=head, timeout=20).json() or {}).get("data") or {}
    elif r.status_code != 200:
        msg = str(j.get("message") or r.text)[:200]
        m = re.search(r"max limit of (\d+) characters", msg)
        if m:
            raise _TooLong(int(m.group(1)))
        if r.status_code == 400 and "accent" in msg.lower():
            raise _BadAccent(msg)
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
    from concurrent.futures import ThreadPoolExecutor

    for _ in range(2):
        parts, paths = _pieces(text, _INTRON_MAX["chars"]), []
        try:
            if len(parts) == 1:
                paths = [_intron_one(parts[0], language)]
            else:   # a long reply: every piece is made at the same time (in order), not one after the other
                with ThreadPoolExecutor(max_workers=min(4, len(parts))) as pool:
                    jobs = [pool.submit(_intron_one, part, language) for part in parts]
                    errors = [j.exception() for j in jobs]
                    paths = [j.result() for j, e in zip(jobs, errors) if e is None]
                    bad = next((e for e in errors if e is not None), None)
                    if bad:
                        raise bad
            break
        except _TooLong as e:
            for p in paths:
                os.remove(p)
            _INTRON_MAX["chars"] = max(40, e.n - 5)
        except Exception:
            for p in paths:
                os.remove(p)
            raise
    else:
        raise RuntimeError("Intron kept refusing the text as too long")
    if len(paths) == 1:
        return paths[0]
    if all(p.endswith(".wav") for p in paths):
        return _join_wavs(paths)
    raise RuntimeError("Intron sent a long reply in pieces that can't be joined (not WAV)")


def _event(engine, ok, language, ms=None):
    try:
        import events
        events.log("voice", engine=engine, ok=ok, lang=language, ms=ms)
    except Exception:  # noqa: BLE001
        pass


_CACHE_DIR = os.path.join(tempfile.gettempdir(), "tradevoice-voice-cache")


def speak(text, language="English", fmt="wav", voice=None, speed=None):
    """Return {path, engine} for an Intron audio file of `text`, or None (voice off, no key, or Intron failed:
    the caller then sends text only). The path is a fresh copy the caller may delete.
    An Intron refusal for credit/key reasons rests it for 10 minutes. voice/speed/fmt are kept for old callers."""
    import hashlib
    import shutil

    if backend() != "intron" or language not in INTRON_VOICES or time.time() < _INTRON_DOWN["until"]:
        return None
    key = hashlib.sha256(f"{INTRON_VOICES[language]}|{language}|{speakable(text)}".encode()).hexdigest()[:32]
    cached = os.path.join(_CACHE_DIR, key + ".wav")
    try:
        fresh, t0 = not os.path.exists(cached), time.perf_counter()
        if fresh:
            made = _intron_speak(text, language)
            os.makedirs(_CACHE_DIR, exist_ok=True)
            shutil.move(made, cached)
        out = _tmp(".wav")
        shutil.copyfile(cached, out)
        _event("intron" if fresh else "cache", True, language,   # /team: Intron calls vs free cached replays
               ms=(time.perf_counter() - t0) * 1000 if fresh else None)
        return {"path": out, "engine": f"intron:{INTRON_VOICES[language][0]}"}
    except Exception as e:  # noqa: BLE001
        print(f"Intron voice failed ({language}): {type(e).__name__}: {e}")
        _event("intron", False, language)
        LAST_ERROR["intron"] = f"{language}: {type(e).__name__}: {e}"[:300]
        if any(w in str(e).lower() for w in ("401", "402", "403", "credit", "quota", "unauthori", "forbidden")):
            _INTRON_DOWN["until"], _INTRON_DOWN["why"] = time.time() + 600, str(e)[:200]
        return None


_INTRON_DOWN = {"until": 0.0, "why": ""}
LAST_ERROR = {}   # engine -> last failure, shown by /api/voice_check and check_whatsapp.py


def why_not_intron():
    """Plain reason the voice is not Intron right now (None if it should be)."""
    if not os.getenv("INTRON_API_KEY"):
        return "INTRON_API_KEY is not in .env (or the app was not restarted after adding it)"
    forced = os.getenv("TTS_BACKEND", "").lower()
    if forced not in ("", "intron"):
        return f"TTS_BACKEND={forced} in .env forces another voice: delete that line (or set TTS_BACKEND=intron)"
    if time.time() < _INTRON_DOWN["until"]:
        return f"Intron refused (key/credits), resting 10 minutes: {_INTRON_DOWN['why']}"
    return LAST_ERROR.get("intron")
