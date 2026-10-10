"""The N-ATLaS evidence script (scripts/natlas_evidence.py), against a fake Modal server: every part prints, one call
failing doesn't stop the rest, its own calls stay out of the pilot's numbers, and no key ever reaches the output.
No network needed. python eval/test_natlas_evidence.py
"""
import contextlib
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import wave

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith(("API_KEY", "_TOKEN", "_SECRET", "_URL")) or k.startswith(("NATLAS", "INTRON", "TEAM_", "TTS_")):
        os.environ.pop(k)
D = tempfile.mkdtemp()
SECRET = "sekrit-key-0042"
SEEN = {"auth": [], "transcribe": []}


class Fake(http.server.BaseHTTPRequestHandler):
    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        SEEN["auth"].append(self.headers.get("Authorization"))
        if self.path.endswith("/models"):
            return self._send({"data": [{"id": "natlas", "root": "NCAIR1/N-ATLaS", "max_model_len": 8192}]})
        return self._send({"ok": True, "models": {"yoruba": "NCAIR1/Yoruba-ASR", "hausa": "NCAIR1/Hausa-ASR",
                                                   "igbo": "NCAIR1/Igbo-ASR", "english": "NCAIR1/NigerianAccentedEnglish"}})

    def do_POST(self):
        SEEN["auth"].append(self.headers.get("Authorization"))
        body = self.rfile.read(int(self.headers["Content-Length"])).decode("latin-1")
        lang = body.split('name="lang"')[1].split("\r\n\r\n")[1].split("\r\n")[0]
        also = body.split('name="also"')[1].split("\r\n\r\n")[1].split("\r\n")[0]
        SEEN["transcribe"].append((lang, also))
        out = {"text": f"heard in {lang}", "model": f"model-{lang}", "seconds": 3.2}
        if also:
            out["also"] = {"text": "heard in english", "model": "NCAIR1/NigerianAccentedEnglish"}
        return self._send(out)

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]
os.environ.update(ACCOUNTS_DB=os.path.join(D, "a.db"), BOOKS_DIR=os.path.join(D, "books"), DB_PATH=os.path.join(D, "t.db"),
                  EVENTS_DB=os.path.join(D, "events.db"), NATLAS_URL=f"http://127.0.0.1:{PORT}/v1",
                  NATLAS_ASR_URL=f"http://127.0.0.1:{PORT}", NATLAS_KEY=SECRET, INTRON_API_KEY=SECRET,
                  NVIDIA_API_KEY=SECRET)
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import events  # noqa: E402
import hearing  # noqa: E402
import llm  # noqa: E402
import natlas_evidence as ne  # noqa: E402
import tts  # noqa: E402

CHECKS = []


def check(name, ok, got=""):
    CHECKS.append(bool(ok))
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:600]}"))


KEY = ne.cases()


def fake_chat(messages, **kw):
    """N-ATLaS answers with the answer key's record; the Hausa call fails (a part failing must not stop the rest)."""
    text = messages[-1]["content"]
    c = next(c for c in KEY.values() if c["text"] == text)
    if c["lang"] == "hausa":
        raise RuntimeError(f"Modal said 500 (Bearer {SECRET})")
    assert kw.get("models") == ["natlas"] and kw.get("schema") and kw.get("shots"), kw
    return json.dumps({"type": c["type"], "amount": c["amount"], "customer": c.get("customer"), "item": None,
                       "quantity": None, "unit": None, "each": None, "due_date": None, "confidence": 0.9, "note": ""}), \
        "natlas:NCAIR1/N-ATLaS"


def fake_speak(text, language="English", **kw):
    p = os.path.join(D, f"v-{language}.wav")
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 1600)
    return {"path": p, "engine": "intron"}


def main():
    # a little pilot log first: two N-ATLaS answers and one backup, one voice note heard by N-ATLaS speech
    events.ENABLED = True   # (only the web server logs; on here, so the evidence run's own calls would show)
    for engine in ("natlas:NCAIR1/N-ATLaS", "natlas:NCAIR1/N-ATLaS", "nvidia/llama-3.3"):
        events.log("llm", "2348031112222", engine=engine, ok=True, ms=900)
    events.log("hear", "2348031112222", engine="natlas:NCAIR1/Yoruba-ASR", ok=True, ms=2000)
    before = len(events.rows())
    llm.chat = fake_chat
    tts.speak = fake_speak
    hearing.merge = lambda a, b, lang, vocab=None, timeout=None: ("merged words", "merged")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = ne.main(["--start", "2020-01-01", "--out", os.path.join(D, "e.txt")])
    txt = out.getvalue()
    print(txt)
    check("runs to the end (exit 0) and writes the file too", code == 0 and open(os.path.join(D, "e.txt")).read().strip() == txt.strip())
    check("all four parts print", all(f"{p}. " in txt for p in "ABCD"), txt[:300])
    check("A: names the served N-ATLaS weights and the four speech models",
          "NCAIR1/N-ATLaS" in txt and all(m in txt for m in ("Yoruba-ASR", "Hausa-ASR", "Igbo-ASR", "NigerianAccentedEnglish")))
    check("A: shows hosts only, never the full link", "127.0.0.1" in txt and f":{PORT}/v1" not in txt)
    check("B: N-ATLaS JSON and the checked record for each language that answered",
          txt.count("N-ATLaS JSON:") == 4 and txt.count("after code checks:") == 4)
    check("B: a failing call says so and the others still run", "could not run" in txt and "4 of 5 records match" in txt, txt)
    check("C: each language heard by its N-ATLaS model; Yoruba, Hausa, Igbo also by English and merged",
          [s[0] for s in SEEN["transcribe"]] == ["english", "english", "yoruba", "hausa", "igbo"]
          and [bool(s[1]) for s in SEEN["transcribe"]] == [False, False, True, True, True]
          and txt.count("merged by N-ATLaS") == 3)
    check("D: the pilot counts (N-ATLaS share of AI answers, voice notes by model)",
          "AI answers: 3, of which N-ATLaS: 67%" in txt and "N-ATLaS speech" in txt, txt)
    check("its own calls are not added to the pilot log", len(events.rows()) == before, len(events.rows()))
    check("every call to our servers carried the key (never printed)", SEEN["auth"] and all(a == f"Bearer {SECRET}" for a in SEEN["auth"]))
    check("no key appears anywhere in the output (even inside an error)", SECRET not in txt)
    check("ends with the N-ATLaS attribution", txt.strip().endswith(ne.ATTRIBUTION))
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} checks pass")
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
