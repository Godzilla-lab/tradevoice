"""Light audio preparation and word confidence for the N-ATLaS hearing server (deploy/modal_asr.py ships this file).

Light only (ROADMAP Part 5): cut the quiet at the start and end, and level the volume. No denoising: a 2025 study
found denoising made Whisper worse at every noise level (8.8% -> 25.8% WER). The team A/B tests it on real market
voice notes with scripts/speech_ab.py; prep=0 on the request turns it off.
Pure numpy, so it runs (and is tested) without the models.
"""
import numpy as np

SR = 16000
FRAME = 480            # 30 ms
KEEP = 0.25            # seconds of quiet kept around the voice (cut words sound wrong)
TARGET = 0.1           # loud parts levelled to about -20 dBFS
MAX_GAIN = 10.0        # at most +20 dB: a whisper-quiet phone is lifted, the noise floor isn't blown up
MIN_GAIN = 0.5


def _rms(audio):
    n = len(audio) // FRAME * FRAME
    if n == 0:
        return np.array([float(np.sqrt(np.mean(np.square(audio, dtype=np.float64)) + 1e-12))]) if len(audio) else \
            np.array([0.0])
    return np.sqrt(np.mean(np.square(audio[:n].reshape(-1, FRAME), dtype=np.float64), axis=1) + 1e-12)


def prepare(audio):
    """16 kHz mono float32 in -> trimmed and levelled float32 out (the same audio if there is no clear voice)."""
    audio = np.asarray(audio, dtype=np.float32)
    rms = _rms(audio)
    if len(audio) < SR // 2 or rms.max() < 0.005:   # too short, or nothing there: leave it to the silence check
        return audio
    loud = np.flatnonzero(rms > max(0.005, rms.max() * 0.05))
    pad = int(KEEP * SR)
    start = max(0, loud[0] * FRAME - pad)
    end = min(len(audio), (loud[-1] + 1) * FRAME + pad)
    out = audio[start:end]
    voiced = rms[loud]
    level = float(np.percentile(voiced, 90))
    gain = min(MAX_GAIN, max(MIN_GAIN, TARGET / max(level, 1e-6)))
    out = out * gain
    peak = float(np.abs(out).max())
    if peak > 0.99:
        out = out * (0.99 / peak)     # never clip
    return out.astype(np.float32)


def words(pieces):
    """[(BPE token, probability)] -> [(word, lowest probability in it)]. Whisper's byte-level tokens start a new
    word with 'Ġ' (a space); `decode` turns a token list back into text."""
    out, cur = [], []
    for tok, p in pieces:
        if cur and tok.startswith("Ġ"):
            out.append(cur)
            cur = []
        cur.append((tok, p))
    if cur:
        out.append(cur)
    return out


def unsure_words(pieces, decode, threshold=0.4):
    """The words the model wasn't sure of (lowest token probability under `threshold`), plus the mean probability
    of all tokens (a whole-note confidence)."""
    unsure = []
    for grp in words(pieces):
        w = decode([t for t, _ in grp]).strip()
        p = min(q for _, q in grp)
        if w and p < threshold:
            unsure.append({"word": w, "p": round(p, 2)})
    mean = float(np.mean([p for _, p in pieces])) if pieces else None
    return unsure, mean
