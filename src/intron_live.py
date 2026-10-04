"""Live talk on Intron's streaming APIs (docs.voice.intron.io: "STT API > Streaming", "TTS Streaming").

Hearing: the page streams the microphone (16 kHz, 16-bit, mono) to our server (/api/live/hear, a WebSocket); we pass
it on to Intron's streaming speech-to-text and send its words back while the trader is still talking. When they
stop, COMMIT gives the final words at once (nothing waits for a whole file to upload and be heard). Intron's models
for Yoruba, Hausa, Igbo and Pidgin are code-switched with English, the way traders talk.
Speaking: the reply is cut into short pieces (Intron takes 10 to 100 characters per piece), streamed to Intron's
text-to-speech, and each piece's audio is ready on its own, so the page plays the first piece while the rest is made.
The brain in between stays N-ATLaS and our code (converse.reply). The API key never leaves the server.
"""
import asyncio
import base64
import json
import os
import re
import threading
import time

import tts

STT_WS = os.getenv("INTRON_STT_WS", "wss://infer.voice.intron.io/stt/v1/stream")
TTS_WS = os.getenv("INTRON_TTS_WS", "wss://infer.voice.intron.io/tts/v1/stream")
# Intron's speech-to-text codes; the local ones are code-switched with English ("Yoruba-English" = yo)
STT_LANG = {"English": os.getenv("INTRON_STT_ENGLISH", "pcm"), "English / Pidgin": os.getenv("INTRON_STT_ENGLISH", "pcm"),
            "Pidgin": "pcm", "Yoruba": "yo", "Hausa": "ha", "Igbo": "ig"}
CHUNK_MIN, CHUNK_MAX = 1024, 32 * 1024          # bytes per audio piece (Intron's limits)
TEXT_MIN, TEXT_MAX = 10, 100                    # characters per text piece (Intron's limits)
_ERRORS = ("ERROR", "INPUT_ERROR", "AUTHENTICATION_ERROR", "RESOURCE_EXHAUSTED", "QUOTA_EXCEEDED",
           "SESSION_TIME_LIMIT_EXCEEDED", "INSUFFICIENT_AUDIO_ACTIVITY", "INSUFFICIENT_TEXT_ACTIVITY",
           "CHUNK_SIZE_TOO_SMALL", "CHUNK_SIZE_TOO_LARGE", "CHUNK_ID_MISMATCH_WITH_TOTAL")
_DOWN = {"until": 0.0, "why": ""}   # a refusal for key or credits: rest 10 minutes (the old hearing is used meanwhile)


def _websockets():
    try:
        import websockets
        return websockets
    except ImportError:
        return None


def hearing_on():
    """Live talk hears with Intron when the key is set, LIVE_HEARING isn't "natlas" and Intron isn't resting."""
    return (bool(os.getenv("INTRON_API_KEY")) and os.getenv("LIVE_HEARING", "intron") == "intron"
            and _websockets() is not None and time.time() >= _DOWN["until"])


def _head():
    return {"Authorization": f"Bearer {os.environ['INTRON_API_KEY']}"}


def _rest(why):
    if any(w in why.lower() for w in ("auth", "credit", "quota", "permission", "access-key")):
        _DOWN["until"], _DOWN["why"] = time.time() + 600, why[:200]


def _log(kind, ok, lang, ms=None, engine="intron-stream"):
    try:
        import events
        events.log(kind, engine=engine, ok=ok, lang=lang, ms=ms)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- hearing (browser -> us -> Intron -> us -> browser)
