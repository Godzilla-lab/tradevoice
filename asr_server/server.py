"""Standalone speech-to-text API for a Brev GPU instance (Whisper + omniASR, same logic as ../asr.py).

Run:  cd asr_server && uvicorn server:app --host 0.0.0.0 --port 8000
Only needed if the Gradio app runs somewhere other than the Brev box.
"""
import os
import sys
import tempfile

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.pop("ASR_URL", None)  # this server IS the ASR backend: always run models locally
import asr  # noqa: E402

TOKEN = os.getenv("ASR_TOKEN", "")
app = FastAPI(title="TradeVoice ASR")


@app.get("/health")
def health():
    return {"ok": True, "whisper": asr.LOCAL_MODEL, "omni": asr.OMNI_MODEL, "languages": list(asr.LANGUAGES)}


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
        return asr.transcribe(tmp.name, language or None)
