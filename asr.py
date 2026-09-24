"""Speech-to-text client.

Mode 1 (recommended on Brev): ASR_URL unset -> faster-whisper runs in this process on the GPU.
Mode 2: ASR_URL=http://<brev-host>:8000 -> calls asr_server/server.py running on the Brev GPU.
"""
import os
import time

ASR_URL = os.getenv("ASR_URL")
ASR_TOKEN = os.getenv("ASR_TOKEN", "")
LOCAL_MODEL = os.getenv("ASR_MODEL", "large-v3-turbo")
# Biases Whisper toward Nigerian market vocabulary and naira shorthand.
INITIAL_PROMPT = ("Market trader voice note in Nigerian English or Pidgin. Naira amounts like 45k, 2,500, 1.5m. "
                  "Names like Mama Tunde, Iya Bisi, Alhaji Musa, Oga Emeka. Items: bag of rice, garri, beans, "
                  "carton of indomie, crate of eggs, paint of beans, mudu. She go pay Friday. E don pay.")

_model = None
_model_name = None


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


def transcribe(path, language=None):
    """Return {text, language, latency_ms, engine}."""
    start = time.perf_counter()
    if ASR_URL:
        import requests

        with open(path, "rb") as f:
            r = requests.post(ASR_URL.rstrip("/") + "/transcribe", files={"file": f},
                              data={"language": language or ""},
                              headers={"Authorization": f"Bearer {ASR_TOKEN}"} if ASR_TOKEN else {},
                              timeout=90)
        r.raise_for_status()
        out = r.json()
        out["engine"] = f"remote:{out.get('model', 'whisper')}"
    else:
        model = _local_model()
        segments, info = model.transcribe(path, language=language or None, vad_filter=True,
                                          initial_prompt=INITIAL_PROMPT, beam_size=5)
        out = {"text": " ".join(s.text.strip() for s in segments).strip(), "language": info.language,
               "engine": f"local:faster-whisper-{_model_name}"}
    out["latency_ms"] = round((time.perf_counter() - start) * 1000)
    return out
