"""Spare Intron keys (src/intron_keys.py): when Intron refuses a key for credit, quota or the key itself, the next key
takes over at once for voice replies, live talk and the backup hearing; the refused key rests and comes back later;
the team is told once per change; no key ever appears in output, the log or an alert.
Fakes only (a local Intron and a fake WebSocket), no network. python eval/test_intron_keys.py
"""
import asyncio
import contextlib
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import time
import wave

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith(("API_KEY", "_TOKEN", "_SECRET", "_URL")) or k.startswith(("NATLAS", "INTRON", "TEAM_", "TTS_")):
        os.environ.pop(k)
D = tempfile.mkdtemp()
A, B, C = "key-aaaa-1111-credit-gone", "key-bbbb-2222-working", "key-cccc-3333-spare"
SEEN = []


def wav_bytes():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 800)
    return buf.getvalue()


class Fake(http.server.BaseHTTPRequestHandler):
    def _send(self, code, obj=None, raw=None):
        b = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "audio/wav" if raw is not None else "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        return self._send(200, raw=wav_bytes())

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        key = self.headers.get("Authorization", "").replace("Bearer ", "")
        SEEN.append((self.path, key))
        if key == A:
            return self._send(402, {"message": "Insufficient credit balance on this account"})
        if self.path.startswith("/tts/"):
            return self._send(200, {"data": {"processing_status": "TTS_TEXT_AUDIO_GENERATED",
                                             "audio_path": f"http://127.0.0.1:{PORT}/audio.wav"}})
        return self._send(200, {"data": {"audio_transcript": "Iya Bisi took rice 5000"}})

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]
os.environ.update(ACCOUNTS_DB=os.path.join(D, "a.db"), BOOKS_DIR=os.path.join(D, "books"), DB_PATH=os.path.join(D, "t.db"),
                  INTRON_TTS_URL=f"http://127.0.0.1:{PORT}", INTRON_URL=f"http://127.0.0.1:{PORT}/file/v1/upload/sync",
                  INTRON_API_KEY=A, INTRON_API_KEY_2=B, INTRON_KEY_REST="60")
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import asr  # noqa: E402
import events  # noqa: E402
import intron_keys  # noqa: E402
import intron_live  # noqa: E402
import natlas_watch  # noqa: E402
import tts  # noqa: E402

tts._CACHE_DIR = os.path.join(D, "voice-cache")
ALERTS = []
natlas_watch._tell_team = ALERTS.append
events.ENABLED = True
CHECKS = []


def check(name, ok, got=""):
    CHECKS.append(bool(ok))
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:500]}"))


def settle():
    time.sleep(0.3)   # alerts go out on a thread


class FakeWS:
    """Intron's streaming API: SESSION_CREATED for a good key, AUTHENTICATION_ERROR or QUOTA_EXCEEDED otherwise."""
    def __init__(self, key):
        self.key = key

    async def recv(self):
        if self.key in (A,):
            return json.dumps({"message_type": "QUOTA_EXCEEDED", "message": "credit exhausted for this access-key"})
        return json.dumps({"message_type": "SESSION_CREATED", "credit_balance": 980 if self.key == B else 450})

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass


class FakeLib:
    @staticmethod
    def connect(url, additional_headers=None, **kw):
        key = (additional_headers or {}).get("Authorization", "").replace("Bearer ", "")
        SEEN.append(("ws", key))

        class Conn:
            def __await__(self_inner):
                async def go():
                    return FakeWS(key)
                return go().__await__()

            async def __aenter__(self_inner):
                return FakeWS(key)

            async def __aexit__(self_inner, *a):
                pass
        return Conn()


intron_live._websockets = lambda: FakeLib


