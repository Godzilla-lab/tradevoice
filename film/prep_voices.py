"""The voice clips for the film: downloads what film/voices.sh made on the server, picks one take per line, trims
the silence, and measures each clip's loudness 60 times a second (the orb follows it). Writes film/voices/chosen.json,
which render.cjs puts into the film (shot lengths follow the real clip lengths) and sound.py mixes.
Run: python film/prep_voices.py                    (download, then choose)
     python film/prep_voices.py --no-download      (choose again from what is already here)
Picks: the four main voices at speed 1.0 (lucy, sade, amina, ngozi; English lines in lucy), unless
film/voices/picks.json says otherwise, e.g. {"yo_ask": "funmi__0.92", "four_ha": "zainab__1"}.
"""
import json
import os
import subprocess
import sys
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
VO = os.path.join(HERE, "voices")
RAW = os.path.join(VO, "raw")
BASE = os.getenv("FILM_VOICES_URL", "https://tradevoice.duckdns.org/static/film-voices/")
MAIN = {"en": "lucy", "yo": "sade", "ha": "amina", "ig": "ngozi", "pcm": "ufoma"}
SR = 48000
FPS = 60


def download():
    os.makedirs(RAW, exist_ok=True)
    with urllib.request.urlopen(BASE + "index.json", timeout=30) as r:
        index = json.load(r)
    for c in index["clips"]:
        dst = os.path.join(RAW, c["file"])
        if not os.path.exists(dst):
            urllib.request.urlretrieve(BASE + c["file"], dst)
    json.dump(index, open(os.path.join(RAW, "index.json"), "w"), indent=1)
    print(f"{len(index['clips'])} clips downloaded ({len(index.get('failed', []))} had failed on the server)")
    return index


def clipped(path):
    import wave
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return int((np.abs(x.astype(np.int32)) >= 32700).sum())


def load(path):
    # some takes come from Spitch with clipped peaks (sade: up to 88 samples): ffmpeg's declipper rebuilds them
    fix = ["-af", "adeclip"] if clipped(path) else []
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, *fix, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def trim(x, db=-42, pad=0.03):
    a = np.abs(x)
    win = int(0.01 * SR)
    lvl = np.sqrt(np.convolve(a ** 2, np.ones(win) / win, mode="same"))
    on = np.where(lvl > 10 ** (db / 20))[0]
    if not len(on):
        return x
    i0 = max(0, on[0] - int(pad * SR))
    i1 = min(len(x), on[-1] + int(pad * SR))
    return x[i0:i1]


def envelope(x):
    hop = SR // FPS
    out = []
    for i in range(0, len(x), hop):
        r = np.sqrt(np.mean(x[i:i + hop] ** 2) + 1e-12)
        out.append(float(np.clip((20 * np.log10(r) + 50) / 38, 0, 1)))
    # a touch of smoothing so the orb breathes rather than flickers
    k = np.array([0.25, 0.5, 0.25])
    sm = np.convolve(out, k, mode="same")
    return [round(float(v), 3) for v in sm]


def main():
    index = download() if "--no-download" not in sys.argv else json.load(open(os.path.join(RAW, "index.json")))
    lines = {ln["id"]: ln for ln in json.load(open(os.path.join(HERE, "lines.json"), encoding="utf-8"))["lines"]}
    picks = {}
    pf = os.path.join(VO, "picks.json")
    if os.path.exists(pf):
        picks = json.load(open(pf))
    have = {c["file"] for c in index["clips"]}
    chosen = {}
    for lid, ln in lines.items():
        code = {"English": "en", "Yoruba": "yo", "Hausa": "ha", "Igbo": "ig", "Pidgin": "pcm"}[ln["language"]]
        want = picks.get(lid) or f"{MAIN[code]}__1"
        f = f"{lid}__{want}.wav"
        if f not in have:   # fall back to any take of this line
            alts = sorted(c for c in have if c.startswith(lid + "__"))
            if not alts:
                print("no clip for", lid)
                continue
            f = alts[0]
        x = trim(load(os.path.join(RAW, f)))
        out = os.path.join(VO, lid + ".wav")
        x = x / max(1.0, np.abs(x).max() / 0.89)     # headroom after the repair (sound.py sets the level)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(SR), "-ac", "1", "-i", "-", out],
                       input=x.astype("<f8").tobytes(), check=True)
        chosen[lid] = {"file": lid + ".wav", "take": f, "dur": round(len(x) / SR, 3), "env": envelope(x)}
        print(f"{lid:<10} {f:<28} {len(x) / SR:5.2f} s")
    json.dump(chosen, open(os.path.join(VO, "chosen.json"), "w"))
    print("chosen.json written")


if __name__ == "__main__":
    main()
