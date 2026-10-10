"""The film's sound, edited to picture: original amapiano music made here (112 BPM, in bars with the shots), the
product's sounds (taps, ticks, sheets, the save chime), real foley and a real West African market recording, the
voices (Spitch clips chosen by prep_voices.py), the music ducked under every voice, then loudness to YouTube's
-14 LUFS. Reads film/out/film.json (render.cjs --info writes it: shots, cues, duration). Writes film/out/mix.wav.
Run: python film/sound.py            (python film/sound.py --stems also writes each bus, to check by ear)
"""
import json
import os
import re
import subprocess
import sys
import wave

import numpy as np
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
ASSETS = os.path.join(HERE, "assets")
SR = 48000
BPM = 112
BEAT = 60 / BPM
BAR = 4 * BEAT
S16 = BEAT / 4
RNG = np.random.default_rng(112)

film = json.load(open(os.path.join(OUT, "film.json")))
DUR = film["duration"] + 0.6
N = int(DUR * SR)


def buf(ch=2):
    return np.zeros((N, ch), dtype=np.float64)


def add(dst, x, t, gain=1.0, pan=0.0):
    """x: mono or stereo; placed at t seconds with equal-power pan."""
    i = int(round(t * SR))
    if i >= N or len(x) == 0:
        return
    if i < 0:
        x, i = x[-i:], 0
    x = x[: N - i]
    if x.ndim == 1:
        a = (pan + 1) * np.pi / 4
        dst[i:i + len(x), 0] += x * gain * np.cos(a)
        dst[i:i + len(x), 1] += x * gain * np.sin(a)
    else:
        dst[i:i + len(x)] += x * gain


def tsec(sec):
    return np.arange(int(sec * SR)) / SR


def sos(kind, f, order=2):
    return signal.butter(order, f, btype=kind, fs=SR, output="sos")


def filt(x, kind, f, order=2):
    return signal.sosfilt(sos(kind, f, order), x, axis=0)


def peaking(x, f0, gain_db, q=1.0):
    a = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / SR
    al = np.sin(w) / (2 * q)
    b = [1 + al * a, -2 * np.cos(w), 1 - al * a]
    aa = [1 + al / a, -2 * np.cos(w), 1 - al / a]
    return signal.lfilter(b, aa, x, axis=0)


def noise(sec):
    return RNG.standard_normal(int(sec * SR))


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def ir(seconds, predelay=0.012, damp=6000, seed=1):
    """A room: exponentially decaying noise (Moorer), darker as it decays; stereo (two seeds)."""
    r = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    env = np.exp(-6.908 * t / seconds)
    outs = []
    for k in range(2):
        x = r.standard_normal(n) * env
        lo = filt(x, "lowpass", damp)
        mix = np.clip(t / seconds, 0, 1)
        x = x * (1 - mix) + lo * mix
        x = np.concatenate([np.zeros(int(predelay * SR)), x])
        outs.append(x / np.sqrt(np.sum(x ** 2)))
    m = max(len(o) for o in outs)
    return np.stack([np.pad(o, (0, m - len(o))) for o in outs], axis=1)


def reverb(x, room, wet=0.2):
    """x stereo -> x with a convolution room added."""
    y = np.stack([signal.fftconvolve(x[:, c], room[:, c])[: len(x)] for c in range(2)], axis=1)
    return x + y * wet