async def relay_hearing(browser, lang):
    """browser: a Starlette WebSocket. It sends audio as binary frames and {"type": "commit"} when the trader has
    finished; it gets {"type": "partial"|"final"|"error", "text"|"message"}. One turn per connection."""
    ws_lib = _websockets()
    code = STT_LANG.get(lang, STT_LANG["English"])
    url = f"{STT_WS}?sample_rate=16000&bit_rate=16&num_channels=1&use_language_asr_input={code}"
    try:
        intron = await ws_lib.connect(url, additional_headers=_head(), open_timeout=8, max_size=2 ** 22)
    except Exception as e:  # noqa: BLE001
        await _send(browser, {"type": "error", "message": f"connect: {type(e).__name__}"})
        _log("hear", False, lang)
        return
    try:
        first = json.loads(await asyncio.wait_for(intron.recv(), 8))
        if first.get("message_type") != "SESSION_CREATED":
            why = str(first.get("message") or first.get("message_type"))
            _rest(why)
            await _send(browser, {"type": "error", "message": why})
            _log("hear", False, lang)
            return
        state = {"buf": bytearray(), "committed_at": None, "done": False}

        async def from_browser():
            while not state["done"]:
                msg = await browser.receive()
                if msg.get("type") == "websocket.disconnect":
                    state["done"] = True
                    return
                if msg.get("bytes"):
                    state["buf"] += msg["bytes"]
                    while len(state["buf"]) >= 3200:      # 0.1 s of audio per piece, like a live source
                        piece = bytes(state["buf"][:CHUNK_MAX])
                        del state["buf"][:len(piece)]
                        await intron.send(json.dumps({"message_type": "INPUT_AUDIO_CHUNK",
                                                      "audio_base_64": base64.b64encode(piece).decode()}))
                elif msg.get("text"):
                    if json.loads(msg["text"]).get("type") == "commit":
                        rest = bytes(state["buf"])
                        if rest:
                            rest += b"\0" * max(0, CHUNK_MIN - len(rest))   # Intron's minimum: pad with silence
                            await intron.send(json.dumps({"message_type": "INPUT_AUDIO_CHUNK",
                                                          "audio_base_64": base64.b64encode(rest).decode()}))
                        state["buf"].clear()
                        state["committed_at"] = time.perf_counter()
                        await intron.send(json.dumps({"message_type": "COMMIT"}))
                        return

        async def from_intron():
            async for raw in intron:
                m = json.loads(raw)
                kind = m.get("message_type")
                if kind == "PARTIAL_TRANSCRIPT":
                    await _send(browser, {"type": "partial", "text": m.get("transcript") or ""})
                elif kind == "COMMITTED_TRANSCRIPT":
                    ms = (time.perf_counter() - state["committed_at"]) * 1000 if state["committed_at"] else None
                    _log("hear", True, lang, ms=ms)   # /team speed: from "you stopped" to the final words
                    await _send(browser, {"type": "final", "text": (m.get("transcript_text") or "").strip()})
                    return
                elif kind in _ERRORS:
                    why = str(m.get("message") or kind)
                    if "no data received" in why:          # nothing was said
                        await _send(browser, {"type": "final", "text": ""})
                        return
                    _rest(why)
                    _log("hear", False, lang)
                    await _send(browser, {"type": "error", "message": why})
                    return

        up = asyncio.ensure_future(from_browser())
        try:
            await asyncio.wait_for(from_intron(), 300)   # Intron's session limit
        finally:
            state["done"] = True
            up.cancel()
    except Exception as e:  # noqa: BLE001
        _log("hear", False, lang)
        await _send(browser, {"type": "error", "message": f"{type(e).__name__}"})
    finally:
        try:
            await intron.close()
        except Exception:  # noqa: BLE001
            pass


async def _send(browser, data):
    try:
        await browser.send_text(json.dumps(data))
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- speaking (reply -> pieces -> Intron -> files)
def pieces(text):
    """The reply in pieces Intron's stream takes (10 to 100 characters), cut at sentence ends, then at commas, then
    at spaces. A piece under 10 characters joins its neighbour ("Done." + the next sentence)."""
    text = tts.speakable(text)
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        while len(sent) > TEXT_MAX:
            comma = sent.rfind(", ", 0, TEXT_MAX)
            cut = comma if comma >= 40 else sent.rfind(" ", 0, TEXT_MAX)   # a pause where the voice would pause
            cut = cut if cut >= TEXT_MIN else TEXT_MAX
            out.append(sent[:cut + 1].strip())
            sent = sent[cut + 1:].strip()
        if sent:
            out.append(sent)
    merged = []
    for p in out:
        if merged and (len(merged[-1]) < TEXT_MIN or len(p) < TEXT_MIN) and len(merged[-1]) + len(p) + 1 <= TEXT_MAX:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged


