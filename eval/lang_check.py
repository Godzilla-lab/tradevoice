"""Which NVIDIA models handle Yoruba, Hausa, Igbo and Pidgin best? Run with your key and compare.

NVIDIA_API_KEY=nvapi-... python eval/lang_check.py                 # text + rendered-image tests
NVIDIA_API_KEY=nvapi-... python eval/lang_check.py --text-only
NVIDIA_API_KEY=nvapi-... python eval/lang_check.py --models google/gemma-3-27b-it,meta/llama-4-maverick-17b-128e-instruct
Real handwriting: put eval/photos/<name>.jpg + eval/photos/<name>.txt (what is really written) and it scores them too.

TEXT test   : each model turns eval/cases_lang.jsonl phrases into entries -> % with type+amount+customer all right.
IMAGE test  : each phrase is drawn as an image; each vision model copies it ->
              letters  = how close the copy is ignoring tone marks, tones = how close including tone marks,
              amount   = amount still read correctly from the copy.
"""
import argparse
import difflib
import glob
import json
import os
import sys
import tempfile
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import llm  # noqa: E402
from extract import SYSTEM_PROMPT, _normalise, _parse_json, fold, parse_amount  # noqa: E402
from vision import COPY_PROMPT, encode_image  # noqa: E402

HERE = os.path.dirname(__file__)
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial Unicode.ttf",
         "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "C:/Windows/Fonts/segoeui.ttf",
         "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "DejaVuSans.ttf"]


def norm(v):
    return " ".join(str(v).lower().split()) if v is not None else None


def sim(a, b):
    return difflib.SequenceMatcher(None, a.strip(), b.strip()).ratio()


def font():
    from PIL import ImageFont

    for f in FONTS:
        try:
            return ImageFont.truetype(f, 34)
        except OSError:
            continue
    print("⚠️ No Unicode font found: tone marks may not render. Install DejaVu/Noto Sans or use real photos.")
    return ImageFont.load_default()


def render(text, fnt, path):
    from PIL import Image, ImageDraw

    words, lines, cur = text.split(), [], ""
    for w in words:  # wrap at ~40 chars
        if len(cur) + len(w) > 40:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    img = Image.new("RGB", (900, 60 + 52 * len(lines)), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((30, 30 + 52 * i), line, fill="black", font=fnt)
    img.save(path, quality=92)


def table(title, results, cols):
    langs = sorted({lang for m in results for lang in results[m]})
    print(f"\n{title}")
    print(f"{'model':<48}" + "".join(f"{lang:>18}" for lang in langs))
    for m, per in results.items():
        row = f"{m:<48}"
        for lang in langs:
            r = per.get(lang)
            row += f"{'ERROR' if r is None else ' / '.join(c(r) for c in cols):>18}"
        print(row)


def text_test(models, cases):
    results = defaultdict(dict)
    for m in models:
        per = defaultdict(lambda: [0, 0])
        for c in cases:
            try:
                prompt = SYSTEM_PROMPT.replace("__TODAY__", "2026-09-27").replace("__WEEKDAY__", "Sunday")
                out, _ = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": c["text"]}],
                                  models=[m], max_tokens=400, timeout=60)
                rec = _normalise(_parse_json(out), c["text"], __import__("datetime").date(2026, 9, 27))
                ok = all(norm(rec.get(f)) == norm(c[f]) for f in ("type", "amount", "customer"))
            except Exception as e:  # noqa: BLE001
                print(f"  {m} {c['id']}: {type(e).__name__}: {str(e)[:80]}")
                ok = False
            per[c["lang"]][0] += ok
            per[c["lang"]][1] += 1
        results[m] = {lang: v for lang, v in per.items()}
        print(f"  done {m}")
    table("TEXT: entries fully correct (type + amount + customer)", results, [lambda r: f"{r[0]}/{r[1]}"])


def image_test(models, items):
    """items: list of (lang, truth_text, image_path)."""
    results = defaultdict(dict)
    for m in models:
        per = defaultdict(lambda: {"letters": [], "tones": [], "amount": [0, 0]})
        for lang, truth, path in items:
            b64 = encode_image(path)
            try:
                out, _ = llm.chat([{"role": "user", "content": [
                    {"type": "text", "text": COPY_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
                    kind="vision", models=[m], max_tokens=600, timeout=90)
            except Exception as e:  # noqa: BLE001
                print(f"  {m} {os.path.basename(path)}: {type(e).__name__}: {str(e)[:80]}")
                out = ""
            p = per[lang]
            p["letters"].append(sim(fold(out), fold(truth)))
            p["tones"].append(sim(out.lower(), truth.lower()))
            p["amount"][0] += parse_amount(out) == parse_amount(truth)
            p["amount"][1] += 1
        results[m] = dict(per)
        print(f"  done {m}")

    def pct(key):
        return lambda r: f"{100 * sum(r[key]) / max(len(r[key]), 1):.0f}%"

    table("IMAGE: letters% / tones% / amounts right", results,
          [pct("letters"), pct("tones"), lambda r: f"{r['amount'][0]}/{r['amount'][1]}"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", help="comma-separated text models (default: LLM_MODELS)")
    ap.add_argument("--vision-models", help="comma-separated vision models (default: VISION_MODELS)")
    ap.add_argument("--cases", default=os.path.join(HERE, "cases_lang.jsonl"))
    ap.add_argument("--text-only", action="store_true")
    ap.add_argument("--images-only", action="store_true")
    args = ap.parse_args()
    if not os.getenv("NVIDIA_API_KEY"):
        raise SystemExit("Set NVIDIA_API_KEY first.")
    cases = [json.loads(line) for line in open(args.cases, encoding="utf-8") if line.strip()]
    text_models = args.models.split(",") if args.models else llm.LLM_MODELS
    vision_models = args.vision_models.split(",") if args.vision_models else llm.VISION_MODELS

    if not args.images_only:
        text_test(text_models, cases)
    if not args.text_only:
        tmp = tempfile.mkdtemp()
        fnt = font()
        items = []
        for c in cases:
            path = os.path.join(tmp, c["id"] + ".jpg")
            render(c["text"], fnt, path)
            items.append((c["lang"], c["text"], path))
        for img in sorted(glob.glob(os.path.join(HERE, "photos", "*.jp*g")) + glob.glob(os.path.join(HERE, "photos", "*.png"))):
            truth = os.path.splitext(img)[0] + ".txt"
            if os.path.exists(truth):
                items.append(("PHOTO " + os.path.basename(img).split("_")[0],
                              open(truth, encoding="utf-8").read(), img))
        image_test(vision_models, items)
    print("\nPut the best models first in LLM_MODELS / VISION_MODELS (.env). Phrases were written by a non-native "
          "speaker; have a native speaker check eval/cases_lang.jsonl.")


if __name__ == "__main__":
    main()
