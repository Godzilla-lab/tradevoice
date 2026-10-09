"""Speech-to-text. N-ATLaS first when NATLAS_ASR_URL is set: the 4 NCAIR1 Whisper-Small models on Modal
(deploy/modal_asr.py; Yoruba-ASR, Hausa-ASR, Igbo-ASR, NigerianAccentedEnglish for English and Pidgin).
Intron and Spitch are NOT used while N-ATLaS hears (team decision 2 Oct): they stay to compare against
(eval/run_eval.py --audio --asr natlas|intron|spitch). When N-ATLaS can't make out a note (silence, unclear audio),
the trader is asked to send it again or type it.
Only when the N-ATLaS hearing SERVER is down (asleep, broken, or the Modal credits are used up) does Intron hear the
note instead (ASR_DOWN_BACKUP, default intron when INTRON_API_KEY is set; "none" = nobody, the trader is asked to
type). The server is then marked down for the whole app and checked in the background (natlas_watch.down), so the
next notes go straight to Intron until N-ATLaS answers again.

Before N-ATLaS: Whisper for English/Pidgin, Meta omniASR for Yoruba, Hausa and Igbo.

Whisper has no Igbo and is poor at Yoruba/Hausa, so voice notes in those languages go to Meta's Omnilingual ASR
(Apache-2.0, 1,600+ languages), self-hosted on the same Brev GPU.

Mode 1 (recommended on Brev): ASR_URL unset -> models run in this process on the GPU.
Mode 2: ASR_URL=http://<brev-host>:8000 -> calls asr_server/server.py running on the Brev GPU.
Spitch (Nigerian speech API, `pip install spitch`, SPITCH_API_KEY), chosen with ASR_ENGINE:
  ASR_ENGINE=local        (default) Whisper / omniASR on our GPU; Spitch only as a fallback if they fail
  ASR_ENGINE=spitch       Spitch for every language; our GPU models as the fallback
  ASR_ENGINE=spitch-local Spitch for Yoruba/Hausa/Igbo, Whisper for English/Pidgin
  ASR_ENGINE=intron / intron-local   same, with Intron Sahara (INTRON_API_KEY): code-switched yo/ig/ha/pcm-English
Any cloud engine with a key is also used as a fallback if the others fail.
Which is more accurate is NOT known yet: compare on the team's voice notes (eval/run_eval.py --audio --asr ...).
"""
import os
import re
import shutil
import subprocess
import tempfile
import time

ASR_URL = os.getenv("ASR_URL")
ASR_TOKEN = os.getenv("ASR_TOKEN", "")
LOCAL_MODEL = os.getenv("ASR_MODEL", "large-v3-turbo")
# omniASR_LLM_3B_v2 needs ~10 GB GPU memory (fits next to Whisper on a 24 GB L4); omniASR_LLM_7B_v2 ~17 GB (L40S).
OMNI_MODEL = os.getenv("OMNI_MODEL", "omniASR_LLM_3B_v2")
OMNI_MAX_SECONDS = 39  # omniASR LLM/CTC models accept audio shorter than 40 s
# Biases Whisper toward Nigerian market vocabulary and naira shorthand.
INITIAL_PROMPT = ("Market trader voice note in Nigerian English or Pidgin. Naira amounts like 45k, 2,500, 1.5m. "
                  "Names like Mama Tunde, Iya Bisi, Alhaji Musa, Oga Emeka. Items: bag of rice, garri, beans, "
                  "carton of indomie, crate of eggs, paint of beans, mudu. She go pay Friday. E don pay.")

# Language picked by the trader -> engine. English/Pidgin use Whisper; the rest use omniASR language codes.
LANGUAGES = {"English / Pidgin": ("whisper", "en"), "Yoruba": ("omni", "yor_Latn"),
             "Hausa": ("omni", "hau_Latn"), "Igbo": ("omni", "ibo_Latn")}

SPITCH_LANG = {"English / Pidgin": "en", "Yoruba": "yo", "Hausa": "ha", "Igbo": "ig"}
# Intron: choosing a code-switched pair IS the model choice (docs.voice.intron.io, via github.com/OkeyAmy/volt-intron).
# "pcm" vs "en" changed a number 100x on the same audio in that project's test: compare both on our voice notes.
INTRON_LANG = {"English / Pidgin": os.getenv("INTRON_EN_CODE", "pcm"), "Yoruba": "yo", "Hausa": "ha", "Igbo": "ig"}
INTRON_URL = os.getenv("INTRON_URL", "https://infer.voice.intron.io/file/v1/upload/sync")