def read_audio(path):
    """Any file ffmpeg reads -> float stereo at 48 kHz."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).astype(np.float64)


# ================================================================ instruments
def kick():
    t = tsec(0.45)
    f = 46 + 90 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t / 0.22)
    x[: int(0.004 * SR)] += filt(noise(0.004), "highpass", 2000) * 0.3
    return np.tanh(x * 1.6) * 0.8


def log_drum(f0, prev=None, length=0.42):
    """The amapiano log drum: FM with a fast-decaying index (the wooden 'pock'), a pitch drop of 10 semitones into the
    note, glide from the previous note, gentle saturation."""
    t = tsec(length)
    start = prev if prev else f0 * 2 ** (10 / 12)
    glide = 0.035 if prev else 0.03
    f = f0 + (start - f0) * np.exp(-t / glide)
    ph = 2 * np.pi * np.cumsum(f) / SR
    idx = 0.4 + 3.2 * np.exp(-t / 0.018)
    mod = np.sin(2 * ph) * idx
    x = np.sin(ph + mod) * np.exp(-t / 0.16)
    x += 0.35 * np.sin(ph) * np.exp(-t / 0.3)
    return np.tanh(x * 2.2) * 0.55


def shaker(v=1.0):
    x = filt(noise(0.06), "highpass", 6500) * np.exp(-tsec(0.06) / 0.012)
    return x * 0.5 * v


def open_hat():
    x = filt(noise(0.16), "highpass", 8000) * np.exp(-tsec(0.16) / 0.05)
    return x * 0.35


def clap():
    x = np.zeros(int(0.25 * SR))
    for k, d in enumerate((0, 0.009, 0.018)):
        b = noise(0.012) * np.exp(-tsec(0.012) / 0.004)
        i = int(d * SR)
        x[i:i + len(b)] += b * (0.7 if k < 2 else 1)
    tail = noise(0.22) * np.exp(-tsec(0.22) / 0.06)
    x[int(0.025 * SR):int(0.025 * SR) + len(tail)] += tail * 0.6
    return filt(x, "bandpass", [900, 2600]) * 0.9


def conga(f=210):
    t = tsec(0.25)
    ff = f * (1 + 0.25 * np.exp(-t / 0.01))
    x = np.sin(2 * np.pi * np.cumsum(ff) / SR) * np.exp(-t / 0.08)
    x[: int(0.005 * SR)] += filt(noise(0.005), "bandpass", [1500, 4000]) * 0.4
    return x * 0.6


def rim():
    t = tsec(0.05)
    return (np.sin(2 * np.pi * 1750 * t) * 0.6 + filt(noise(0.05), "bandpass", [2000, 5000]) * 0.4) * np.exp(-t / 0.01)


def epiano(notes, length=0.5):
    """Rhodes-like stab: sine pairs with a fast bell partial."""
    t = tsec(length)
    x = np.zeros(len(t))
    for n in notes:
        f = midi(n)
        x += np.sin(2 * np.pi * f * t + 0.9 * np.sin(2 * np.pi * f * t) * np.exp(-t / 0.05))
        x += 0.18 * np.sin(2 * np.pi * f * 7.0 * t) * np.exp(-t / 0.02)
    return x * np.exp(-t / 0.18) * (1 - np.exp(-t / 0.003)) / len(notes)


def pad(notes, length):
    t = tsec(length)
    L = np.zeros(len(t))
    R = np.zeros(len(t))
    for n in notes:
        for d, side in ((-7, 0), (0, 2), (7, 1)):
            f = midi(n) * 2 ** (d / 1200)
            ph = RNG.uniform(0, 1)
            saw = 2 * ((f * t + ph) % 1) - 1
            if side in (0, 2):
                L += saw
            if side in (1, 2):
                R += saw
    att = 1 - np.exp(-t / 0.35)
    rel = np.clip((length - t) / 0.5, 0, 1)
    x = np.stack([L, R], axis=1) * (att * rel)[:, None] / (len(notes) * 2)
    return filt(x, "lowpass", 1500, 4)


def kalimba(n, length=1.2):
    t = tsec(length)
    f = midi(n)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.45) + 0.5 * np.sin(2 * np.pi * f * 5.93 * t) * np.exp(-t / 0.04)
    return x * (1 - np.exp(-t / 0.002)) * 0.5


# ================================================================ the arrangement, bar by bar, from the shots
CHORDS = [  # Cm9, F9, Bbmaj9, Gm7 (Roland's amapiano progression, without the turnaround)
    ([63, 67, 70, 74], 36), ([57, 63, 67, 72], 41), ([62, 65, 69, 72], 34), ([62, 65, 67, 70], 43)]
LOG_A = [(3, 0), (6, 0), (10, 7), (11, 12), (14, 0)]          # (16th step, semitones above the root)
LOG_B = [(2, 0), (7, 12), (10, 7), (13, 0), (15, -2)]
KAL_A = [(0, 79), (3, 82), (6, 84), (10, 79), (12, 77)]
KAL_B = [(0, 75), (4, 77), (6, 79), (9, 70), (12, 72)]
MODES = {   # what plays in each shot
    "open": {"pad": 0.55},
    "notebook": {"pad": 0.7, "kal": 0.8, "shaker": 0.5, "rim": 0.6},
    "logo": {"all": 1},
    "speak": {"all": 0.9},
    "voices": {"pad": 0.8, "log": 0.9, "shaker": 0.7, "conga": 0.6, "kal": 0.5},
    "sums": {"all": 1}, "send": {"all": 1}, "pages": {"all": 1},
    "natlas": {"pad": 1.0, "log": 0.8, "kal": 0.6},
    "end": {"all": 1},
}
ALL = ("kick", "log", "shaker", "hat", "clap", "conga", "rim", "stabs", "pad", "kal")


def shot_at(t):
    for s in film["shots"]:
        if s["start"] - 1e-6 <= t < s["end"] - 1e-6:
            return s
    return film["shots"][-1]


def music():
    bus = {k: buf() for k in ALL}
    nbars = int(round(film["duration"] / BAR))
    end = next(s for s in film["shots"] if s["id"] == "end")
    end_bar = int(round(end["start"] / BAR))
    K = kick()
    prev_f = None
    for b in range(nbars):
        t0 = b * BAR
        s = shot_at(t0 + 0.01)
        mode = dict(MODES.get(s["id"], {}))
        if b >= end_bar + 1:    # the end card: one bar of groove, then only pad and kalimba
            mode = {"pad": 0.8, "kal": 0.7}
        lvl = lambda k: mode.get("all", mode.get(k, 0))   # noqa: E731
        notes, root = CHORDS[b % 4]
        sw = lambda step: t0 + step * S16 + (0.06 * 2 * S16 if step % 2 else 0)   # noqa: E731  56% swing
        if lvl("pad"):
            add(bus["pad"], pad(notes, BAR + 0.5), t0, 0.5 * lvl("pad"))
        if lvl("kick"):
            for st in (0, 4, 8, 12):
                add(bus["kick"], K, sw(st), 0.9 * lvl("kick"))
        if lvl("log"):
            for st, semi in (LOG_A if b % 2 == 0 else LOG_B):
                f = midi(root + 12 + semi)
                add(bus["log"], log_drum(f, prev_f), sw(st), 0.75 * lvl("log"))
                prev_f = f
        if lvl("shaker"):
            for st in range(16):
                v = (0.55, 0.28, 0.4, 0.28)[st % 4] * RNG.uniform(0.8, 1.15)
                if RNG.uniform() < 0.06:
                    continue
                add(bus["shaker"], shaker(v), sw(st) + RNG.uniform(-0.003, 0.003), 0.5 * lvl("shaker"), pan=0.35)
        if lvl("hat"):
            for st in (2, 6, 10, 14):
                add(bus["hat"], open_hat(), sw(st), 0.45 * lvl("hat"), pan=-0.25)
        if lvl("clap"):
            for st in (4, 12):
                add(bus["clap"], clap(), sw(st), 0.5 * lvl("clap"), pan=0.05)
        if lvl("conga"):
            for st, f in ((4, 230), (7, 300), (10, 230), (12, 190)):
                add(bus["conga"], conga(f), sw(st), 0.5 * lvl("conga"), pan=-0.4)
        if lvl("rim"):
            for st in (3, 9, 14):
                add(bus["rim"], rim(), sw(st) + 0.008, 0.35 * lvl("rim"), pan=0.45)
        if lvl("stabs"):
            for st in (2, 10):
                add(bus["stabs"], epiano([n + 12 for n in notes[:3]] if b % 4 == 3 else notes), sw(st), 0.5 * lvl("stabs"), pan=-0.15)
        if lvl("kal") and b % 4 in (0, 1, 2) or (lvl("kal") and s["id"] in ("open", "notebook", "natlas", "end")):
            for st, n in (KAL_A if b % 2 == 0 else KAL_B):
                add(bus["kal"], kalimba(n), sw(st), 0.45 * (lvl("kal") or 0.5), pan=0.3 if st % 2 else -0.3)
    # the drop: riser into the logo, a hit on it, the final hit on the end card
    logo = next(s for s in film["shots"] if s["id"] == "logo")
    rise_len = 1.6
    r = filt(noise(rise_len), "bandpass", [800, 6000]) * np.linspace(0, 1, int(rise_len * SR)) ** 2
    add(bus["pad"], r * 0.25, logo["start"] - rise_len)
    for tt, g in ((logo["start"], 1.0), (end["start"], 0.8)):
        boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-tsec(1.4) / 0.08)) / SR) * np.exp(-tsec(1.4) / 0.45)
        add(bus["kick"], boom * 0.9 * g, tt)
        add(bus["pad"], filt(noise(1.8), "highpass", 5000) * np.exp(-tsec(1.8) / 0.5) * 0.12 * g, tt)
    # kick pumps the pad and stabs a little
    side = np.zeros(N)
    for b in range(nbars):
        s = shot_at(b * BAR + 0.01)
        if MODES.get(s["id"], {}).get("all"):
            for st in (0, 4, 8, 12):
                i = int((b * BAR + st * S16) * SR)
                L = min(N - i, int(0.25 * SR))
                if L > 0:
                    side[i:i + L] = np.maximum(side[i:i + L], np.exp(-np.arange(L) / SR / 0.09))
    duck = 1 - 0.35 * side
    for k in ("pad", "stabs"):
        bus[k] *= duck[:, None]
    room = ir(1.6, damp=5000, seed=3)
    m = sum(bus[k] for k in ALL if k not in ("kick", "log"))
    m = reverb(m, room, wet=0.18)
    m += bus["kick"] + filt(bus["log"], "lowpass", 2500)
    m[:, :] = np.tanh(m * 0.9) / 0.9
    return m


# ================================================================ product sounds and foley
def foley(name):
    for f in sorted(os.listdir(ASSETS)) if os.path.isdir(ASSETS) else []:
        if f.startswith("sfx_" + name) and f.endswith((".mp3", ".wav", ".ogg", ".flac")):
            x = read_audio(os.path.join(ASSETS, f))
            return x
    return None


def whoosh(length=0.5, up=False, gain=1.0):
    n = int(length * SR)
    x = noise(length)
    out = np.zeros(n)
    blk = 256
    for i in range(0, n, blk):
        p = i / n
        c = 500 * (8 ** (p if up else (1 - abs(2 * p - 1)) if not up else p))
        c = min(c, 9000)
        out[i:i + blk] = signal.sosfilt(sos("bandpass", [c / 1.6, c * 1.6]), x[i:i + blk])
    env = np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5
    return out * env * 0.5 * gain


def tap():
    t = tsec(0.06)
    return (filt(noise(0.06), "bandpass", [1500, 2700]) * 0.6 + np.sin(2 * np.pi * 3000 * t) * 0.15) * np.exp(-t / 0.012)


def tick(pitch=0):
    t = tsec(0.06)
    f = (1500 * np.exp(-t / 0.03) + 500) * 2 ** (pitch / 12)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.018) * 0.5


def chime():
    out = np.zeros(int(1.2 * SR))
    for k, (f, d) in enumerate(((1046.5, 0), (1318.5, 0.085))):
        t = tsec(1.0)
        x = (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t / 0.08)) * np.exp(-t / 0.35)
        i = int(d * SR)
        out[i:i + len(x)] += x * (1 - np.exp(-t / 0.002)) * 0.35
    return out


def shutter():
    out = np.zeros(int(0.35 * SR))
    for d, g in ((0, 1), (0.16, 0.6)):
        t = tsec(0.03)
        x = filt(noise(0.03), "bandpass", [1800, 6000]) * np.exp(-t / 0.006) + np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.01) * 0.5
        i = int(d * SR)
        out[i:i + len(x)] += x * g
    return out * 0.6


def pen(length, strike=False):
    n = int(length * SR)
    x = filt(noise(length), "bandpass", [1800, 7000])
    t = np.arange(n) / SR
    if strike:
        env = np.sin(np.pi * np.clip(t / length, 0, 1)) ** 0.6
    else:   # strokes: 9 to 13 a second, uneven
        rate = 11 + 2 * np.sin(2 * np.pi * 0.7 * t)
        env = 0.5 + 0.5 * np.sin(2 * np.pi * np.cumsum(rate) / SR) ** 2
        env *= np.clip(t / 0.03, 0, 1) * np.clip((length - t) / 0.05, 0, 1)
    return x * env * 0.18


def hit():
    t = tsec(1.0)
    return np.sin(2 * np.pi * np.cumsum(50 + 40 * np.exp(-t / 0.05)) / SR) * np.exp(-t / 0.3) * 0.5


def effects():
    fx = buf()
    real = {k: foley(k) for k in ("pen", "page", "shutter", "tap", "whoosh")}
    for c in film["cues"]:
        k, t = c["kind"], c["t"]
        g = c.get("gain", 1.0)
        if k == "whoosh":
            if real["whoosh"] is not None:
                add(fx, real["whoosh"][: int(0.8 * SR)] * 0.5, t, g)
            else:
                add(fx, whoosh(0.5, c.get("up", False)), t, g)
        elif k == "sheet":
            add(fx, whoosh(0.32, True, 0.5), t, 0.6)
        elif k == "tap":
            add(fx, real["tap"][: int(0.15 * SR)] if real["tap"] is not None else tap(), t, 0.7)
        elif k == "tick":
            add(fx, tick(c.get("pitch", 0) * 2), t, g * 1.2, pan=0.1)
        elif k == "chime":
            add(fx, chime(), t, 0.8)
        elif k == "shutter":
            add(fx, real["shutter"][: int(0.6 * SR)] if real["shutter"] is not None else shutter(), t, 0.9)
        elif k == "pen":
            if real["pen"] is not None and not c.get("strike"):
                src = real["pen"]
                off = int(RNG.uniform(0, max(1, len(src) / SR - c["dur"] - 0.1)) * SR)
                seg = src[off:off + int(c["dur"] * SR)]
                fade = np.clip(np.minimum(np.arange(len(seg)), np.arange(len(seg))[::-1]) / (0.02 * SR), 0, 1)
                add(fx, seg * fade[:, None], t, 0.8)
            else:
                add(fx, pen(c["dur"], c.get("strike", False)), t, 1.0, pan=-0.2)
        elif k == "hit":
            add(fx, hit(), t, g)
        elif k == "swell":
            n = int(c["dur"] * SR)
            sw = filt(noise(c["dur"]), "lowpass", 900) * np.linspace(0, 1, n) ** 2 * 0.12
            add(fx, sw, t)
    return reverb(fx, ir(0.8, damp=7000, seed=5), wet=0.12)


# ================================================================ the market
AMB_LEVEL = {"open": 1.0, "notebook": 0.42, "logo": 0.16, "speak": 0.2, "voices": 0.05, "sums": 0.1,
             "send": 0.12, "pages": 0.12, "natlas": 0.03, "end": 0.12}


def market():
    d = os.path.join(ASSETS, "market")
    main = read_audio(os.path.join(d, "market_582962.mp3")) if os.path.exists(os.path.join(d, "market_582962.mp3")) else None
    lagos = read_audio(os.path.join(d, "market_411123.mp3")) if os.path.exists(os.path.join(d, "market_411123.mp3")) else None
    amb = buf()
    if main is not None:
        seg = main[int(14 * SR):int(14 * SR) + N]
        amb[: len(seg)] += seg * 2.5    # this recording is quiet (-25.7 LUFS)
    if lagos is not None:
        seg = lagos[int(8 * SR):int(8 * SR) + N]
        amb[: len(seg)] += seg * 0.5    # and this one loud (-13.6 LUFS)
    # level by shot, eased between shots; a slow fade-in at the start and out at the end
    lv = np.zeros(N)
    for s in film["shots"]:
        a, b = int(s["start"] * SR), min(N, int(s["end"] * SR))
        lv[a:b] = AMB_LEVEL.get(s["id"], 0.1)
    lv[int(film["duration"] * SR):] = 0
    lv = signal.sosfiltfilt(sos("lowpass", 1.2), lv)
    lv *= np.clip(np.arange(N) / (1.4 * SR), 0, 1)
    lv *= np.clip((film["duration"] * SR - np.arange(N)) / (2.0 * SR), 0, 1)
    amb = filt(amb, "highpass", 70)
    return amb * lv[:, None]


# ================================================================ voices
def voices():
    vb = buf()
    room = ir(0.5, predelay=0.008, damp=6500, seed=9)
    for c in film["cues"]:
        if c["kind"] != "voice" or not c.get("file"):
            continue
        path = os.path.join(HERE, "voices", c["file"])
        if not os.path.exists(path):
            print("missing voice clip:", c["file"])
            continue
        x = read_audio(path).mean(axis=1)
        x = filt(x, "highpass", 90)
        x = peaking(x, 3200, 3.0, 0.9)
        x = peaking(x, 250, -1.5, 1.0)
        x /= max(1e-9, np.sqrt(np.mean(x ** 2))) / 0.12   # every line at the same speaking level
        add(vb, x, c["t"], 1.0)
    return reverb(vb, room, wet=0.07)


def duck(x, by, db=-9.0, attack=0.015, release=0.6):
    e = np.abs(by).max(axis=1)
    e = (e > 0.01).astype(np.float64)
    out = np.zeros_like(e)
    a, r = np.exp(-1 / (attack * SR)), np.exp(-1 / (release * SR))
    # attack/release smoothing of the "a voice is speaking" gate
    y = 0.0
    for i in range(0, len(e), 64):
        v = e[i:i + 64].max()
        y = v + (y - v) * (a ** 64 if v > y else r ** 64)
        out[i:i + 64] = y
    g = 10 ** (db * out / 20)
    return x * g[:, None]


def write_wav(path, x):
    y = np.clip(x, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((y * 32767).astype("<i2").tobytes())


def loudnorm(src, dst):
    a = "loudnorm=I=-14:TP=-1:LRA=11:print_format=json"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-af", a, "-f", "null", "-"], capture_output=True, text=True)
    m = json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])
    a2 = (f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:print_format=json")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-y", "-i", src, "-af", a2, "-ar", str(SR), dst], capture_output=True, text=True)
    m2 = json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])
    return m2.get("normalization_type"), m2.get("output_i"), m2.get("output_tp")


def main():
    os.makedirs(OUT, exist_ok=True)
    print(f"film {film['duration']:.2f} s, {len(film['cues'])} cues")
    mus = music()
    fx = effects()
    amb = market()
    vo = voices()
    mus = duck(mus, vo, -9.0)
    amb = duck(amb, vo, -8.0)
    mix = mus * 0.5 + fx * 0.9 + amb * 0.9 + vo * 1.25
    # a gentle bus glue and a safety soft-clip
    mix = np.tanh(mix * 1.1) / 1.1
    if "--stems" in sys.argv:
        for name, x in (("music", mus), ("fx", fx), ("market", amb), ("voices", vo)):
            write_wav(os.path.join(OUT, f"stem_{name}.wav"), x * 0.8)
    pre = os.path.join(OUT, "mix_pre.wav")
    write_wav(pre, mix * 0.7)
    kind, i, tp = loudnorm(pre, os.path.join(OUT, "mix.wav"))
    print(f"mix.wav: {kind} normalisation, {i} LUFS, true peak {tp} dBTP")


if __name__ == "__main__":
    main()
