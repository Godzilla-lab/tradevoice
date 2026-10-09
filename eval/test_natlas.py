"""N-ATLaS is the main brain: tried first, with the model card's settings and worked examples, and the backups
take over when it is down. No GPU or network: a fake server stands in for N-ATLaS and the cloud.

python eval/test_natlas.py
"""
import datetime as dt
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
for k in ("NVIDIA_API_KEY", "LOCAL_LLM_URL", "NATLAS_URL", "NATLAS_KEY", "LLM_SHOTS_FOR"):
    os.environ.pop(k, None)
import extract  # noqa: E402
import llm  # noqa: E402

CALLS = []      # (model name as sent, kwargs)
DOWN = set()    # served names that fail
REPLY = {}      # served name -> reply text


class Err(Exception):
    def __init__(self, status):
        super().__init__(f"status {status}")
        self.status_code = status


def fake_client(kind, timeout, retries=0, model=None):
    def create(**kw):
        CALLS.append((kw["model"], kw))
        if kw["model"] in DOWN:
            raise Err(401 if kw["model"] == "natlas" else 503)
        text = REPLY.get(kw["model"], '{"ok": true}')
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


llm._client = fake_client
import natlas_watch  # noqa: E402

natlas_watch._probe = lambda part: (False, "test")   # the background check after a failure: no network in tests
passed = total = 0


def check(name, cond):
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"{'✓' if cond else '✗'} {name}")


def reset(env=None, down=(), models=("cloud/a", "cloud/b")):
    CALLS.clear()
    DOWN.clear()
    DOWN.update(down)
    REPLY.clear()
    llm._working.clear()
    llm._resting.clear()
    llm.LLM_MODELS[:] = list(models)
    for k in ("NVIDIA_API_KEY", "NATLAS_URL", "LOCAL_LLM_URL"):
        os.environ.pop(k, None)
    os.environ.update(env or {})


SYS = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
SHOTS = [("u1", "a1"), ("u2", "a2")]
BOTH = {"NVIDIA_API_KEY": "x", "NATLAS_URL": "http://natlas/v1"}

# 1. N-ATLaS first, with the card's settings
reset(BOTH)
out, model = llm.chat(SYS, shots=SHOTS)
name, kw = CALLS[0]
check("N-ATLaS is tried first when NATLAS_URL is set", name == "natlas" and len(CALLS) == 1)
check("answer is labelled as N-ATLaS (for /team engine share)", model == "natlas:NCAIR1/N-ATLaS"
      and llm.is_natlas(model))
check("card settings: temperature 0.1, repetition penalty 1.12", kw["temperature"] == 0.1
      and kw["extra_body"]["repetition_penalty"] == 1.12)
check("chat template gets today's date_string", kw["extra_body"]["chat_template_kwargs"]["date_string"])
roles = [m["role"] for m in kw["messages"]]
check("worked examples go between the system prompt and the question",
      roles == ["system", "user", "assistant", "user", "assistant", "user"]
      and kw["messages"][1]["content"] == "u1" and kw["messages"][-1]["content"] == "hi")

# 2. N-ATLaS down (any error, even auth) -> the backups answer
reset(BOTH, down={"natlas"})
out, model = llm.chat(SYS, shots=SHOTS)
check("N-ATLaS down (401) -> next model answers instead of failing", model == "cloud/a"
      and [c[0] for c in CALLS] == ["natlas", "cloud/a"])
check("cloud models don't get the examples or N-ATLaS settings",
      len(CALLS[1][1]["messages"]) == 2 and "extra_body" not in CALLS[1][1] and CALLS[1][1]["temperature"] == 0.0)

# 3. after a fallback, N-ATLaS still leads once it is back (and its rest period is over)
DOWN.clear()
llm._resting.clear()
out, model = llm.chat(SYS)
check("N-ATLaS leads again after recovering (not pushed behind the last good backup)", model.startswith("natlas"))

# 4. only N-ATLaS configured (no NVIDIA key)
reset({"NATLAS_URL": "http://natlas/v1"})
check("N-ATLaS alone counts as 'AI available'", llm.available() and not llm.available("vision"))
out, model = llm.chat(SYS)
check("without NVIDIA key only N-ATLaS is tried", [c[0] for c in CALLS] == ["natlas"])

# 5. not configured -> never tried
reset({"NVIDIA_API_KEY": "x"}, models=("natlas", "cloud/a"))
out, model = llm.chat(SYS)
check("no NATLAS_URL -> N-ATLaS skipped even if listed", model == "cloud/a" and "natlas" not in [c[0] for c in CALLS])

# 6. vision is never sent to N-ATLaS (text-only model)
reset(BOTH)
llm.VISION_MODELS[:] = ["cloud/vision"]
out, model = llm.chat([{"role": "user", "content": "photo"}], kind="vision")
check("photos go to the vision models, not N-ATLaS", model == "cloud/vision")

