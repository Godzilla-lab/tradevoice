"""Speech-to-text: Whisper for English/Pidgin, Meta omniASR for Yoruba, Hausa and Igbo.

Whisper has no Igbo and is poor at Yoruba/Hausa, so voice notes in those languages go to Meta's Omnilingual ASR
(Apache-2.0, 1,600+ languages), self-hosted on the same Brev GPU.

Mode 1 (recommended on Brev): ASR_URL unset -> models run in this process on the GPU.
Mode 2: ASR_URL=http://<brev-host>:8000 -> calls asr_server/server.py running on the Brev GPU.
"""
import os
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


def transcribe(path, language=None):
    """language: a key of LANGUAGES (e.g. "Yoruba"), a Whisper code like "en", or None for auto.
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
    elif engine == "omni":
        out = _omni_transcribe(path, code)
    else:
        model = _local_model()
        segments, info = model.transcribe(path, language=code, vad_filter=True,
                                          initial_prompt=INITIAL_PROMPT, beam_size=5)
        out = {"text": " ".join(s.text.strip() for s in segments).strip(), "language": info.language,
               "engine": f"local:faster-whisper-{_model_name}"}
    out["latency_ms"] = round((time.perf_counter() - start) * 1000)
    return out


def omni_languages_ok():
    """Check our three omniASR language codes are supported by the installed package."""
    from omnilingual_asr.models.wav2vec2_llama.lang_ids import supported_langs

    return {code: code in supported_langs for eng, code in LANGUAGES.values() if eng == "omni"}
