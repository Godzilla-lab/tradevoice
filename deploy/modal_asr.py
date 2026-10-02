"""N-ATLaS speech recognition (the 4 NCAIR1 Whisper-Small models) on Modal, as one small HTTP API.

    POST /transcribe   form: file=<audio, any format>, lang=yoruba|hausa|igbo|english, prompt=<optional hints>
                       header: Authorization: Bearer <NATLAS_KEY>
    -> {"text", "model", "seconds", "ms", "loop"}

Models (chosen by the trader's language; Pidgin and English use NigerianAccentedEnglish, team decision 1 Oct):
    yoruba -> NCAIR1/Yoruba-ASR   hausa -> NCAIR1/Hausa-ASR   igbo -> NCAIR1/Igbo-ASR
    english / pidgin -> NCAIR1/NigerianAccentedEnglish

Deploy (same Modal secret as the LLM: NATLAS_KEY + HF_TOKEN with the Yoruba-ASR conditions accepted):
    modal deploy deploy/modal_asr.py          # prints the URL -> NATLAS_ASR_URL in .env
Runs on CPU by default (Whisper-Small is ~244M parameters, no GPU queue, cheap). NATLAS_ASR_GPU=T4 for a GPU.
Sleeps after 60 idle minutes like the LLM; the web app's market-hours ping keeps it warm in the day.
"""
import os

import modal

MODELS = {"yoruba": "NCAIR1/Yoruba-ASR", "hausa": "NCAIR1/Hausa-ASR", "igbo": "NCAIR1/Igbo-ASR",
          "english": "NCAIR1/NigerianAccentedEnglish"}
GPU = os.getenv("NATLAS_ASR_GPU") or None
SLEEP_AFTER = int(os.getenv("NATLAS_SLEEP_MIN", "60"))

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    # EXACT versions (a floating transformers broke the LLM server on 2 Oct). Change only on purpose, then re-test.
    .pip_install("torch==2.8.0", "transformers==4.57.6", "tokenizers==0.22.2", "huggingface_hub==0.36.2",
                 "hf_transfer==0.1.9", "soundfile==0.13.1", "numpy==2.2.6", "fastapi[standard]==0.118.0",
                 "python-multipart==0.0.20", "accelerate==1.10.1")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
hf_cache = modal.Volume.from_name("tradevoice-hf-cache", create_if_missing=True)
app = modal.App("tradevoice-natlas-asr")


@app.cls(image=image, gpu=GPU, cpu=4.0, memory=8192, secrets=[modal.Secret.from_name("natlas")],
         volumes={"/root/.cache/huggingface": hf_cache}, scaledown_window=SLEEP_AFTER * 60, timeout=600)
@modal.concurrent(max_inputs=4)
class ASR:
    @modal.enter()
    def load(self):
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor

        torch.set_num_threads(4)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.models = {}
        for lang, repo in MODELS.items():  # all 4 in memory (~1 GB each on CPU): no wait when the language changes
            proc = WhisperProcessor.from_pretrained(repo, token=os.environ.get("HF_TOKEN"))
            model = WhisperForConditionalGeneration.from_pretrained(repo, torch_dtype=dtype,
                                                                    token=os.environ.get("HF_TOKEN"))
            self.models[lang] = (proc, model.to(self.device).eval())

    def _audio(self, data):
        """Any format (WhatsApp .ogg/Opus, m4a, webm, wav) -> 16 kHz mono float32 via ffmpeg. Light prep only:
        no denoising (a 2025 study found it made Whisper worse)."""
        import subprocess

        import numpy as np
        out = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000",
                              "-f", "f32le", "pipe:1"], input=data, capture_output=True, check=True).stdout
        return np.frombuffer(out, dtype=np.float32)

    def _has_speech(self, audio):
        """Enough loud 30 ms frames to be a voice? (silence test on 2 Oct: Yoruba/Igbo/Hausa looped, English
        'heard' the hint names.) Threshold relative to the loudest part, with an absolute floor."""
        import numpy as np
        n = 480
        frames = audio[: len(audio) // n * n].reshape(-1, n) if len(audio) >= n else audio.reshape(1, -1)
        rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1) + 1e-12)
        if rms.max() < 0.005:                      # about -46 dBFS: nothing there
            return False
        loud = rms > max(0.005, rms.max() * 0.1)
        return loud.sum() * n / 16000 >= 0.3       # at least 0.3 s of voice

    def _run(self, lang, audio, prompt):
        import torch
        proc, model = self.models[lang]
        texts = []
        for start in range(0, max(len(audio), 1), 30 * 16000):   # Whisper hears 30 s at a time
            chunk = audio[start:start + 30 * 16000]
            if len(chunk) < 1600:                                 # <0.1 s left over
                continue
            feats = proc(chunk, sampling_rate=16000, return_tensors="pt").input_features
            feats = feats.to(self.device, dtype=next(model.parameters()).dtype)
            kw = {"max_new_tokens": min(440, 40 + int(len(chunk) / 16000 * 12))}  # cap: ~12 tokens per second
            if prompt:  # the trader's own names/items: Whisper reads ~224 tokens of prompt, keep it short
                kw["prompt_ids"] = proc.get_prompt_ids(prompt[:600], return_tensors="pt").to(self.device)
            with torch.inference_mode():
                ids = model.generate(feats, **kw)
            text = proc.batch_decode(ids, skip_special_tokens=True)[0]
            if prompt and text.strip().startswith(prompt[:40].strip()):
                text = text.strip()[len(prompt[:600].strip()):]  # some versions echo the prompt back
            texts.append(text.strip())
        return " ".join(t for t in texts if t)

    @modal.asgi_app()
    def web(self):
        import time

        from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
        api = FastAPI()

        @api.get("/health")
        def health(authorization: str = Header("")):
            if authorization != f"Bearer {os.environ['NATLAS_KEY']}":
                raise HTTPException(401)
            return {"ok": True, "models": MODELS}

        @api.post("/transcribe")
        async def transcribe(file: UploadFile = File(...), lang: str = Form("english"), prompt: str = Form(""),
                             authorization: str = Header("")):
            if authorization != f"Bearer {os.environ['NATLAS_KEY']}":
                raise HTTPException(401)
            lang = {"pidgin": "english", "yo": "yoruba", "ha": "hausa", "ig": "igbo", "en": "english"}.get(
                lang.lower(), lang.lower())
            if lang not in self.models:
                raise HTTPException(400, f"lang must be one of {sorted(self.models)}")
            t = time.perf_counter()
            audio = self._audio(await file.read())
            seconds = len(audio) / 16000
            if not self._has_speech(audio):   # Whisper invents words on silence (loops, or the hint names)
                return {"text": "", "no_speech": True, "model": MODELS[lang], "seconds": round(seconds, 1),
                        "ms": round((time.perf_counter() - t) * 1000)}
            text = self._run(lang, audio, prompt.strip())
            return {"text": text, "model": MODELS[lang], "seconds": round(seconds, 1),
                    "ms": round((time.perf_counter() - t) * 1000)}

        return api