NATLAS_ASR_LANG = {"English / Pidgin": "english", "Yoruba": "yoruba", "Hausa": "hausa", "Igbo": "igbo",
                   "en": "english", "yo": "yoruba", "ha": "hausa", "ig": "igbo"}

_model = None
_model_name = None
_omni = None


def _local_model():
    global _model, _model_name
    if _model is None:
        from faster_whisper import WhisperModel
        import ctranslate2

        gpu = ctranslate2.get_cuda_device_count() > 0
        _model_name = LOCAL_MODEL if gpu else os.getenv("ASR_CPU_MODEL", "small")
        _model = WhisperModel(_model_name,
                              device="cuda" if gpu else "cpu",
                              compute_type="float16" if gpu else "int8")
    return _model


def _omni_pipeline():
    global _omni
    if _omni is None:
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline

        _omni = ASRInferencePipeline(model_card=OMNI_MODEL)
    return _omni


def to_wav16k(path, max_seconds=None):
    """Phone/browser audio (m4a, ogg, webm, mp3…) -> 16 kHz mono WAV. Returns a temp path the caller deletes."""
    if not shutil.which("ffmpeg"):
        if path.lower().endswith(".wav"):
            return _trim_wav(path, max_seconds)  # no ffmpeg: WAV is readable as is, just enforce the length limit
        if path.lower().endswith(".flac"):
            return None
        raise RuntimeError("ffmpeg is needed to convert this audio: sudo apt-get install -y ffmpeg")
    fd, out = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000"]
    if max_seconds:
        cmd += ["-t", str(max_seconds)]
    subprocess.run(cmd + [out], check=True)
    return out


def _trim_wav(path, max_seconds):
    """Copy of a WAV cut to max_seconds (None if already short enough)."""
    import wave

    with wave.open(path) as w:
        params, rate, frames = w.getparams(), w.getframerate(), w.getnframes()
        if not max_seconds or frames <= rate * max_seconds:
            return None
        data = w.readframes(int(rate * max_seconds))
    fd, out = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(out, "w") as o:
        o.setparams(params)
        o.writeframes(data)
    return out


def _duration_s(wav):
    import wave

    with wave.open(wav) as w:
        return w.getnframes() / w.getframerate()


def _omni_transcribe(path, code):
    wav = to_wav16k(path, max_seconds=OMNI_MAX_SECONDS)
    src = wav or path
    try:
        result = _omni_pipeline().transcribe([src], lang=[code], batch_size=1)[0]
        text = result if isinstance(result, str) else (getattr(result, "text", None) or
                                                       (result.get("text") if isinstance(result, dict) else str(result)))
        note = None
        if wav and _duration_s(wav) >= OMNI_MAX_SECONDS - 0.5:
            note = f"Only the first {OMNI_MAX_SECONDS} seconds were used; send shorter voice notes."
        return {"text": text.strip(), "language": code, "engine": f"local:{OMNI_MODEL}", "note": note}
    finally:
        if wav:
            os.remove(wav)


def _prompt(vocab):
    """Whisper's prompt + this trader's own names/items (Whisper only reads the last ~224 tokens: keep it short)."""
    if not vocab:
        return INITIAL_PROMPT
    extra = ", ".join((vocab.get("names") or [])[:15] + (vocab.get("items") or [])[:8])
    return f"{INITIAL_PROMPT} {extra}." if extra else INITIAL_PROMPT


def _spitch_transcribe(path, language, vocab=None):
    """Spitch speech-to-text (model mansa_v1). special_words = this trader's names/items (format: comma-separated,
    unverified against Spitch's docs)."""
    from spitch import Spitch

    wav = to_wav16k(path) if shutil.which("ffmpeg") else None
    try:
        with open(wav or path, "rb") as f:
            audio = f.read()
        kwargs = {"content": audio, "language": SPITCH_LANG.get(language, "en"), "model": "mansa_v1"}
        words = ", ".join((vocab or {}).get("names", [])[:20] + (vocab or {}).get("items", [])[:10])
        if words:
            kwargs["special_words"] = words
        resp = Spitch().speech.transcribe(**kwargs)
        return {"text": (resp.text or "").strip(), "language": kwargs["language"], "engine": "spitch:mansa_v1"}
    finally:
        if wav:
            os.remove(wav)


