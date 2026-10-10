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
    """Live talk hears with Intron when a key is set and not resting, LIVE_HEARING isn't "natlas" and Intron isn't
    resting."""
    import intron_keys
    return (intron_keys.pick() is not None and os.getenv("LIVE_HEARING", "intron") == "intron"
            and _websockets() is not None and time.time() >= _DOWN["until"])


def _head():
    import intron_keys
    key = intron_keys.pick()
    return intron_keys.head(key) if key else {}


async def _connect(url, max_size):
    """A WebSocket to Intron that has said SESSION_CREATED, and the key it used. A key Intron refuses (auth, credit,
    quota) rests and the next key is tried at once (intron_keys.py). Raises RuntimeError(why) when none works."""
    import intron_keys
    key, why = intron_keys.pick(), "no Intron key left (all refused: credit or the key)"
    while key:
        ws = await _websockets().connect(url, additional_headers=intron_keys.head(key), open_timeout=8, max_size=max_size)
        first = json.loads(await asyncio.wait_for(ws.recv(), 8))
        if first.get("message_type") == "SESSION_CREATED":
            intron_keys.ok(key[0])
            return ws, key
        why = str(first.get("message") or first.get("message_type"))
        await ws.close()
        keyed = intron_keys.refusal(why) or (first.get("message_type") in ("AUTHENTICATION_ERROR", "QUOTA_EXCEEDED")
                                             and not intron_keys.temporary(why))
        if not keyed:   # e.g. "language not available, please wait 30 seconds": the key is fine; this turn only
            break
        key = intron_keys.refused(key[0], why)
    _rest(why)
    raise RuntimeError(why)


def _rest(why):
    """Every key refused: live talk rests 10 minutes (the old hearing is used meanwhile)."""
    import intron_keys
    if intron_keys.refusal(why) and not intron_keys.pick():
        _DOWN["until"], _DOWN["why"] = time.time() + 600, why[:200]


def _refused_now(key, why):
    """A refusal in the middle of a session: that key rests, the next turn uses the next key."""
    import intron_keys
    if key and intron_keys.refusal(why):
        intron_keys.refused(key[0], why)
    _rest(why)


def _log(kind, ok, lang, ms=None, engine="intron-stream"):
    try:
        import events
        events.log(kind, engine=engine, ok=ok, lang=lang, ms=ms)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- hearing (browser -> us -> Intron -> us -> browser)
async def relay_hearing(browser, lang, collect=False, on_commit=None):
    """browser: a Starlette WebSocket. It sends audio as binary frames and {"type": "commit"} when the trader has
    finished; it gets {"type": "partial"|"final"|"error", "text"|"message"}. One turn per connection.
    on_commit(words): called when the trader stops, with the words heard so far (live talk starts reading them while
    Intron finishes the final words). Returns {"text": final words, "pcm": the audio} (pcm only with collect=True: a
    trader who said yes to training)."""
    got = {"text": "", "pcm": bytearray() if collect else None}
    ws_lib = _websockets()
    code = STT_LANG.get(lang, STT_LANG["English"])
    url = f"{STT_WS}?sample_rate=16000&bit_rate=16&num_channels=1&use_language_asr_input={code}"
    try:
        intron, key = await _connect(url, 2 ** 22)
    except RuntimeError as e:   # Intron answered, but no key was accepted
        await _send(browser, {"type": "error", "message": str(e)})
        _log("hear", False, lang)
        return got
    except Exception as e:  # noqa: BLE001
        await _send(browser, {"type": "error", "message": f"connect: {type(e).__name__}"})
        _log("hear", False, lang)
        return got
    try:
        state = {"buf": bytearray(), "committed_at": None, "done": False, "partial": ""}

        async def from_browser():
            while not state["done"]:
                msg = await browser.receive()
                if msg.get("type") == "websocket.disconnect":
                    state["done"] = True
                    return
                if msg.get("bytes"):
                    state["buf"] += msg["bytes"]
                    if got["pcm"] is not None:
                        got["pcm"] += msg["bytes"]
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
                        prewarm(lang)   # the reply's voice session opens now, not after the reply is written
                        if on_commit and state["partial"]:
                            try:
                                on_commit(state["partial"])
                            except Exception as e:  # noqa: BLE001  (only a head start; never in the way)
                                print(f"live talk early reading not started: {type(e).__name__}")
                        return

        async def from_intron():
            async for raw in intron:
                m = json.loads(raw)
                kind = m.get("message_type")
                if kind == "PARTIAL_TRANSCRIPT":
                    state["partial"] = (m.get("transcript") or "").strip() or state["partial"]
                    await _send(browser, {"type": "partial", "text": m.get("transcript") or ""})
                elif kind == "COMMITTED_TRANSCRIPT":
                    ms = (time.perf_counter() - state["committed_at"]) * 1000 if state["committed_at"] else None
                    got["text"] = (m.get("transcript_text") or "").strip()
                    await _send(browser, {"type": "final", "text": got["text"]})   # the page first, the log after
                    _log("hear", True, lang, ms=ms)   # /team speed: from "you stopped" to the final words
                    return
                elif kind in _ERRORS:
                    why = str(m.get("message") or kind)
                    if "no data received" in why:          # nothing was said
                        await _send(browser, {"type": "final", "text": ""})
                        return
                    _refused_now(key, why)
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
    return got


async def _send(browser, data):
    try:
        await browser.send_text(json.dumps(data))
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- speaking (reply -> pieces -> Intron -> files)
def pieces(text, lang="English"):
    """The reply in pieces Intron's stream takes (10 to 100 characters), cut at sentence ends, then at commas, then
    at spaces. A piece under 10 characters joins its neighbour ("Done." + the next sentence)."""
    text = tts.speakable(text, lang)
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


