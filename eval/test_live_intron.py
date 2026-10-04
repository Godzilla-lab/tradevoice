"""Live talk on Intron's streaming APIs, against fake Intron servers that follow the docs (docs.voice.intron.io:
STT Streaming, TTS Streaming): the mic streamed through our server, words while you talk, the final words on
commit, the reply's voice in pieces (10-100 characters), the voice cache, refusals and the old way as backup.

python eval/test_live_intron.py
"""
import asyncio
import base64
import io
import json
import os
import sys
import tempfile
import threading
import time
import wave

os.environ["TV_NO_DOTENV"] = "1"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["BOOKS_DIR"] = tempfile.mkdtemp()
os.environ["ACCOUNTS_DB"] = os.path.join(tempfile.mkdtemp(), "a.db")
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "NATLAS", "WHATSAPP_", "INTRON")):
        os.environ.pop(k)
os.environ.update(TRADEVOICE_ADMIN="0", AUTO_REMINDERS="0", AUTH_REQUIRED="0", INTRON_API_KEY="test-key")

import websockets  # noqa: E402

passed = total = 0


def check(name, cond, got=""):
    global passed, total
    total += 1
    passed += bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  got: {got!r}"))


def wav_bytes(seconds=0.2):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * int(16000 * seconds))
    return b.getvalue()


# ---------------------------------------------------------------- fake Intron (STT + TTS on one port)
SEEN = {"stt": [], "tts": [], "chunks": [], "texts": [], "auth": [], "connections": 0}
MODE = {"stt": "ok", "tts": "ok"}


async def fake(ws):
    path = ws.request.path
    SEEN["auth"].append(ws.request.headers.get("Authorization"))
    SEEN["connections"] += 1
    if path.startswith("/stt"):
        SEEN["stt"].append(path)
        if MODE["stt"] == "quota":
            await ws.send(json.dumps({"message_type": "QUOTA_EXCEEDED", "credits_balance": "0",
                                      "message": "insufficient credits balance"}))
            return
        await ws.send(json.dumps({"message_type": "SESSION_CREATED", "session_id": "s1", "credit_balance": 9}))
        got = 0
        async for raw in ws:
            m = json.loads(raw)
            if m["message_type"] == "INPUT_AUDIO_CHUNK":
                n = len(base64.b64decode(m["audio_base_64"]))
                SEEN["chunks"].append(n)
                got += n
                await ws.send(json.dumps({"message_type": "AUDIO_CHUNK_ACK", "chunk_id": len(SEEN["chunks"])}))
                if len(SEEN["chunks"]) == 2:
                    await ws.send(json.dumps({"message_type": "PARTIAL_TRANSCRIPT", "transcript": "Mama Ngozi took"}))
            elif m["message_type"] == "COMMIT":
                if not got:
                    await ws.send(json.dumps({"message_type": "INPUT_ERROR", "message": "no data received"}))
                    return
                await ws.send(json.dumps({"message_type": "COMMITTED_TRANSCRIPT", "transcript_id": "t1",
                                          "transcript_text": "Mama Ngozi took rice 5000 on credit", "audio_len": 3}))
                return
    else:
        SEEN["tts"].append(path)
        if MODE["tts"] == "down":
            await ws.send(json.dumps({"message_type": "AUTHENTICATION_ERROR",
                                      "message": "permission denied,access-key error"}))
            return
        await ws.send(json.dumps({"message_type": "SESSION_CREATED", "session_id": "s2", "credit_balance": 9}))
        texts, polls = [], {}
        async for raw in ws:
            m = json.loads(raw)
            if m["message_type"] == "INPUT_TEXT_CHUNK":
                t = m["text"]
                SEEN["texts"].append(t)
                if not 10 <= len(t) <= 100:
                    await ws.send(json.dumps({"message_type": "CHUNK_SIZE_TOO_LARGE" if len(t) > 100
                                              else "CHUNK_SIZE_TOO_SMALL"}))
                    return
                texts.append(t)
                await ws.send(json.dumps({"message_type": "TEXT_CHUNK_ACK", "chunk_id": len(texts)}))
            elif m["message_type"] == "FETCH_AUDIO_CHUNK":
                i = m["chunk_id"]
                polls[i] = polls.get(i, 0) + 1
                ready = polls[i] >= 2   # the first ask: still PROCESSING (like the docs' example)
                await ws.send(json.dumps({"message_type": "FETCH_AUDIO_CHUNK", "processing_staus":
                                          "READY" if ready else "PROCESSING", "chunk_id": i,
                                          "audio_base_64": base64.b64encode(wav_bytes()).decode() if ready else "",
                                          "extension": ".wav"}))
            elif m["message_type"] == "COMMIT":
                await ws.send(json.dumps({"message_type": "COMMITTED_AUDIO", "text_id": "x", "audio_len": 1}))
                return


