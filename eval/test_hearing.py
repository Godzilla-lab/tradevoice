"""Speech fixes (ROADMAP Part 5): light audio prep, two hearing models merged by N-ATLaS (amounts only if heard),
and asking again for just the unclear part. No keys, no models: the servers are faked.

python eval/test_hearing.py
"""
import json
import os
import sys
import tempfile
from types import SimpleNamespace

os.environ["TV_NO_DOTENV"] = "1"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["BOOKS_DIR"] = tempfile.mkdtemp()
os.environ["ACCOUNTS_DB"] = os.path.join(tempfile.mkdtemp(), "a.db")
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith("LOCAL_") or k.startswith("NATLAS") or k.startswith("ASR_"):
        os.environ.pop(k)
os.environ.update(TRADEVOICE_ADMIN="0", AUTO_REMINDERS="0", AUTH_REQUIRED="0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import numpy as np  # noqa: E402

import converse  # noqa: E402
import hearing  # noqa: E402
import ledger  # noqa: E402
import llm  # noqa: E402
import speech_prep  # noqa: E402

passed = total = 0


def check(name, cond, got=""):
    global passed, total
    total += 1
    passed += bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  got: {got!r}"))


# 1. light audio prep: trim the quiet ends, level the volume, never clip, leave silence alone
sr = 16000
t = np.arange(sr) / sr
voice = (0.01 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)          # a quiet phone, 1 s of "voice"
note = np.concatenate([np.zeros(2 * sr, np.float32), voice, np.zeros(2 * sr, np.float32)])
out = speech_prep.prepare(note)
check("prep: 2 s of quiet at each end cut (about 0.25 s kept each side)", 1.4 * sr <= len(out) <= 1.6 * sr, len(out))
check("prep: a quiet voice is lifted (at most +20 dB)", 0.05 < float(np.abs(out).max()) <= 0.1 + 1e-3,
      float(np.abs(out).max()))
loud = np.concatenate([np.zeros(sr, np.float32), (0.95 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)])
check("prep: a loud voice is never clipped", float(np.abs(speech_prep.prepare(loud)).max()) <= 0.99)
silence = np.zeros(3 * sr, np.float32)
check("prep: silence is left as it is (the silence check rejects it)", np.array_equal(speech_prep.prepare(silence), silence))
check("prep: a very short note is left as it is", len(speech_prep.prepare(voice[:4000])) == 4000)

# 2. word confidence from the model's token probabilities
pieces = [("ĠMama", 0.95), ("ĠTun", 0.9), ("de", 0.3), ("Ġpaid", 0.97), ("Ġ50", 0.2), ("k", 0.8)]
unsure, mean = speech_prep.unsure_words(pieces, lambda toks: "".join(toks).replace("Ġ", " "), 0.4)
check("unsure words: a word is as sure as its least sure piece", [u["word"] for u in unsure] == ["Tunde", "50k"],
      unsure)
check("…and the whole note gets a mean probability", abs(mean - 0.6867) < 0.01, mean)

# 3. merging two transcripts with N-ATLaS, with the guards
VOCAB = {"names": ["Iya Bisi", "Mama Tunde"], "items": ["rice"]}
REPLY, CALLS = {"text": ""}, []


def fake_chat(messages, **k):
    CALLS.append((messages[0]["content"], k))
    if REPLY.get("raise"):
        raise TimeoutError("slow")
    return REPLY["text"], "natlas"


llm.chat = fake_chat
A, B = "Iya Bisi ra apo iresi meji ni 90000", "Iya Bisi bought two bags of rice 90000"
check("merge: no second transcript -> the first", hearing.merge(A, "", "Yoruba") == (A, "no_b"))
check("merge: the same words -> no AI call", hearing.merge(A, A + ".", "Yoruba") == (A, "same") and not CALLS)
check("merge: N-ATLaS not set up -> the language model's words", hearing.merge(A, B, "Yoruba")[1] == "asleep")
os.environ["NATLAS_URL"] = "http://natlas/v1"
llm._resting["natlas"] = 9e12
check("merge: N-ATLaS asleep -> no waiting, the language model's words", hearing.merge(A, B, "Yoruba") == (A, "asleep"))
llm._resting.pop("natlas")
REPLY["text"] = "Iya Bisi ra apo rice meji ni 90000"
got = hearing.merge(A, B, "Yoruba", VOCAB)
check("merge: N-ATLaS writes one sentence", got == ("Iya Bisi ra apo rice meji ni 90000", "merged"), got)
check("…given both transcripts and the book's names, N-ATLaS only, short wait",
      A in CALLS[-1][0] and B in CALLS[-1][0] and "Mama Tunde" in CALLS[-1][0]
      and CALLS[-1][1].get("models") == ["natlas"] and CALLS[-1][1].get("deadline") <= 8)
REPLY["text"] = "Iya Bisi ra apo iresi meji ni 900000"
check("guard: an amount neither model heard is refused", hearing.merge(A, B, "Yoruba", VOCAB) == (A, "amount"))
REPLY["text"] = A + " and she also bought beans and oil and pepper and tomatoes and onions for the party on Sunday"
check("guard: a merge much longer than both (made-up words) is refused", hearing.merge(A, B, "Yoruba")[1] == "long")
REPLY["raise"] = True
check("guard: N-ATLaS slow or failing -> the language model's words", hearing.merge(A, B, "Yoruba") == (A, "failed"))
REPLY.pop("raise")

# 4. what to ask again
c = hearing.check({"text": "Mama Ngozi took rice 5000"}, {"text": "Mama Ngozi took rice 50000"})
check("check: the two models heard different amounts", c == {"amounts": [5000.0, 50000.0]}, c)
c = hearing.check({"text": "Mama Ngozi took rice 5000", "unsure": [{"word": "5000", "p": 0.2}]})
check("check: the model wasn't sure of the amount", c and c.get("unsure_amount"), c)
c = hearing.check({"text": "Adaeze took rice 5000", "unsure": [{"word": "Adaeze,", "p": 0.3}]})
check("check: a word it wasn't sure of (maybe a name)", c and c.get("unsure_words") == ["adaeze"], c)
c = hearing.check({"text": "Iya Bisi ra iresi 5000"}, {"text": "Iya Bisi rice 5000", "unsure": [{"word": "ra", "p": .1}]},
                  "Iya Bisi ra iresi 5000")
check("check: only words in what the chat reads count; the same amount twice is fine", c == {"unsure_words": ["ra"]}, c)
check("check: nothing unclear -> nothing to ask", hearing.check({"text": "Mama Ngozi took rice 5000"}) is None)

# 5. the hearing server call: prep on, the English model too for Yoruba / Hausa / Igbo, merged
import asr  # noqa: E402

POSTS, HEARD = [], {}


class FakeResp:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def _post(url, files, data, headers, timeout):
    POSTS.append(dict(data))
    return FakeResp(HEARD)


sys.modules["requests"] = SimpleNamespace(post=_post, get=lambda *a, **k: None,
                                          exceptions=SimpleNamespace(Timeout=TimeoutError, ConnectionError=OSError))
os.environ.update(NATLAS_ASR_URL="http://asr", NATLAS_KEY="k")
f = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
f.write(b"fake")
f.close()
HEARD.clear()
HEARD.update(text=A, model="NCAIR1/Yoruba-ASR", seconds=4, unsure=[],
             also={"text": B, "model": "NCAIR1/NigerianAccentedEnglish", "unsure": []})
REPLY["text"] = "Iya Bisi ra apo rice meji ni 90000"
out = asr.transcribe(f.name, "Yoruba", VOCAB)
check("Yoruba note: light prep on, the English model asked for too", POSTS[-1].get("prep") == "1"
      and POSTS[-1].get("also") == "english" and POSTS[-1].get("lang") == "yoruba", POSTS[-1])
check("…the merged words are used, and both transcripts are kept for the record",
      out["text"] == REPLY["text"] and out["heard"] == [A, B] and out["engine"].endswith("+english:merged"), out)
HEARD.clear()
HEARD.update(text="Mama Ngozi took rice 5000", model="NCAIR1/NigerianAccentedEnglish", seconds=3,
             unsure=[{"word": "5000", "p": 0.21}])
out = asr.transcribe(f.name, "English / Pidgin", VOCAB)
check("English note: one model (no 'also'), and the unsure amount goes to the chat",
      POSTS[-1].get("also") == "" and out.get("check", {}).get("unsure_amount"), (POSTS[-1], out))
os.environ.update(NATLAS_ASR_PREP="0", NATLAS_ASR_MERGE="0")
asr.transcribe(f.name, "Hausa", VOCAB)
check("both can be switched off (A/B test): NATLAS_ASR_PREP=0, NATLAS_ASR_MERGE=0",
      POSTS[-1].get("prep") == "0" and POSTS[-1].get("also") == "", POSTS[-1])
os.environ.pop("NATLAS_ASR_PREP")
os.environ.pop("NATLAS_ASR_MERGE")
HEARD.clear()
HEARD.update(text=A, model="NCAIR1/Yoruba-ASR", seconds=4,
             also={"text": "ati ati ati ati ati ati ati ati ati ati ati ati ati ati ati ati ati ati ati ati", "model": "x"})
out = asr.transcribe(f.name, "Yoruba", VOCAB)
check("a second model stuck in a loop is ignored", out["text"] == A and "heard" not in out, out)
HEARD.clear()
HEARD.update(text=A, model="NCAIR1/Yoruba-ASR", seconds=4)
out = asr.transcribe(f.name, "Yoruba", VOCAB)
check("an older hearing server (no 'also' in its answer) still works", out["text"] == A, out)

# 6. the chat asks again for just the unclear part (offline rules understand the words here)
for k in ("NATLAS_URL", "NATLAS_ASR_URL"):
    os.environ.pop(k)
st = converse.new_state()
st["heard_check"] = {"amounts": [5000.0, 50000.0]}
r = converse.reply("Mama Ngozi bought rice for 5000 on credit", st)
check("two amounts heard: 'I heard ₦5,000 or ₦50,000. Say the amount again.'",
      r["text"] == "I heard ₦5,000 or ₦50,000. Say the amount again.", r["text"])
check("…said with the amounts in words", "fifty thousand naira" in r["spoken"], r["spoken"])
check("…the draft waits, its amount marked", st["pending"].get("_reask") == "amount")
r = converse.reply("fifty thousand", st)
check("…the amount said again fixes it, the rest is kept",
      st["pending"]["amount"] == 50000 and st["pending"]["customer"] == "Mama Ngozi"
      and not st["pending"].get("_reask") and "₦50,000" in r["text"], r["text"])
check("…and the check was for that message only", "heard_check" not in st)
st = converse.new_state()
st["heard_check"] = {"unsure_amount": True}
r = converse.reply("Iya Bisi paid 7000", st)
check("unsure amount: 'I heard ₦7,000, but not clearly. Say the amount again.'",
      r["text"] == "I heard ₦7,000, but not clearly. Say the amount again.", r["text"])
r = converse.reply("yes", st)
check("…'yes' keeps what was heard (the trader checked it)", r["text"].startswith("Saved."), r["text"])
st = converse.new_state()
st["heard_check"] = {"unsure_words": ["adaeze"]}
r = converse.reply("Mama Adaeze took 2 bags of rice for 90000 on credit", st)
check("a new name not heard clearly: 'Say the customer's name again.'",
      r["text"] == "I didn't hear the name well. Say the customer's name again.", r["text"])
r = converse.reply("Mama Adanna", st)
check("…the name said again replaces it, amount kept",
      st["pending"]["customer"] == "Mama Adanna" and st["pending"]["amount"] == 90000 and "Mama Adanna" in r["text"], r["text"])
ledger.add_entry({"type": "credit_sale", "amount": 1000, "customer": "Mama Tunde"})
st = converse.new_state()
st["heard_check"] = {"unsure_words": ["tunde"]}
r = converse.reply("Mama Tunde took rice for 4000 on credit", st)
check("a name already in the book isn't asked again (it was a hint)", "name" not in r["text"] and st["pending"].get(
    "_reask") is None, r["text"])
for lang, want in {"Pidgin": "I hear ₦5,000 or ₦50,000. Talk the money again.",
                   "Yoruba": "Mo gbọ́ ₦5,000 tàbí ₦50,000. Ẹ sọ iye owó náà lẹ́ẹ̀kan sí i.",
                   "Hausa": "Na ji ₦5,000 ko ₦50,000. Sake faɗin kuɗin.",
                   "Igbo": "Anụrụ m ₦5,000 ma ọ bụ ₦50,000. Kwuo ego ahụ ọzọ."}.items():
    st = converse.new_state()
    st["prefer"], st["heard_check"] = lang, {"amounts": [5000.0, 50000.0]}
    r = converse.reply("Mama Ngozi bought rice for 5000", st)
    check(f"{lang}: asked in their language", r["text"] == want, r["text"])

# 7. web: live talk hears in one call and replies in the next; the check goes with the words
from fastapi.testclient import TestClient  # noqa: E402

import web  # noqa: E402

asr.transcribe_auto = lambda path, language=None, vocab=None: {
    "text": "Mama Ngozi took rice 5000 on credit", "engine": "test", "check": {"amounts": [5000.0, 50000.0]}}
cl = TestClient(web.app)
h = cl.post("/api/hear", files={"file": ("n.webm", b"0" * 200)}, data={"lang": "English", "consent": "yes"}).json()
r = cl.post("/api/say", json={"session": "ab", "text": h["heard"], "lang": "English"}).json()
check("live talk: /api/hear then /api/say asks for the amount again",
      "Say the amount again" in json.dumps(r) and "amount" in ((r.get("draft") or {}).get("unsure") or []), r)
r = cl.post("/api/say", json={"session": "ab2", "text": h["heard"], "lang": "English"}).json()
check("…once only (typed or repeated words don't carry an old check)", "Say the amount again" not in json.dumps(r), r)
r = cl.post("/api/voice", files={"file": ("n.webm", b"0" * 200)},
            data={"session": "ab3", "lang": "English", "consent": "yes"}).json()
check("voice note card: the same question", "Say the amount again" in json.dumps(r), r)

print(f"\n{passed}/{total} checks pass")
sys.exit(0 if passed == total else 1)
