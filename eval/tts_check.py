"""Make voice samples in every language for a native-speaker listening test.

python eval/tts_check.py          -> eval/tts_samples/<Language>_<n>.(wav|mp3) + script.txt
python eval/tts_check.py --audition             -> the same sentence in EVERY Spitch voice at speed 0.9 and 1.0
python eval/tts_check.py --audition --lang Pidgin,Yoruba --speeds 0.85,0.95,1.05
   Pick by ear, then put the winners in .env:  TTS_VOICE_PIDGIN=tega  TTS_VOICE_YORUBA=funmi  TTS_SPEED=0.95
Ask a native speaker of each language: "Is it clear? Is anything wrong or rude? Would a trader understand it?"
Score 1-5 per sample in eval/tts_samples/scores.txt, and drop any language that scores below 3 from the demo.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import settings  # noqa: E402,F401  (loads .env)
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

# Spitch voices per language (from the SDK's voice list; which of ufoma/tega/justice/boma suit Pidgin is untested)
AUDITION = {"Pidgin": ["ufoma", "tega", "justice", "boma", "kingsley", "remi"],
            "English": ["lucy", "lina", "john", "jude", "henry", "kani", "remi", "kingsley"],
            "Yoruba": ["sade", "funmi", "segun", "femi"], "Hausa": ["amina", "zainab", "aliyu", "hasan"],
            "Igbo": ["ngozi", "amara", "obinna", "ebuka"]}


def audition(langs, speeds):
    import random

    out = os.path.join(OUT, "audition")
    os.makedirs(out, exist_ok=True)
    rec = {"type": "credit_sale", "amount": 45000, "customer": "Mama Tunde", "due_date": "2026-10-02"}
    rows = []
    for lang in langs:
        text = tts.confirmation_text(rec, lang, balance=66600, rng=random.Random(0))
        print(f"\n{lang}: {text}")
        for voice in AUDITION[lang]:
            for sp in speeds:
                try:
                    res = tts.speak(text, lang, voice=voice, speed=sp)
                    dest = os.path.join(out, f"{lang}_{voice}_{sp}{os.path.splitext(res['path'])[1]}")
                    shutil.move(res["path"], dest)
                    print(f"  ✅ {os.path.basename(dest)}")
                    rows.append(os.path.basename(dest))
                except Exception as e:  # noqa: BLE001
                    print(f"  ❌ {lang} {voice} {sp}: {type(e).__name__}: {str(e)[:70]}")
                    break  # this voice doesn't work for this language: skip its other speeds
    with open(os.path.join(out, "picks.txt"), "w", encoding="utf-8") as f:
        f.write("# Which sounds most like a real, friendly Nigerian? Score 1-5 (5 = I'd trust it with my money)\n"
                "# sample | warm/friendly | natural speed | clear | notes\n")
        f.writelines(f"{r} |  |  |  | \n" for r in rows)
    print(f"\nListen in {out} and score them in picks.txt. Put the winners in .env (see the top of this file).")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--audition", action="store_true")
    ap.add_argument("--lang", default=",".join(AUDITION))
    ap.add_argument("--speeds", default="0.9,1.0")
    args = ap.parse_args()
    if tts.backend() != "spitch" and args.audition:
        raise SystemExit("Audition needs Spitch: SPITCH_API_KEY in .env and pip install spitch")
    if args.audition:
        audition(args.lang.split(","), [float(x) for x in args.speeds.split(",")])
        raise SystemExit
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
