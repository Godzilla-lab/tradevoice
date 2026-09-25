"""Make voice samples in every language for a native-speaker listening test.

python eval/tts_check.py          -> eval/tts_samples/<Language>_<n>.(wav|mp3) + script.txt
Ask a native speaker of each language: "Is it clear? Is anything wrong or rude? Would a trader understand it?"
Score 1-5 per sample in eval/tts_samples/scores.txt, and drop any language that scores below 3 from the demo.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tts  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "tts_samples")
ENTRIES = [
    ({"type": "credit_sale", "amount": 45000, "customer": "Mama Tunde", "due_date": "2026-10-02", "item": "rice"},
     False, None),
    ({"type": "credit_sale", "amount": 45000, "customer": "Mama Tunde", "due_date": "2026-10-02", "item": "rice"},
     True, 66600),
    ({"type": "payment_received", "amount": 12000, "customer": "Iya Bisi"}, True, 18000),
    ({"type": "sale", "amount": 18500, "item": "indomie"}, True, None),
    ({"type": "expense", "amount": 3500, "item": "transport"}, True, None),
]

if __name__ == "__main__":
    engine = tts.backend()
    if not engine:
        raise SystemExit("No voice engine: add SPITCH_API_KEY to .env (pip install spitch), or pip install -r requirements-tts.txt")
    os.makedirs(OUT, exist_ok=True)
    script = []
    for lang in tts.REPLY_LANGS:
        for i, (rec, saved, bal) in enumerate(ENTRIES, 1):
            text = tts.confirmation_text(rec, lang, balance=bal, saved=saved)
            try:
                res = tts.speak(text, lang)
                dest = os.path.join(OUT, f"{lang}_{i}{os.path.splitext(res['path'])[1]}")
                shutil.move(res["path"], dest)
                line = f"{os.path.basename(dest)}\t{res['engine']}\t{text}"
            except Exception as e:  # noqa: BLE001
                line = f"{lang}_{i}\tFAILED {type(e).__name__}: {str(e)[:80]}\t{text}"
            print(line)
            script.append(line)
    with open(os.path.join(OUT, "script.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(script) + "\n")
    scores = os.path.join(OUT, "scores.txt")
    if not os.path.exists(scores):  # a form to fill in, one line per sample; never overwrite real scores
        with open(scores, "w", encoding="utf-8") as f:
            f.write("# Play each sample to a NATIVE speaker (not the person who wrote it). Score 1-5:\n"
                    "#   clear = could you understand every word?   natural = does it sound like a real person?\n"
                    "#   amount = did you hear the right naira amount? (y/n)   fix = better wording, anything rude\n"
                    "# sample | listener (first name) | clear | natural | amount | fix\n")
            for line in script:
                f.write(f"{line.split(chr(9))[0]} |  |  |  |  | \n")
    print(f"\nSamples in {OUT}. Play them to native speakers and fill in {scores}.")
