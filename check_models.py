"""Check which NVIDIA API models work with your key BEFORE the event.

python check_models.py            # test our configured LLM_MODELS / VISION_MODELS
python check_models.py --search   # ask NVIDIA which models exist, try the likely ones, print what works
python check_models.py --search gemma,qwen,llama   # only models whose id contains these words

Put the working ones first in LLM_MODELS / VISION_MODELS in your .env (search mode prints the lines).
"""
import argparse
import base64
import io
import os
import time

from openai import OpenAI
from PIL import Image, ImageDraw

import llm

# Families worth trying for our job (chat + JSON; vision for photos). Skips embedding/reward/guard/etc. models.
DEFAULT_SEARCH = "gemma,qwen,llama,nemotron,mistral,mixtral,phi,deepseek,gpt-oss,kimi,glm"
SKIP_WORDS = ("embed", "rerank", "reward", "guard", "safety", "retriever", "parse", "ocr", "clip", "nv-", "bge",
              "coder", "math", "audio", "tts", "asr", "whisper", "translate", "base", "fuyu", "detector")
VISION_HINTS = ("vision", "-vl", "vlm", "gemma-3", "gemma-4", "llama-4", "multimodal", "mistral-small", "pixtral",
                "kimi-k2.5", "qwen3.5", "qwen3.6", "phi-4-multimodal", "nemotron-nano-12b", "cosmos")

if not os.getenv("NVIDIA_API_KEY"):
    raise SystemExit("Set NVIDIA_API_KEY first (from build.nvidia.com), e.g.  set -a; source .env; set +a")

client = OpenAI(base_url=llm.NVIDIA_BASE_URL, api_key=os.environ["NVIDIA_API_KEY"], timeout=60, max_retries=0)

img = Image.new("RGB", (600, 200), "white")
ImageDraw.Draw(img).text((20, 80), "Mama Tunde rice 45000 credit", fill="black")
buf = io.BytesIO()
img.save(buf, format="JPEG")
IMAGE = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
TEXT_Q = 'Reply with only this JSON: {"ok": true}'
IMAGE_Q = [{"type": "text", "text": "Copy the text in this image."}, {"type": "image_url", "image_url": {"url": IMAGE}}]


def try_model(model, content, max_tokens=200):
    """Return (ok, line)."""
    start = time.perf_counter()
    try:
        r = client.chat.completions.create(model=model, messages=[{"role": "user", "content": content}],
                                           max_tokens=max_tokens, temperature=0)
        out = llm.clean(r.choices[0].message.content or "").replace("\n", " ")[:60]
        return True, f"✅ {model:<48} {time.perf_counter() - start:5.1f}s  {out!r}"
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "status_code", "")
        why = {403: "no access for this key", 404: "not found", 410: "removed by NVIDIA",
               429: "rate limited (try again)"}.get(code, str(e)[:70])
        return False, f"❌ {model:<48} {code} {why}"


def list_live():
    try:
        return sorted(m.id for m in client.models.list().data)
    except Exception as e:  # noqa: BLE001
        print(f"Could not list models ({type(e).__name__}: {str(e)[:80]})")
        return []


def check_configured():
    live = set(list_live())
    if live:
        print(f"Your key sees {len(live)} models. Ours:")
        for m in dict.fromkeys(llm.LLM_MODELS + llm.VISION_MODELS):
            print(f"  {'listed ' if m in live else 'MISSING'}  {m}")
    print("Text models (LLM_MODELS):")
    for m in llm.LLM_MODELS:
        print(" ", try_model(m, TEXT_Q)[1])
    print("Vision models (VISION_MODELS):")
    for m in llm.VISION_MODELS:
        print(" ", try_model(m, IMAGE_Q)[1])
    print("\nNothing works? Run:  python check_models.py --search")


def search(words):
    live = list_live()
    cands = [m for m in live if any(w in m.lower() for w in words) and not any(s in m.lower() for s in SKIP_WORDS)]
    print(f"NVIDIA lists {len(live)} models; trying {len(cands)} likely chat models (about 2 s each)...\n")
    text_ok, vision_ok = [], []
    for m in cands:
        ok, line = try_model(m, TEXT_Q, max_tokens=60)
        print(" ", line)
        if ok:
            text_ok.append(m)
            if any(h in m.lower() for h in VISION_HINTS):
                vok, vline = try_model(m, IMAGE_Q, max_tokens=60)
                print("    photo:", vline)
                if vok:
                    vision_ok.append(m)
        time.sleep(1.5)  # stay under the free-tier rate limit
    print("\n==== Working models ====")
    print("Text  :", ", ".join(text_ok) or "none")
    print("Vision:", ", ".join(vision_ok) or "none")
    if text_ok or vision_ok:
        # prefer families known to be stronger for Nigerian languages (see docs/RESEARCH.md)
        rank = ("gemma", "qwen", "nemotron", "llama", "mistral", "deepseek", "gpt-oss")

        def order(ms):
            return sorted(ms, key=lambda m: next((i for i, f in enumerate(rank) if f in m), len(rank)))

        print("\nPaste these two lines into your .env (then run  set -a; source .env; set +a):")
        print("LLM_MODELS=" + ",".join(order(text_ok)[:4]))
        print("VISION_MODELS=" + ",".join(order(vision_ok)[:3]))
    else:
        print("\nNo model worked. Check the key is active on build.nvidia.com (log in, open a model page, "
              "try it in the browser), or create a new key.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", nargs="?", const=DEFAULT_SEARCH, help="comma-separated words to match model ids")
    args = ap.parse_args()
    if args.search:
        search([w.strip().lower() for w in args.search.split(",") if w.strip()])
    else:
        check_configured()