def _intron_transcribe(path, language, vocab=None):
    """Intron Sahara synchronous file API: multipart audio_file_name / audio_file_blob / use_language_asr_input,
    Bearer key, files <= 120 s, transcript in data.audio_transcript."""
    import requests

    wav = to_wav16k(path, max_seconds=119) if shutil.which("ffmpeg") else None
    try:
        with open(wav or path, "rb") as f:
            name = os.path.basename(wav or path)
            r = requests.post(INTRON_URL, headers={"Authorization": f"Bearer {os.environ['INTRON_API_KEY']}"},
                              # general, not Intron's default telehealth (medical) post-processing, and no
                              # Intron AI rewriting: a market note must never come back as a medical sentence
                              data={"audio_file_name": name, "use_language_asr_input": INTRON_LANG.get(language, "pcm"),
                                    "use_category": "file_category_general", "use_disable_llm_corrections": "TRUE"},
                              files={"audio_file_blob": (name, f, "audio/wav")}, timeout=60)
        if r.status_code in (401, 403):
            raise RuntimeError("Intron: key rejected (check INTRON_API_KEY)")
        r.raise_for_status()
        text = (r.json().get("data") or {}).get("audio_transcript")
        if not isinstance(text, str):
            raise RuntimeError(f"Intron: no transcript in the answer ({str(r.json())[:120]})")
        return {"text": text.strip(), "language": INTRON_LANG.get(language, "pcm"), "engine": "intron:sahara"}
    finally:
        if wav:
            os.remove(wav)


def looping(text, seconds=None):
    """Whisper-Small fine-tunes can get stuck repeating themselves on hard audio (an independent test saw
    whisper-tiny loop on 7 of 20 Hausa clips, worst on numbers). Never take an amount from such a transcript."""
    words = re.findall(r"[\w'-]+", (text or "").lower())   # "kaka nan, kaka nan," -> same words, no commas
    for n in (1, 2, 3):
        run = 1
        for i in range(n, len(words) - n + 1, n):
            run = run + 1 if words[i:i + n] == words[i - n:i] else 1
            if run >= 4:
                return True
    if seconds and len(text or "") > 40 + 30 * seconds:  # far more words than anyone says in that time
        return True
    return False


class Down(RuntimeError):
    """The N-ATLaS hearing server didn't answer (asleep, broken, no credits): not the trader's audio."""


def down_backup_name():
    """Who hears voice notes while the N-ATLaS hearing server is down (None = nobody)."""
    name = (os.getenv("ASR_DOWN_BACKUP") or "intron").strip().lower()
    key = {"intron": "INTRON_API_KEY", "spitch": "SPITCH_API_KEY"}.get(name)
    return name if key and os.getenv(key) else None


def _down_backup():
    if os.getenv("ASR_ONLY"):   # benchmarks: the engine alone, nothing hiding its failures
        return None
    return {"intron": _intron_transcribe, "spitch": _spitch_transcribe}.get(down_backup_name() or "")


