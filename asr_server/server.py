"""Standalone Whisper speech-to-text API for a Brev GPU instance.

Run:  uvicorn server:app --host 0.0.0.0 --port 8000
Only needed if the Gradio app runs somewhere other than the Brev box.
"""
import os
import tempfile
import time

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from faster_whisper import WhisperModel

MODEL = os.getenv("ASR_MODEL", "large-v3-turbo")
TOKEN = os.getenv("ASR_TOKEN", "")
INITIAL_PROMPT = ("Market trader voice note in Nigerian English or Pidgin. Naira amounts like 45k, 2,500, 1.5m. "
                  "Names like Mama Tunde, Iya Bisi, Alhaji Musa, Oga Emeka. Items: bag of rice, garri, beans, "
                  "carton of indomie, crate of eggs, paint of beans, mudu. She go pay Friday. E don pay.")

app = FastAPI(title="TradeVoice ASR")
model = WhisperModel(MODEL, device="cuda", compute_type="float16")


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...), language: str = Form(""),
                     authorization: str = Header("")):
    if TOKEN and authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "bad token")
    suffix = os.path.splitext(file.filename or "")[1] or ".wav"
    # Audio is written to a temp file only for decoding and deleted immediately.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(await file.read())
        tmp.flush()
        start = time.perf_counter()
        segments, info = model.transcribe(tmp.name, language=language or None, vad_filter=True,
                                          initial_prompt=INITIAL_PROMPT, beam_size=5)
        text = " ".join(s.text.strip() for s in segments).strip()
    return {"text": text, "language": info.language, "model": MODEL,
            "gpu_ms": round((time.perf_counter() - start) * 1000)}