loop = asyncio.new_event_loop()
started = threading.Event()
PORT = {}


def serve():
    asyncio.set_event_loop(loop)

    async def main():
        server = await websockets.serve(fake, "127.0.0.1", 0)
        PORT["n"] = server.sockets[0].getsockname()[1]
        started.set()
        await asyncio.Future()
    loop.run_until_complete(main())


threading.Thread(target=serve, daemon=True).start()
started.wait(5)
os.environ["INTRON_STT_WS"] = f"ws://127.0.0.1:{PORT['n']}/stt/v1/stream"
os.environ["INTRON_TTS_WS"] = f"ws://127.0.0.1:{PORT['n']}/tts/v1/stream"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

import intron_live  # noqa: E402
import tts  # noqa: E402
import web  # noqa: E402

tts._CACHE_DIR = tempfile.mkdtemp()   # a fresh voice cache for this run
c = TestClient(web.app)

# 1. the pieces Intron's voice stream takes: 10 to 100 characters, cut where a voice pauses
for text in ["Done. Dino will pay you twenty thousand naira. All together, Dino still owes you forty five thousand "
             "naira, and Mama Ngozi owes you the rest of the money from last week. Should I save it?",
             "Mama Ngozi will pay you five thousand naira. Should I save it?"]:
    ps = intron_live.pieces(text)
    check(f"pieces of {len(text)} characters: each 10-100, nothing lost", all(10 <= len(p) <= 100 for p in ps)
          and " ".join(ps) == tts.speakable(text), ps)
check("'Done.' joins the next sentence (Intron needs 10+)", intron_live.pieces("Done. Dino will pay you.")[0]
      == "Done. Dino will pay you.")

# 2. hearing while you talk: our server passes the mic to Intron and the words back
check("/api/warm says live hearing is on (key set)", c.post("/api/warm", json={}).json().get("live") is True)
with c.websocket_connect("/api/live/hear?lang=Yoruba&consent=yes") as ws:
    for _ in range(5):
        ws.send_bytes(b"\1\0" * 1600)        # 0.1 s each
    m = ws.receive_json()
    check("words come back while you talk (partial)", m == {"type": "partial", "text": "Mama Ngozi took"}, m)
    ws.send_bytes(b"\1\0" * 350)              # a short last piece
    ws.send_text(json.dumps({"type": "commit"}))
    m = ws.receive_json()
check("…on commit: the final words", m == {"type": "final", "text": "Mama Ngozi took rice 5000 on credit"}, m)
check("…Intron got Yoruba's code (yo), 16 kHz 16-bit mono, and our key (never the page's)",
      "use_language_asr_input=yo" in SEEN["stt"][-1] and "sample_rate=16000" in SEEN["stt"][-1]
      and SEEN["auth"][-1] == "Bearer test-key", (SEEN["stt"][-1:], SEEN["auth"][-1:]))
check("…every audio piece within Intron's 1 KB to 32 KB (the short last one padded)",
      SEEN["chunks"] and all(1024 <= n <= 32768 for n in SEEN["chunks"]), SEEN["chunks"])
with c.websocket_connect("/api/live/hear?lang=English&consent=yes") as ws:
    ws.send_text(json.dumps({"type": "commit"}))
    m = ws.receive_json()