def _natlas_transcribe(path, language, vocab=None):
    """N-ATLaS speech model for the trader's language, on our Modal server.
    The server sleeps after an hour with no voice notes and takes a minute or two to wake.
    - A backup can hear (Intron): one try of NATLAS_ASR_FIRST (15 s). No answer -> Down: the backup hears this note,
      and the server is woken and checked in the background (the trader doesn't wait for it).
    - No backup: one normal try (NATLAS_ASR_TIMEOUT, 60 s); if it doesn't answer, wake it (/health waits until it is
      up) and try once more with the long wait (NATLAS_ASR_TIMEOUT_COLD, 240 s), instead of telling the trader
      "I couldn't hear you"."""
    import requests

    lang = NATLAS_ASR_LANG.get(language or "English / Pidgin", "english")
    hints = ", ".join((vocab or {}).get("names", [])[:15] + (vocab or {}).get("items", [])[:8])
    base = os.environ["NATLAS_ASR_URL"].rstrip("/")
    head = {"Authorization": f"Bearer {os.getenv('NATLAS_KEY', '')}"}

    # two models on one note for Yoruba / Hausa / Igbo (traders mix in English), merged by N-ATLaS (hearing.py)
    also = "english" if lang != "english" and os.getenv("NATLAS_ASR_MERGE", "1") == "1" else ""
    form = {"lang": lang, "prompt": hints, "prep": os.getenv("NATLAS_ASR_PREP", "1"), "also": also}

    def send(timeout):
        with open(path, "rb") as f:
            return requests.post(base + "/transcribe", files={"file": (os.path.basename(path), f)},
                                 data=form, headers=head, timeout=timeout)
    slow = (requests.exceptions.Timeout, requests.exceptions.ConnectionError)
    try:
        if _down_backup():
            try:
                r = send(float(os.getenv("NATLAS_ASR_FIRST", "15")))
            except slow as e:
                raise Down(f"N-ATLaS speech server didn't answer in time ({type(e).__name__})") from e
        else:
            try:
                r = send(float(os.getenv("NATLAS_ASR_TIMEOUT", "60")))
            except slow:
                print("N-ATLaS speech server didn't answer in time: waking it, then one more try")
                try:
                    requests.get(base + "/health", headers=head,
                                 timeout=float(os.getenv("NATLAS_ASR_TIMEOUT_COLD", "240")))
                except slow:
                    pass
                r = send(float(os.getenv("NATLAS_ASR_TIMEOUT_COLD", "240")))
        status = getattr(r, "status_code", 200)
        if status == 401:
            raise Down("N-ATLaS speech server refused the key: NATLAS_KEY on the server and on Modal differ")
        if status == 404:
            raise Down("N-ATLaS speech server link is wrong (404): check NATLAS_ASR_URL")
        if status in (402, 403, 429) or status >= 500:
            raise Down(f"N-ATLaS speech server error (HTTP {status})")
        r.raise_for_status()
        out = r.json()
    except Down as e:
        import llm
        llm._natlas_down("natlas_asr", e)   # the next notes skip it until a background check finds it up
        raise
    except slow as e:   # the long wait ran out too
        import llm
        llm._natlas_down("natlas_asr", e)
        raise Down(f"N-ATLaS speech server didn't answer ({type(e).__name__})") from e
    if out.get("no_speech"):
        raise RuntimeError("no speech heard (silence or too quiet)")
    if looping(out.get("text"), out.get("seconds")):
        raise RuntimeError("N-ATLaS speech model repeated itself (unclear audio)")
    import hearing

    text, engine = (out.get("text") or "").strip(), f"natlas:{out.get('model')}"
    second = out.get("also") if isinstance(out.get("also"), dict) else None
    if second and looping(second.get("text"), out.get("seconds")):
        second = None
    res = {"text": text, "language": lang, "engine": engine}
    if second:
        res["heard"] = [text, (second.get("text") or "").strip()]
        merged, how = hearing.merge(text, second.get("text"), lang.title(), vocab)
        res["merge"] = how
        if how == "merged":
            res["text"], res["engine"] = merged, engine + "+english:merged"
    chk = hearing.check(out, second, res["text"])
    if chk:
        res["check"] = chk
    return res


def _local_transcribe(path, language, vocab):
    engine, code = LANGUAGES.get(language, ("whisper", language or None))
    if engine == "omni":
        return _omni_transcribe(path, code)
    model = _local_model()
    segments, info = model.transcribe(path, language=code, vad_filter=True,
                                      initial_prompt=_prompt(vocab), beam_size=5)
    return {"text": " ".join(s.text.strip() for s in segments).strip(), "language": info.language,
            "engine": f"local:faster-whisper-{_model_name}"}


