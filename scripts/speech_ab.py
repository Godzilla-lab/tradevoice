"""Before vs after for the speech fixes (ROADMAP Part 5), on real market voice notes: is the AMOUNT and the CUSTOMER
right? (That is what matters to a trader, more than every word.)

    python scripts/speech_ab.py CLIPS_FOLDER [--noise market.wav --snr 10,5,0] [--out results.csv]

CLIPS_FOLDER has the voice notes (any format) and expected.csv with columns:
    file,language,amount,customer          e.g.  note01.ogg,Yoruba,45000,Mama Tunde
language = English / Pidgin / Yoruba / Hausa / Igbo; customer may be empty. Only use notes the speaker agreed to.
--noise mixes a recording of market noise into every note at each signal-to-noise level (dB), to test noise.

Variants (all on the live N-ATLaS hearing server, NATLAS_ASR_URL + NATLAS_KEY from .env):
    raw       the note as it is, one model                  (before)
    prep      light prep (trim + level), one model
    merged    light prep + the English model too, merged by N-ATLaS (Yoruba / Hausa / Igbo only)
The words are turned into a record by the offline rules (src/extract.py), the same for every variant, so only the
hearing differs. The script wakes the N-ATLaS servers (paid minutes).
"""
import argparse
import csv
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import settings  # noqa: E402,F401  (loads .env)

LANG = {"english": "english", "pidgin": "english", "english / pidgin": "english", "yoruba": "yoruba",
        "hausa": "hausa", "igbo": "igbo"}


def _pcm(path):
    import numpy as np
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le",
                          "pipe:1"], capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32)


def noisy(path, noise, snr):
    """The note with market noise mixed in at `snr` dB -> a temporary WAV path."""
    import wave

    import numpy as np
    voice, n = _pcm(path), _pcm(noise)
    n = np.resize(n, len(voice))
    pv, pn = float(np.mean(voice ** 2)) + 1e-12, float(np.mean(n ** 2)) + 1e-12
    mix = voice + n * np.sqrt(pv / (pn * 10 ** (snr / 10)))
    mix = np.clip(mix / max(1.0, float(np.abs(mix).max()) / 0.99), -1, 1)
    fd, out = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((mix * 32767).astype("<i2").tobytes())
    return out


def hear(path, lang, prep, also, vocab):
    import requests

    hints = ", ".join(vocab.get("names", [])[:15] + vocab.get("items", [])[:8])
    with open(path, "rb") as f:
        r = requests.post(os.environ["NATLAS_ASR_URL"].rstrip("/") + "/transcribe",
                          files={"file": (os.path.basename(path), f)},
                          data={"lang": lang, "prompt": hints, "prep": "1" if prep else "0",
                                "also": "english" if also else ""},
                          headers={"Authorization": f"Bearer {os.getenv('NATLAS_KEY', '')}"}, timeout=300)
    r.raise_for_status()
    return r.json()


def score(text, want_amount, want_customer):
    from askbook import same_person
    from extract import parse_amount, rule_extract

    rec = rule_extract(text or "")
    amount = parse_amount(text or "")
    ok_amount = want_amount is not None and amount is not None and abs(float(amount) - want_amount) < 0.5
    got = rec.get("customer") or ""
    ok_customer = (not want_customer and not got) or bool(want_customer and got and (
        same_person(want_customer, got) or same_person(got, want_customer)))
    return ok_amount, ok_customer


def main():
    import hearing

    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--noise")
    ap.add_argument("--snr", default="10,5,0")
    ap.add_argument("--out", default="speech_ab.csv")
    a = ap.parse_args()
    if not os.getenv("NATLAS_ASR_URL"):
        sys.exit("NATLAS_ASR_URL is not set (.env)")
    rows = list(csv.DictReader(open(os.path.join(a.folder, "expected.csv"), encoding="utf-8")))
    names = sorted({r.get("customer") or "" for r in rows} - {""})
    vocab = {"names": names, "items": []}
    levels = [None] + ([float(x) for x in a.snr.split(",")] if a.noise else [])
    results = []
    for r in rows:
        lang = LANG.get((r.get("language") or "english").strip().lower(), "english")
        want_amount = float(r["amount"]) if (r.get("amount") or "").strip() else None
        for snr in levels:
            path = os.path.join(a.folder, r["file"])
            tmp = noisy(path, a.noise, snr) if snr is not None else None
            try:
                variants = [("raw", False, False), ("prep", True, False)] + (
                    [("merged", True, True)] if lang != "english" else [])
                for name, prep, also in variants:
                    out = hear(tmp or path, lang, prep, also, vocab)
                    text = out.get("text") or ""
                    if also and out.get("also"):
                        text, _ = hearing.merge(text, out["also"].get("text"), lang.title(), vocab)
                    ok_a, ok_c = score(text, want_amount, r.get("customer"))
                    results.append({"file": r["file"], "language": lang, "noise_db": "" if snr is None else snr,
                                    "variant": name, "amount_ok": int(ok_a), "customer_ok": int(ok_c),
                                    "words": text})
                    print(f"{r['file']:<20} {lang:<8} {('' if snr is None else f'{snr:g} dB'):<6} {name:<7} "
                          f"amount {'ok ' if ok_a else 'NO '} customer {'ok ' if ok_c else 'NO '} | {text[:60]}")
            finally:
                if tmp:
                    os.remove(tmp)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    print("\nAmount and customer right (before = raw):")
    keys = sorted({(x["language"], x["noise_db"], x["variant"]) for x in results}, key=str)
    for lang, snr, var in keys:
        part = [x for x in results if (x["language"], x["noise_db"], x["variant"]) == (lang, snr, var)]
        am = sum(x["amount_ok"] for x in part)
        cu = sum(x["customer_ok"] for x in part)
        print(f"  {lang:<8} {('quiet' if snr == '' else f'{snr:g} dB'):<7} {var:<7} amount {am}/{len(part)}"
              f"  customer {cu}/{len(part)}")
    print(f"\nEvery note: {a.out} (holds the words heard: keep it private)")


if __name__ == "__main__":
    main()