# 7. benchmarks can give everyone the examples, or nobody
reset(BOTH, down={"natlas"})
llm.SHOTS_FOR = "all"
llm.chat(SYS, shots=SHOTS)
check("LLM_SHOTS_FOR=all gives the backup the examples too (fair benchmark)", len(CALLS[1][1]["messages"]) == 6)
reset(BOTH)
llm.SHOTS_FOR = ""
llm.chat(SYS, shots=SHOTS)
check("LLM_SHOTS_FOR='' = zero-shot N-ATLaS", len(CALLS[0][1]["messages"]) == 2)
llm.SHOTS_FOR = "natlas"

# 8. end to end: extract() records the engine, and our guards still check N-ATLaS
TODAY = dt.date(2026, 9, 27)
reset({"NATLAS_URL": "http://natlas/v1"})
REPLY["natlas"] = json.dumps({"type": "credit_sale", "item": "rice", "quantity": 2, "unit": "bag", "amount": 20000,
                              "customer": "Mama Ada", "due_date": None, "confidence": 0.9, "note": None})
rec, meta = extract.extract("Sold 2 bags of rice to Mama Ada for 20k, she will pay later", today=TODAY)
check("extract() says N-ATLaS made the record", llm.is_natlas(meta["engine"]) and rec["amount"] == 20000)
check("extract() sends N-ATLaS the worked examples (every language, one with no amount)",
      len(CALLS[0][1]["messages"]) == 2 + 2 * len(extract.SHOTS)
      and any(json.loads(a)["amount"] is None for _, a in extract.SHOTS))
REPLY["natlas"] = json.dumps({"type": "sale", "quantity": 4, "unit": "bag", "amount": 7500, "each": True})
rec, meta = extract.extract("Sold 4 bags of rice, 7,500 each", today=TODAY)
check("model reports a per-unit price, CODE multiplies (4 x 7,500 = 30,000)", rec["amount"] == 30000)
REPLY["natlas"] = json.dumps({"type": "sale", "quantity": 4, "unit": "bag", "amount": 3500, "each": False})
rec, meta = extract.extract("Sold 4 bags of rice for 3,500", today=TODAY)
check("a total stays a total (no 'each' -> no multiplying)", rec["amount"] == 3500)
REPLY["natlas"] = json.dumps({"type": "sale", "amount": 5000, "customer": "Mama Ada"})
rec, meta = extract.extract("Mama Ada never pay the 5000 for rice", today=TODAY)
check("rules still overrule N-ATLaS ('never pay' = credit, not a sale)", rec["type"] == "credit_sale")
REPLY["natlas"] = "Sorry, I can't help with that."
rec, meta = extract.extract("Sold beans for 3000", today=TODAY)
check("N-ATLaS gives no JSON -> offline rules, never a crash", meta["engine"].startswith("rules")
      and rec["amount"] == 3000)

# 9. the worked examples are valid records, and their amounts were said in their sentences
ok = True
for text, answer in extract.SHOTS:
    a = json.loads(answer)
    ok &= a["type"] in extract.TYPES and a["customer"] in (None,) + tuple([a["customer"]] if a["customer"]
                                                                            and a["customer"] in text else [])
check("worked examples are valid records with names that appear in the sentence", ok)

# 10. health watch: alerts the team once after 2 fails, once when back; quiet at night
sent, answers = [], []
natlas_watch.check = lambda: answers.pop(0)
for a in (True, False, False, False, True):
    answers.append(a)
    natlas_watch.step(send=sent.append)
check("one failed check -> no alert yet; 2 in a row -> ONE team alert; back -> one 'answering again'",
      len(sent) == 2 and "not answering" in sent[0] and "again" in sent[1])
check("health checks only in market hours (Nigeria time)",
      natlas_watch._market_hours(dt.datetime(2026, 10, 6, 9)) and not natlas_watch._market_hours(
          dt.datetime(2026, 10, 6, 22)) and not natlas_watch._market_hours(dt.datetime(2026, 10, 6, 3)))

# 10a. Talk opened: wake both servers; a brain that doesn't answer in 3 s is asleep -> backups answer until it's up
import time as _time  # noqa: E402

import requests as _rq  # noqa: E402

_real_get, PINGS = _rq.get, []


def _slow_get(url, timeout=None, headers=None):
    PINGS.append(url)
    if url.endswith("/models"):
        _time.sleep(3.6)      # a sleeping GPU starting up
    return type("R", (), {"status_code": 200, "text": "natlas"})()


_rq.get = _slow_get
os.environ.update(NATLAS_URL="https://natlas.test/v1", NATLAS_ASR_URL="https://asr.test")
llm._resting.pop("natlas", None)
natlas_watch._WOKEN["at"] = 0
first = natlas_watch.wake()
_time.sleep(3.3)
asleep = llm._resting.get("natlas", 0) > _time.time()
again = natlas_watch.wake()
_time.sleep(0.8)
check("Talk opened: both N-ATLaS servers are pinged at once (brain + speech)",
      first and {u.split("/")[-1] for u in PINGS} == {"models", "health"})
