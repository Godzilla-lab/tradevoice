"""N-ATLaS speech recognition (the 4 NCAIR1 Whisper-Small models) on Modal, as one small HTTP API.

    POST /transcribe   form: file=<audio, any format>, lang=yoruba|hausa|igbo|english, prompt=<optional hints>,
                             prep=1|0 (light audio prep, default 1), also=<a second language model on the same note>
                       header: Authorization: Bearer <NATLAS_KEY>
    -> {"text", "model", "seconds", "ms", "unsure": [{"word", "p"}], "confidence",
        "also": {"text", "model", "unsure", "confidence"}}   ("also" only when asked)

Two models on one note (ROADMAP Part 5): for Yoruba / Hausa / Igbo the app also asks for "english", so a trader who
mixes languages is heard by both; the app's N-ATLaS LLM merges the two (src/hearing.py). Both run at the same time,
so the server has 8 CPUs by default (NATLAS_ASR_CPU).
"unsure" = words the model wasn't sure of (lowest token probability < NATLAS_ASR_UNSURE, default 0.4): the app asks
again for just that part ("Say the amount again").

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
CPU = float(os.getenv("NATLAS_ASR_CPU", "8"))
UNSURE = float(os.getenv("NATLAS_ASR_UNSURE", "0.4"))
PREP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "speech_prep.py")
SLEEP_AFTER = int(os.getenv("NATLAS_SLEEP_MIN", "60"))

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    # EXACT versions (a floating transformers broke the LLM server on 2 Oct). Change only on purpose, then re-test.
    .pip_install("torch==2.8.0", "transformers==4.57.6", "tokenizers==0.22.2", "huggingface_hub==0.36.2",
                 "hf_transfer==0.1.9", "soundfile==0.13.1", "numpy==2.2.6", "fastapi[standard]==0.118.0",
                 "python-multipart==0.0.20", "accelerate==1.10.1")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .add_local_file(PREP, "/root/speech_prep.py")   # light audio prep + word confidence (tested in eval/)
)
hf_cache = modal.Volume.from_name("tradevoice-hf-cache", create_if_missing=True)
app = modal.App("tradevoice-natlas-asr")


@app.cls(image=image, gpu=GPU, cpu=CPU, memory=8192, secrets=[modal.Secret.from_name("natlas")],
         volumes={"/root/.cache/huggingface": hf_cache}, scaledown_window=SLEEP_AFTER * 60, timeout=600)
@modal.concurrent(max_inputs=4)
class ASR:
    @modal.enter()
    def load(self):
        import threading

        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor

        torch.set_num_threads(max(2, int(CPU) // 2))   # two models at once (the "also" model) share the CPUs
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.models = {}
        self.locks = {lang: threading.Lock() for lang in MODELS}   # one note at a time per model, others in parallel
        for lang, repo in MODELS.items():  # all 4 in memory (~1 GB each on CPU): no wait when the language changes
            proc = WhisperProcessor.from_pretrained(repo, token=os.environ.get("HF_TOKEN"))
            model = WhisperForConditionalGeneration.from_pretrained(repo, torch_dtype=dtype,
                                                                    token=os.environ.get("HF_TOKEN"))
            self.models[lang] = (proc, model.to(self.device).eval())

    def _audio(self, data):
        """Any format (WhatsApp .ogg/Opus, m4a, webm, wav) -> 16 kHz mono float32 via ffmpeg. The light prep
        (speech_prep.prepare) comes after the silence check; no denoising (a 2025 study found it made Whisper worse)."""
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
        """-> (text, unsure words, mean token probability). Scores come with the words at no extra cost."""
        with self.locks[lang]:
            return self._run_locked(lang, audio, prompt)

    def _run_locked(self, lang, audio, prompt):
        import torch
        from speech_prep import unsure_words
        proc, model = self.models[lang]
        tok = proc.tokenizer
        texts, pieces = [], []
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
                out = model.generate(feats, return_dict_in_generate=True, output_scores=True, **kw)
            seq = out.sequences[0]
            try:     # the scores belong to the last len(scores) tokens: the words, after the prompt and start tokens
                probs = model.compute_transition_scores(out.sequences, out.scores, normalize_logits=True)[0].exp()
                gen = seq[-len(probs):]
                for i, p in zip(gen.tolist(), probs.tolist()):
                    t = tok.convert_ids_to_tokens(i)
                    if i not in tok.all_special_ids and not t.startswith("<|"):
                        pieces.append((t, p))
                text = tok.decode(gen, skip_special_tokens=True)
            except Exception as e:  # noqa: BLE001 - no scores: the words alone, as before
                print(f"word scores failed: {type(e).__name__}: {e}")
                text = tok.decode(seq, skip_special_tokens=True)
            if prompt and text.strip().startswith(prompt[:40].strip()):
                text = text.strip()[len(prompt[:600].strip()):]  # some versions echo the prompt back
            texts.append(text.strip())
        unsure, mean = unsure_words(pieces, tok.convert_tokens_to_string, UNSURE)
        return " ".join(t for t in texts if t), unsure, mean

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
        def transcribe(file: UploadFile = File(...), lang: str = Form("english"), prompt: str = Form(""),
                       prep: str = Form("1"), also: str = Form(""), authorization: str = Header("")):
            # a plain def: FastAPI runs it in a thread, so one long note doesn't hold up the others
            from concurrent.futures import ThreadPoolExecutor

            from speech_prep import prepare
            if authorization != f"Bearer {os.environ['NATLAS_KEY']}":
                raise HTTPException(401)
            names = {"pidgin": "english", "yo": "yoruba", "ha": "hausa", "ig": "igbo", "en": "english"}
            lang = names.get(lang.lower(), lang.lower())
            also = names.get(also.lower(), also.lower())
            if lang not in self.models or (also and also not in self.models):
                raise HTTPException(400, f"lang must be one of {sorted(self.models)}")
            t = time.perf_counter()
            audio = self._audio(file.file.read())
            seconds = len(audio) / 16000
            if not self._has_speech(audio):   # Whisper invents words on silence (loops, or the hint names)
                return {"text": "", "no_speech": True, "model": MODELS[lang], "seconds": round(seconds, 1),
                        "ms": round((time.perf_counter() - t) * 1000)}
            if prep != "0":
                audio = prepare(audio)
            p = prompt.strip()
            with ThreadPoolExecutor(2) as pool:   # the second model hears the same note at the same time
                first = pool.submit(self._run, lang, audio, p)
                second = pool.submit(self._run, also, audio, p) if also and also != lang else None
                text, unsure, conf = first.result()
                res = {"text": text, "model": MODELS[lang], "seconds": round(seconds, 1), "unsure": unsure,
                       "confidence": conf, "prep": prep != "0"}
                if second:
                    t2, u2, c2 = second.result()
                    res["also"] = {"text": t2, "model": MODELS[also], "unsure": u2, "confidence": c2}
            res["ms"] = round((time.perf_counter() - t) * 1000)
            return res

        return api