class Voice:
    """One spoken reply, made piece by piece. files[i] is set (a path, or None for no voice) and ready[i] fires as
    soon as piece i is made, so the page can play piece 1 while piece 2 is still being made."""

    def __init__(self, text, lang):
        self.lang = lang if lang in tts.INTRON_VOICES else "English"
        self.parts = pieces(text)
        self.files = [None] * len(self.parts)
        self.ready = [threading.Event() for _ in self.parts]

    def start(self):
        threading.Thread(target=self._make, daemon=True).start()
        return self

    def _done(self, i, path):
        self.files[i] = path
        self.ready[i].set()

    def _make(self):
        todo = []
        for i, part in enumerate(self.parts):      # already said before: from the voice cache, free and at once
            path = tts.cached(part, self.lang)
            if path:
                self._done(i, path)
            else:
                todo.append(i)
        if not todo:
            return
        stream_ok = (tts.backend() == "intron" and _websockets() is not None and time.time() >= _DOWN["until"]
                     and all(len(self.parts[i]) >= TEXT_MIN for i in todo))
        if stream_ok:
            try:
                asyncio.run(self._stream(todo))
                todo = [i for i in todo if not self.ready[i].is_set()]
            except Exception as e:  # noqa: BLE001  (the old way below makes what is left)
                print(f"Intron voice stream failed: {type(e).__name__}: {e}")
                _log("voice", False, self.lang)
        for i in todo:                              # one piece at a time, in order (the page waits for them in order)
            out = tts.speak(self.parts[i], self.lang)
            self._done(i, out["path"] if out else None)

    async def _stream(self, todo):
        ws_lib = _websockets()
        lang, accent = tts.INTRON_VOICES[self.lang]
        accent = os.getenv(f"INTRON_ACCENT_{self.lang.upper()}") or tts._GOOD_ACCENT.get(self.lang) or accent
        url = (f"{TTS_WS}?voice_accent={accent}&voice_gender={os.getenv('INTRON_GENDER', 'female')}"
               f"&voice_language={lang}&output_audio_format=wav")
        t0 = time.perf_counter()
        async with ws_lib.connect(url, additional_headers=_head(), open_timeout=8, max_size=2 ** 24) as ws:
            first = json.loads(await asyncio.wait_for(ws.recv(), 8))
            if first.get("message_type") != "SESSION_CREATED":
                why = str(first.get("message") or first.get("message_type"))
                _rest(why)
                raise RuntimeError(why)
            for n, i in enumerate(todo, 1):
                await ws.send(json.dumps({"message_type": "INPUT_TEXT_CHUNK", "text": self.parts[i], "ack_id": n}))
                ack = json.loads(await asyncio.wait_for(ws.recv(), 8))
                if ack.get("message_type") in _ERRORS:
                    raise RuntimeError(str(ack.get("message") or ack.get("message_type")))
            for n, i in enumerate(todo, 1):
                end = time.time() + 40
                while True:
                    await ws.send(json.dumps({"message_type": "FETCH_AUDIO_CHUNK", "chunk_id": n}))
                    m = json.loads(await asyncio.wait_for(ws.recv(), 20))
                    if m.get("message_type") in _ERRORS:
                        raise RuntimeError(str(m.get("message") or m.get("message_type")))
                    status = m.get("processing_status") or m.get("processing_staus")   # (the docs spell it both ways)
                    if status == "READY" and m.get("audio_base_64"):
                        break
                    if time.time() > end:
                        raise TimeoutError(f"piece {n} not ready")
                    await asyncio.sleep(0.12)
                audio = base64.b64decode(m["audio_base_64"])
                path = tts.keep(self.parts[i], self.lang, audio, m.get("extension") or ".wav")
                if n == 1:
                    _log("voice", True, self.lang, ms=(time.perf_counter() - t0) * 1000)   # /team: first sound
                self._done(i, path)
            await ws.send(json.dumps({"message_type": "COMMIT"}))
            try:   # Intron saves the session on COMMIT: wait for its summary (every piece is already playing)
                await asyncio.wait_for(ws.recv(), 3)
            except Exception:  # noqa: BLE001
                pass