check("…a brain that takes over 3 s is starting up: backups answer meanwhile (no 20 s wait per message)", asleep)
check("…and N-ATLaS leads again as soon as it answers", "natlas" not in llm._resting)
check("…at most one wake-up a minute", again is False)
_rq.get = _real_get

# 10b. N-ATLaS calls a book question "other": the word lists still route it as a question (live bug, 2 Oct)
import askbook  # noqa: E402

reset({"NATLAS_URL": "http://natlas/v1"})
REPLY["natlas"] = json.dumps({"kind": "other", "what": "owed_to_me", "customer": None, "period": "all"})
q, _ = askbook.parse("Who owes me?")
check("'Who owes me?' stays a book question even when N-ATLaS says 'other'", q["kind"] == "query"
      and q["what"] == "owed_to_me")

# 11. N-ATLaS speech: right model per language, loops and silence rejected, Intron/Spitch not used as backups
import asr  # noqa: E402
import tempfile  # noqa: E402

POSTS = []


class FakeResp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


HEARD = {}


class _Timeout(Exception):
    pass


class _ConnErr(Exception):
    pass


COLD, GETS = {"left": 0}, []


def _post(url, files, data, headers, timeout):
    POSTS.append((url, data, timeout))
    if COLD["left"] > 0:   # a sleeping server: the first try times out
        COLD["left"] -= 1
        raise _Timeout()
    return FakeResp(HEARD)


fake_requests = SimpleNamespace(post=_post, get=lambda url, headers, timeout: GETS.append((url, timeout)),
                                exceptions=SimpleNamespace(Timeout=_Timeout, ConnectionError=_ConnErr))
sys.modules["requests"] = fake_requests
os.environ.update({"NATLAS_ASR_URL": "http://asr", "INTRON_API_KEY": "x"})
os.environ.pop("ASR_ENGINE", None)
asr._intron_transcribe = lambda *a, **k: {"text": "intron heard it", "engine": "intron"}
note = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
note.write(b"fake")
note.close()
HEARD.update(text="Mo ta àpò ìrẹsì méjì fún Iya Bisi", model="NCAIR1/Yoruba-ASR", seconds=4.0)
out = asr.transcribe(note.name, "Yoruba", {"names": ["Iya Bisi"], "items": ["rice"]})
check("Yoruba voice note -> NCAIR1/Yoruba-ASR, with the trader's names as hints",
      POSTS[-1][1]["lang"] == "yoruba" and "Iya Bisi" in POSTS[-1][1]["prompt"] and out["engine"].startswith("natlas"))
asr.transcribe(note.name, "English / Pidgin")
check("English/Pidgin -> NigerianAccentedEnglish model", POSTS[-1][1]["lang"] == "english")
HEARD.clear()
HEARD.update(text="kaka nan, kaka nan, kaka nan, kaka nan.", model="NCAIR1/Hausa-ASR", seconds=2.0)
try:
    asr.transcribe(note.name, "Hausa")
    check("a looping transcript is rejected (never read amounts from it)", False)
except RuntimeError as e:
    check("a looping transcript is rejected, and Intron is NOT used as a backup", "repeated" in str(e))
HEARD.clear()
HEARD.update(text="", no_speech=True, seconds=2.0)
try:
    asr.transcribe(note.name, "Igbo")
    check("silence -> 'no speech', not invented words", False)
except RuntimeError as e:
    check("silence -> 'no speech', not invented words", "no speech" in str(e))
HEARD.clear()
HEARD.update(text="Iya Bisi paid 5000", model="NCAIR1/NigerianAccentedEnglish", seconds=2.0)
COLD["left"], n = 1, len(POSTS)
out = asr.transcribe(note.name, "English / Pidgin")
check("asleep, Intron set: one short try, then Intron hears this note (no 4-minute wait)",
      out["engine"] == "intron" and len(POSTS) == n + 1 and POSTS[-1][2] <= 15)
out = asr.transcribe(note.name, "English / Pidgin")
check("…and the next note goes straight to Intron while N-ATLaS hearing is marked down",
      out["engine"] == "intron" and len(POSTS) == n + 1)
llm._resting.pop("natlas_asr", None)
os.environ["ASR_DOWN_BACKUP"] = "none"
COLD["left"], n = 1, len(POSTS)
out = asr.transcribe(note.name, "English / Pidgin")
check("asleep, no backup: the first try times out -> it wakes the server (/health) and tries once more with a long wait",
      out["text"] == "Iya Bisi paid 5000" and len(POSTS) == n + 2 and GETS and GETS[-1][0].endswith("/health")
      and POSTS[-1][2] >= 240 > POSTS[-2][2])
os.environ.pop("ASR_DOWN_BACKUP")
os.environ["ASR_ENGINE"] = "intron"
check("tests can still pick Intron to compare (ASR_ENGINE=intron)",
      asr.transcribe(note.name, "Igbo")["engine"] == "intron")
os.remove(note.name)

print(f"\n{passed}/{total} N-ATLaS checks pass")
sys.exit(0 if passed == total else 1)