def main():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        # 1. voice replies: key 1 has no credit, key 2 makes the voice at once
        got = tts.speak("Iya Bisi will pay you sixty thousand naira.", "English")
        settle()
        tts_keys = [k for p, k in SEEN if p.startswith("/tts/")]
        check_voice = (got and got["engine"].startswith("intron") and tts_keys[:2] == [A, B], got, tts_keys)
        alerts_1 = list(ALERTS)
        states_1 = intron_keys.states()
        # 2. the next reply goes straight to key 2 (key 1 rests), no new alert
        SEEN.clear()
        tts.speak("Mama Ngozi paid you five thousand naira.", "English")
        settle()
        second = [k for p, k in SEEN if p.startswith("/tts/")]
        alerts_2 = list(ALERTS)
        # 3. the backup hearing uses the working key too
        SEEN.clear()
        wav = os.path.join(D, "note.wav")
        open(wav, "wb").write(wav_bytes())
        heard = asr._intron_transcribe(wav, "English / Pidgin")
        asr_keys = [k for p, k in SEEN if p.startswith("/file/")]
        # 4. live talk: key 1 resting, so the hearing session opens with key 2
        intron_keys.reset()
        ALERTS.clear()
        SEEN.clear()
        ws, key = asyncio.run(intron_live._connect("wss://fake/stt", 1024))
        settle()
        live_keys = [k for p, k in SEEN if p == "ws"]
        alerts_live = list(ALERTS)
        # 5. every key refused: voice off, live talk rests, one 'every key' alert
        intron_keys.reset()
        ALERTS.clear()
        os.environ["INTRON_API_KEY_2"] = A   # (both keys now out of credit)
        intron_keys._told["last"] = None
        tts._INTRON_DOWN["until"] = 0
        none_voice = tts.speak("Oga Emeka owes you nine thousand naira.", "English")
        try:
            asyncio.run(intron_live._connect("wss://fake/stt", 1024))
            live_err = None
        except RuntimeError as e:
            live_err = str(e)
        settle()
        alerts_all = list(ALERTS)
        voice_down, live_down = time.time() < tts._INTRON_DOWN["until"], time.time() < intron_live._DOWN["until"]
        hearing_on = intron_live.hearing_on()
        os.environ["INTRON_API_KEY_2"] = B
        # 6. a rest ends: key 1 is tried first again
        intron_keys.reset()
        tts._INTRON_DOWN["until"] = intron_live._DOWN["until"] = 0
        os.environ["INTRON_KEY_REST"] = "0.002"   # 0.12 s
        intron_keys.refused("key 1", "HTTP 402 credit")
        first_after = intron_keys.pick()[0]
        time.sleep(0.2)
        first_later = intron_keys.pick()[0]
        os.environ["INTRON_KEY_REST"] = "60"
        # 7. preflight: each key's own line with its credit; a refused spare is a WARN
        import preflight
        intron_keys.reset()
        os.environ.update(INTRON_API_KEY=C, INTRON_API_KEY_3=C)   # every key with credit
        pf_all = preflight.intron_hearing()
        os.environ["INTRON_API_KEY"] = A
        os.environ["INTRON_API_KEY_3"] = A
        pf_warn = preflight.intron_hearing()
        os.environ.pop("INTRON_API_KEY_3")
    text = out.getvalue()
    print(text)
    check("voice: key 1 refused (no credit), key 2 makes the reply at once", *check_voice[:1], check_voice)
    check("…the team is told once: 'key 1 was refused, using key 2'",
          len(alerts_1) == 1 and "key 1" in alerts_1[0] and "Using key 2" in alerts_1[0], alerts_1)
    check("…key 1 shows as resting, key 2 in use", states_1[0]["state"].startswith("resting")
          and states_1[1]["state"] == "in use", states_1)
    check("the next reply goes straight to key 2, and no second alert", second == [B] and alerts_2 == alerts_1,
          (second, alerts_2))
    check("backup hearing: uses the working key (key 1 resting)", heard["text"] and asr_keys == [B], (heard, asr_keys))
    check("live talk: key 1's session refused (quota), it reconnects with key 2", key[0] == "key 2" and live_keys == [A, B],
          (key, live_keys))
    check("…and tells the team", len(alerts_live) == 1 and "Using key 2" in alerts_live[0], alerts_live)
    check("every key refused: no voice (text replies) and the voice rests", none_voice is None and voice_down)
    check("…live talk can't open, rests, and the page uses the N-ATLaS hearing", live_err and live_down and not hearing_on,
          (live_err, live_down, hearing_on))
    check("…the team hears 'using key 2', then one 'every key' alert that says how to add a key",
          len(alerts_all) == 2 and "Using key 2" in alerts_all[0] and "every Intron key" in alerts_all[1]
          and "INTRON_API_KEY_2" in alerts_all[1], alerts_all)
    check("a refused key comes back after its rest (INTRON_KEY_REST)", first_after == "key 2" and first_later == "key 1",
          (first_after, first_later))
    check("preflight: each key with its credit", pf_all[0] == "PASS" and "key 1: works, credit 450, in use" in pf_all[1]
          and "key 2: works, credit 980, spare" in pf_all[1] and "key 3: works, credit 450, spare" in pf_all[1], pf_all)
    check("preflight: a refused spare is a WARN that says top up", pf_warn[0] == "WARN" and "key 3: refused" in pf_warn[1],
          pf_warn)
    log = [r for r in events.rows(team=True) if r["kind"] == "intron_key"]
    check("/team's log has each switch (key named, no key)", log and all(r["engine"].startswith("key ") for r in log), log)
    every = text + json.dumps(ALERTS + alerts_1 + alerts_all) + json.dumps(log) + json.dumps([pf_all, pf_warn])
    check("no key value anywhere: output, alerts, log, preflight", not any(k in every for k in (A, B, C)))
    check("/api/status counts only", '"intron_keys"' not in text and all(k not in json.dumps(intron_keys.states())
                                                                         for k in (A, B, C)))
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} spare-key checks pass")
    return 0 if all(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