# The voice streams run on one event loop of their own, so a session can be opened before the reply exists (when the
# trader stops talking) and used by the reply a moment later: the connection and Intron's session are already up.
_LOOP = {"loop": None}
_LOOP_LOCK = threading.Lock()
READY = {}            # reply language -> (future of an open session, when it was asked for)
READY_FOR = float(os.getenv("INTRON_TTS_READY_SECONDS", "25"))   # an unused session is closed after this


def _loop():
    with _LOOP_LOCK:
        if _LOOP["loop"] is None:
            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, daemon=True, name="intron-voice").start()
            _LOOP["loop"] = loop
    return _LOOP["loop"]


def _voice_lang(lang):
    return lang if lang in tts.INTRON_VOICES else "English"


def stream_ok():
    import intron_keys
    return (tts.backend() == "intron" and intron_keys.pick() is not None and _websockets() is not None
            and time.time() >= _DOWN["until"])


async def _open_voice(lang):
    """A new Intron text-to-speech session for this language (connected, SESSION_CREATED)."""
    name = _voice_lang(lang)
    code, accent = tts.INTRON_VOICES[name]
    accent = os.getenv(f"INTRON_ACCENT_{name.upper()}") or tts._GOOD_ACCENT.get(name) or accent
    url = (f"{TTS_WS}?voice_accent={accent}&voice_gender={os.getenv('INTRON_GENDER', 'female')}"
           f"&voice_language={code}&output_audio_format=wav")
    ws, _ = await _connect(url, 2 ** 24)
    return ws


def prewarm(lang):
    """Open the reply's voice session ahead of time (live talk: when the trader stops talking). Never raises."""
    try:
        if not stream_ok():
            return
        lang, now = _voice_lang(lang), time.time()
        for k, (fut, at) in list(READY.items()):   # sessions nobody used: closed
            if now - at > READY_FOR:
                READY.pop(k, None)
                fut.add_done_callback(lambda f: f.exception() is None and asyncio.run_coroutine_threadsafe(
                    f.result().close(), _loop()))
        if lang not in READY:
            READY[lang] = (asyncio.run_coroutine_threadsafe(_open_voice(lang), _loop()), now)
    except Exception as e:  # noqa: BLE001
        print(f"voice session not opened early: {type(e).__name__}: {e}")


async def _session(lang):
    """The session opened early for this language if there is a fresh one, else a new one."""
    got = READY.pop(_voice_lang(lang), None)
    if got and time.time() - got[1] <= READY_FOR:
        try:
            return await asyncio.wrap_future(got[0]), True
        except Exception:  # noqa: BLE001  (it failed to open: open a new one below)
            pass
    return await _open_voice(lang), False


class Voice:
    """One spoken reply, made piece by piece. files[i] is set (a path, or None for no voice) and ready[i] fires as
    soon as piece i is made, so the page can play piece 1 while piece 2 is still being made."""

    def __init__(self, text, lang):
        self.lang = _voice_lang(lang)
        self.parts = pieces(text, self.lang)
        self.files = [None] * len(self.parts)
        self.ready = [threading.Event() for _ in self.parts]
        self.used_ready = False   # the session opened when the trader stopped talking was used

    def start(self):
        threading.Thread(target=self._make, daemon=True).start()
        return self

    def _done(self, i, path):
        self.files[i] = tts.small(path) if path else None   # MP3 for the phone: a fraction of the WAV's size
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
        if stream_ok() and all(len(self.parts[i]) >= TEXT_MIN for i in todo):
            try:
                asyncio.run_coroutine_threadsafe(self._stream(todo), _loop()).result(timeout=120)
                todo = [i for i in todo if not self.ready[i].is_set()]
            except Exception as e:  # noqa: BLE001  (the old way below makes what is left)
                print(f"Intron voice stream failed: {type(e).__name__}: {e}")
                _log("voice", False, self.lang)
        for i in todo:                              # one piece at a time, in order (the page waits for them in order)
            out = tts.speak(self.parts[i], self.lang)
            self._done(i, out["path"] if out else None)

    async def _stream(self, todo):
        t0 = time.perf_counter()
        ws, early = await _session(self.lang)
        self.used_ready = early
        try:
            try:
                await self._send_text(ws, todo)
            except Exception:  # noqa: BLE001
                if not early:
                    raise
                await ws.close()                    # the early session had gone stale: one fresh try
                ws = await _open_voice(self.lang)
                await self._send_text(ws, todo)
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
                    await asyncio.sleep(0.08)
                audio = base64.b64decode(m["audio_base_64"])
                path = tts.keep(self.parts[i], self.lang, audio, m.get("extension") or ".wav")
                self._done(i, path)
                if n == 1:
                    _log("voice", True, self.lang, ms=(time.perf_counter() - t0) * 1000,
                         engine="intron-stream" + (" (ready session)" if early else ""))   # /team: first sound
            await ws.send(json.dumps({"message_type": "COMMIT"}))
            try:   # Intron saves the session on COMMIT: wait for its summary (every piece is already playing)
                await asyncio.wait_for(ws.recv(), 3)
            except Exception:  # noqa: BLE001
                pass
        finally:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass

    async def _send_text(self, ws, todo):
        """Every piece at once, then the acknowledgements (one round trip, not one per piece): Intron starts making
        piece 1 the moment it arrives."""
        for n, i in enumerate(todo, 1):
            await ws.send(json.dumps({"message_type": "INPUT_TEXT_CHUNK", "text": self.parts[i], "ack_id": n}))
        for _ in todo:
            ack = json.loads(await asyncio.wait_for(ws.recv(), 8))
            if ack.get("message_type") in _ERRORS:
                raise RuntimeError(str(ack.get("message") or ack.get("message_type")))