def transcribe(path, language=None, vocab=None):
    """language: a key of LANGUAGES (e.g. "Yoruba"), a Whisper code like "en", or None for auto.
    vocab: {"names": [...], "items": [...]} from this trader's book (helps Whisper; omniASR takes no prompt).
    Return {text, language, latency_ms, engine[, note]}."""
    start = time.perf_counter()
    engine, code = LANGUAGES.get(language, ("whisper", language or None))
    if ASR_URL:
        import requests

        with open(path, "rb") as f:
            r = requests.post(ASR_URL.rstrip("/") + "/transcribe", files={"file": f},
                              data={"language": language or ""},
                              headers={"Authorization": f"Bearer {ASR_TOKEN}"} if ASR_TOKEN else {},
                              timeout=120)
        r.raise_for_status()
        out = r.json()
        out["engine"] = f"remote:{out.get('engine', out.get('model', 'asr'))}"
    else:
        # default: Intron when its key is set (best for our 5 languages), else our own models
        import llm

        natlas = llm.natlas_hearing_on()
        mode = (os.getenv("ASR_ENGINE") or ("natlas" if natlas else
                                            "intron" if os.getenv("INTRON_API_KEY") else "local")).lower()
        clouds = {"natlas": (_natlas_transcribe, "NATLAS_ASR_URL"),
                  "spitch": (_spitch_transcribe, "SPITCH_API_KEY"), "intron": (_intron_transcribe, "INTRON_API_KEY")}
        chosen = mode.replace("-local", "")
        cloud_first = chosen in clouds and (not mode.endswith("-local") or engine == "omni")
        ready = [name for name, (_, key) in clouds.items()   # cloud engines with a key (N-ATLaS: unless switched off)
                 if os.getenv(key) and (name != "natlas" or natlas)]
        order = ([clouds[chosen][0]] if cloud_first and chosen in ready else []) + [_local_transcribe]
        if os.getenv("ASR_ONLY"):   # benchmarks: this engine alone, no fallback hiding its failures
            order = order[:1]
        elif natlas and mode == "natlas":
            # the app hears with N-ATLaS (team decision 2 Oct): Intron/Spitch are for comparison tests, and hear
            # only while the N-ATLaS server is down (below). ASR_BACKUPS (e.g. "intron") = also on unclear audio.
            order = [_natlas_transcribe] + [clouds[n][0] for n in os.getenv("ASR_BACKUPS", "").split(",")
                                            if n.strip() in ready and n.strip() != "natlas"]
            if _down_backup() and llm.natlas_resting("natlas_asr"):
                order = [_down_backup()]   # marked down: no wait at all (a background check brings N-ATLaS back)
        elif mode == "natlas":   # ASR_ENGINE=natlas but NATLAS_MODE=off: the backup that hears while it is down
            order = [f for f in (_down_backup(),) if f]
        else:
            order += [clouds[name][0] for name in ready if clouds[name][0] not in order]  # the rest = fallbacks
        out, errors, was_down = None, [], False
        for fn in order:
            try:
                out = fn(path, language, vocab)
                break
            except Exception as e:  # noqa: BLE001 - try the other engine
                errors.append(f"{fn.__name__.strip('_').split('_')[0]}: {type(e).__name__}: {str(e)[:80]}")
                if isinstance(e, Down):
                    was_down = True
                    if _down_backup() and _down_backup() not in order:
                        order.append(_down_backup())   # the server is down, not the audio: the backup hears it
        if out is None:
            _event("natlas" if mode == "natlas" else mode, False, (time.perf_counter() - start) * 1000, language)
            raise (Down if was_down or not order else RuntimeError)(
                "Speech-to-text failed: " + (" | ".join(errors) or "N-ATLaS hearing is switched off and no backup is set"))
        if errors:
            out["note"] = ((out.get("note") or "") + f" (first engine failed: {errors[0]})").strip()
    out["latency_ms"] = round((time.perf_counter() - start) * 1000)
    _event(out.get("engine"), True, out["latency_ms"], language)
    return out


def _event(engine, ok, ms, language):
    try:
        import events
        events.log("hear", engine=engine, ok=ok, ms=ms, lang=language)
    except Exception:  # noqa: BLE001
        pass


def omni_languages_ok():
    """Check our three omniASR language codes are supported by the installed package."""
    from omnilingual_asr.models.wav2vec2_llama.lang_ids import supported_langs

    return {code: code in supported_langs for eng, code in LANGUAGES.values() if eng == "omni"}


LOCAL = {"Yoruba", "Hausa", "Igbo"}


def transcribe_auto(path, language=None, vocab=None):
    """transcribe(), then check which language the words are in. If they look like another of our languages
    (e.g. the trader spoke Yoruba while "English / Pidgin" was selected), hear it again in that language, so the
    trader never has to switch by hand. Returns the same dict plus "detected" (the language to use next time)."""
    import askbook

    out = transcribe(path, language, vocab)
    detected = askbook.guess_language(out.get("text") or "")
    if detected in LOCAL and detected != language:
        try:
            again = transcribe(path, detected, vocab)
            if (again.get("text") or "").strip():
                again["latency_ms"] = again.get("latency_ms", 0) + out.get("latency_ms", 0)
                out = again
        except Exception:  # noqa: BLE001 - keep the first result
            pass
    if detected in LOCAL:
        out["detected"] = detected
    elif language in LOCAL:
        out["detected"] = language  # the trader chose Yoruba/Hausa/Igbo: words without tone marks don't undo that
    else:
        out["detected"] = "English / Pidgin"
    return out