check("nothing said: empty final words (the page asks again), English/Pidgin uses pcm",
      m == {"type": "final", "text": ""} and "use_language_asr_input=pcm" in SEEN["stt"][-1], m)
with c.websocket_connect("/api/live/hear?lang=English") as ws:
    m = ws.receive_json()
check("no consent: refused", m.get("type") == "error", m)

# 3. the live reply: N-ATLaS/our code answer, the voice streamed by Intron in pieces, played as each is ready
started_old = []
web._start_voice = lambda sid: started_old.append(sid)
SEEN["texts"].clear()
d = c.post("/api/say", json={"session": "live1", "text": "Mama Ngozi took rice 5000 on credit", "lang": "English"}).json()
check("the reply says how many voice pieces", d["parts"] >= 2 and d["speak"] and not started_old, d)
got = [c.get(f"/api/speak/{d['speak']}/{i}") for i in range(d["parts"])]
check("each piece is a WAV the page can play, in order", all(r.status_code == 200 and r.content[:4] == b"RIFF"
                                                              for r in got), [r.status_code for r in got])
check("…Intron was sent the reply's words, 10-100 characters a piece",
      SEEN["texts"] and " ".join(SEEN["texts"]) == " ".join(web.VOICES[d["speak"]].parts)
      and all(10 <= len(t) <= 100 for t in SEEN["texts"]), SEEN["texts"])
n_tts = len(SEEN["tts"])
d2 = c.post("/api/say", json={"session": "live2", "text": "Mama Ngozi took rice 5000 on credit", "lang": "English"}).json()
for i in range(d2["parts"]):
    c.get(f"/api/speak/{d2['speak']}/{i}")
check("the same words again: from the voice cache (no Intron call, no cost)", len(SEEN["tts"]) == n_tts,
      len(SEEN["tts"]) - n_tts)
check("a piece that doesn't exist: 404", c.get(f"/api/speak/{d['speak']}/99").status_code == 404)

# 4. refusals: Intron's voice down -> the old voice makes the pieces; hearing quota -> the old hearing, rests 10 min
MODE["tts"] = "down"
made = []


def old_voice(text, lang="English", **k):
    made.append(text)
    p = tempfile.mkstemp(suffix=".wav")[1]
    open(p, "wb").write(wav_bytes())
    return {"path": p, "engine": "intron:old"}


tts.speak = old_voice
d = c.post("/api/say", json={"session": "live3", "text": "Iya Bisi took beans 8000 on credit", "lang": "English"}).json()
got = [c.get(f"/api/speak/{d['speak']}/{i}").status_code for i in range(d["parts"])]
parts = web.VOICES[d["speak"]].parts
check("Intron's voice stream refused: every piece still made (the old way, or the cache)", got == [200] * d["parts"]
      and made and set(made) <= set(parts), (got, made, parts))
intron_live._DOWN["until"] = 0
MODE["stt"] = "quota"
with c.websocket_connect("/api/live/hear?lang=Hausa&consent=yes") as ws:
    m = ws.receive_json()
check("hearing: no credit -> an error to the page (it hears its recording the old way)",
      m.get("type") == "error" and "credit" in m.get("message", ""), m)
check("…and live hearing rests 10 minutes (the page uses the old hearing meanwhile)",
      c.post("/api/warm", json={}).json().get("live") is False)
intron_live._DOWN["until"] = 0
os.environ["LIVE_HEARING"] = "natlas"
check("LIVE_HEARING=natlas switches it off", c.post("/api/warm", json={}).json().get("live") is False)
os.environ.pop("LIVE_HEARING")

# 5. logged out: the hearing socket is refused
web.AUTH_REQUIRED = True
try:
    with c.websocket_connect("/api/live/hear?lang=English&consent=yes") as ws:
        ws.receive_json()
    check("logged out: refused", False)
except WebSocketDisconnect as e:
    check("logged out: refused (4401)", e.code == 4401, e.code)
web.AUTH_REQUIRED = False

print(f"\n{passed}/{total} checks pass")
sys.exit(0 if passed == total else 1)
