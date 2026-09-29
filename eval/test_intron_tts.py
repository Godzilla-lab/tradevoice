"""Intron voice (TTS): request shape, long replies in pieces, learned text limit, accent retry, 503 polling,
fallback to Spitch when Intron refuses. Intron is faked (no key or network needed).   python eval/test_intron_tts.py
"""
import io
import os
import sys
import wave

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("TTS_", "INTRON_")):
        os.environ.pop(k)
os.environ["INTRON_API_KEY"] = "test-key"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import requests  # noqa: E402

import tts  # noqa: E402

CHECKS = []


def check(name, ok, got=""):
    ok = bool(ok)
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def wav_bytes(n=800):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000), w.writeframes(b"\0\0" * n)
    return b.getvalue()


class R:
    def __init__(self, code, j=None, content=b"", headers=None):
        self.status_code, self._j, self.content, self.headers, self.text = code, j, content, headers or {}, str(j)

    def json(self):
        return self._j

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


SENT, MODE = [], {"limit": None, "accent_bad": False, "busy": False, "refuse": False}


def fake_post(url, json=None, headers=None, timeout=None):
    SENT.append((url, json, headers))
    if MODE["refuse"]:
        return R(402, {"message": "insufficient credits"})
    if MODE["limit"] and len(json["text"]) > MODE["limit"]:
        return R(400, {"message": f"text character count greater than the max limit of {MODE['limit']} characters"})
    if MODE["accent_bad"] and "voice_accent" in json:
        return R(400, {"message": f"invalid text voice accent,{json['voice_accent']} not supported"})
    if MODE["busy"]:
        return R(503, {"data": {"text_id": "t1"}})
    return R(200, {"data": {"audio_path": "https://cdn/x.wav", "processing_status": "TTS_TEXT_AUDIO_GENERATED"}})


def fake_get(url, headers=None, timeout=None):
    if "/status/" in url:
        return R(200, {"data": {"audio_path": "https://cdn/x.wav", "processing_status": "TTS_TEXT_AUDIO_GENERATED"}})
    return R(200, content=wav_bytes())


requests.post, requests.get = fake_post, fake_get


def main():
    check("Intron is the voice when INTRON_API_KEY is set", tts.backend() == "intron")
    out = tts.speak("Mama Tunde don pay you forty-five thousand naira.", "Yoruba")
    url, body, head = SENT[-1]
    check("request: /tts/v1/generate, bearer key, yo + yoruba accent", url.endswith("/tts/v1/generate")
          and head["Authorization"] == "Bearer test-key" and body["voice_language"] == "yo"
          and body["voice_accent"] == "yoruba", SENT[-1])
    check("audio downloaded as a WAV file", out["path"].endswith(".wav") and out["engine"] == "intron:yo", out)
    tts.speak("Hello", "Pidgin")
    check("Pidgin uses the Nigerian English voice", SENT[-1][1]["voice_language"] == "en"
          and SENT[-1][1]["voice_accent"] == "nigerian")

    SENT.clear()
    MODE["limit"] = 100
    long = " ".join(["Iya Bisi owes you twenty thousand naira for indomie."] * 6)
    out = tts.speak(long, "English")
    check("too long -> learns the 100-character limit, sends pieces, joins them", out["path"].endswith(".wav")
          and all(len(b["text"]) <= 100 for _, b, _ in SENT[1:]) and tts._INTRON_MAX["chars"] <= 100, [len(b["text"]) for _, b, _ in SENT])
    with wave.open(out["path"]) as w:
        check("…into one clip", w.getnframes() == 800 * len(tts._pieces(tts.speakable(long), tts._INTRON_MAX["chars"])))
    MODE["limit"] = None

    MODE["accent_bad"] = True
    SENT.clear()
    tts.speak("Ina kwana", "Hausa")
    check("accent refused -> retried without an accent", "voice_accent" not in SENT[-1][1] and len(SENT) == 2, SENT)
    MODE["accent_bad"] = False

    MODE["busy"] = True
    check("503 with text_id -> polls the status until ready", tts.speak("Daalụ", "Igbo")["path"].endswith(".wav"))
    MODE["busy"] = False

    MODE["refuse"] = True
    os.environ["SPITCH_API_KEY"] = "x"
    tts._spitch_safe = lambda text, language, fmt, v, speed: "/tmp/spitch.wav"
    out = tts.speak("Hello", "English")
    check("Intron out of credits -> Spitch speaks instead", out["engine"].startswith("spitch"), out)
    n = len(SENT)
    tts.speak("Hello again", "English")
    check("…and Intron rests for 10 minutes (not asked again)", len(SENT) == n)

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} Intron voice checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
