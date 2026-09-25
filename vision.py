"""Photo of a notebook page / receipt -> plain text lines, one money event per line.

Default: a vision model on build.nvidia.com. To self-host on the Brev GPU instead, serve an open vision model with
vLLM (OpenAI-compatible) and point VISION_BASE_URL / VISION_MODELS at it — see README.
"""
import base64
import io
import os
import time

import llm

# NVIDIA-hosted endpoints only accept small inline images, so we shrink until the base64 fits.
MAX_B64_BYTES = int(os.getenv("VISION_MAX_B64_BYTES", "175000"))

PROMPT = """This is a photo of a Nigerian market trader's handwritten record book page or a receipt.
It may be written in English, Nigerian Pidgin, Yoruba, Hausa or Igbo, or a mix.
For every money record, output ONE line in this format:
<the line copied EXACTLY as written, keeping every letter, tone mark and number> => <short English meaning>
If the line is already in English, just copy it without "=>".
In the English meaning say clearly if it is a sale, a sale on credit (someone owes / "credit" / "bal" / gbèsè / bashi / ụgwọ),
money paid back, or an expense, and keep amounts as digits and names exactly as written.
If a word or number is unreadable write [?].
Examples:
Sold 3 bags rice to Mama Tunde 45000 cr, pay Friday
Iya Bisi ti san 12000 => Iya Bisi paid back 12000
Na biya 3500 kudin mota => Expense: transport 3500
Output ONLY the lines, nothing else. If there are no money records, output NONE."""

# Used by eval/lang_check.py to measure how exactly a model copies text (letters + tone marks).
COPY_PROMPT = ("Copy the text in this image EXACTLY, character for character, keeping every tone mark and "
               "diacritic (e.g. ẹ ọ ṣ à é ị ụ ṅ). Output only the text.")


def encode_image(path):
    """Downscale + JPEG-compress until the base64 payload is small enough. Returns base64 str."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    side, quality = 1024, 80
    while True:
        im = img.copy()
        im.thumbnail((side, side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode()
        if len(b64) <= MAX_B64_BYTES or side <= 640:
            return b64
        side, quality = int(side * 0.8), max(quality - 10, 50)


def read_notebook(path):
    """Return {text, latency_ms, engine}. Raises if no vision API is configured."""
    if not (os.getenv("VISION_API_KEY") or os.getenv("NVIDIA_API_KEY")):
        raise RuntimeError("Photo reading needs NVIDIA_API_KEY (or VISION_API_KEY + VISION_BASE_URL).")
    start = time.perf_counter()
    b64 = encode_image(path)
    text, model = llm.chat([{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
    ]}], kind="vision", max_tokens=1000, timeout=int(os.getenv("VISION_TIMEOUT", "45")))
    if text.upper() == "NONE":
        text = ""
    return {"text": text, "latency_ms": round((time.perf_counter() - start) * 1000), "engine": f"vision:{model}"}
