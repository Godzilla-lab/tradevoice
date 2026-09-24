"""Check which NVIDIA API models work with your key BEFORE the event.

NVIDIA_API_KEY=nvapi-... python check_models.py
Put the working ones first in LLM_MODELS / VISION_MODELS in your .env.
"""
import base64
import io
import os
import time

from openai import OpenAI
from PIL import Image, ImageDraw

import llm

if not os.getenv("NVIDIA_API_KEY"):
    raise SystemExit("Set NVIDIA_API_KEY first (from build.nvidia.com).")

client = OpenAI(base_url=llm.NVIDIA_BASE_URL, api_key=os.environ["NVIDIA_API_KEY"], timeout=60, max_retries=0)

img = Image.new("RGB", (600, 200), "white")
ImageDraw.Draw(img).text((20, 80), "Mama Tunde rice 45000 credit", fill="black")
buf = io.BytesIO()
img.save(buf, format="JPEG")
IMAGE = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def try_model(model, content):
    start = time.perf_counter()
    try:
        r = client.chat.completions.create(model=model, messages=[{"role": "user", "content": content}],
                                           max_tokens=200, temperature=0)
        out = llm.clean(r.choices[0].message.content).replace("\n", " ")[:70]
        return f"✅ {model:<45} {time.perf_counter() - start:5.1f}s  {out!r}"
    except Exception as e:  # noqa: BLE001
        return f"❌ {model:<45} {type(e).__name__}: {str(e)[:90]}"


try:
    live = {m.id for m in client.models.list().data}
    print(f"Your key sees {len(live)} models. Ours:")
    for m in dict.fromkeys(llm.LLM_MODELS + llm.VISION_MODELS):
        print(f"  {'listed ' if m in live else 'MISSING'}  {m}")
except Exception as e:  # noqa: BLE001
    print(f"Could not list models ({type(e).__name__}); testing directly.")

print("Text models (LLM_MODELS):")
for m in llm.LLM_MODELS:
    print(" ", try_model(m, 'Reply with only this JSON: {"ok": true}'))
print("Vision models (VISION_MODELS):")
for m in llm.VISION_MODELS:
    print(" ", try_model(m, [{"type": "text", "text": "Copy the text in this image."},
                             {"type": "image_url", "image_url": {"url": IMAGE}}]))
