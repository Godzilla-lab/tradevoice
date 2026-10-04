"""The Ask chat's server side (design 3, Ask tab): /api/ask, /api/ask/photo, /api/ask/say, /api/ask/reset.
No keys needed: the brain is the offline rules, the photo reader and the voice are faked.

python eval/test_ask.py
"""
import os
import re
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["BOOKS_DIR"] = tempfile.mkdtemp()
os.environ["ACCOUNTS_DB"] = os.path.join(tempfile.mkdtemp(), "a.db")
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "NATLAS", "WHATSAPP_")):
        os.environ.pop(k)
os.environ.update(TRADEVOICE_ADMIN="0", AUTO_REMINDERS="0", AUTH_REQUIRED="0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import ledger  # noqa: E402
import photo  # noqa: E402
import web  # noqa: E402

passed = total = 0


def check(name, cond, got=""):
    global passed, total
    total += 1
    passed += bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  got: {got!r}"))


ledger.add_entry({"type": "credit_sale", "amount": 45000, "customer": "Iya Bisi", "item": "rice"})
ledger.add_entry({"type": "credit_sale", "amount": 25000, "customer": "Oga Emeka", "item": "beans"})
ledger.add_entry({"type": "sale", "amount": 8000, "item": "garri"})
ledger.add_entry({"type": "payment_received", "amount": 2000, "customer": "Oga Emeka"})
c = TestClient(web.app)
ask = lambda text, session="chat", **kw: c.post("/api/ask", json=dict({"session": session, "text": text,  # noqa: E731
                                                                       "lang": "English"}, **kw)).json()

# 1. the design's four questions, answered from the book, with the big number on top
r = ask("Who owes me the most?")
check("'Who owes me the most?': Iya Bisi, big number ₦45,000", r["n"] == "₦45,000" and "Iya Bisi" in r["t"], r)
r = ask("How much did I get today?")
check("'How much did I get today?' = money that came in (cash sales + debts paid): ₦10,000",
      r["n"] == "₦10,000" and "came in" in r["t"], r)
r = ask("Who is late?")
check("'Who is late?': nobody, no big number", r["n"] is None and r["t"].startswith("Nobody is late"), r)
r = ask("How much is owed in total?")
check("'How much is owed in total?': ₦68,000, each person listed", r["n"] == "₦68,000" and "Oga Emeka ₦23,000" in r["t"],
      r)

# 2. any other question goes to the same brain (book, tools, languages)
r = ask("How much does Oga Emeka owe me?")
check("a free question: Oga Emeka ₦23,000", r["n"] == "₦23,000", r)
r = ask("If I give 10% discount on 45000, how much?")
check("the calculator, working shown", r["n"] == "₦40,500" and "₦45,000 - 10% = ₦40,500" in r["t"], r)
r = ask("Elo ni Oga Emeka jẹ mí?", lang="Yoruba")
check("Yoruba question, Yoruba answer", r["lang"] == "Yoruba" and "23,000" in r["t"], r)
r = ask("how much does he owe now?")
check("follow-on: 'he' = the last person asked about (Oga Emeka)", "23,000" in r["t"], r)

# 3. a record said in the chat waits for "yes" (nothing saved by asking alone); no WhatsApp *stars*
before = len(ledger.entries(limit=1000))
r = ask("Mama Ngozi took rice 20000 on credit")
check("a record in the chat: read back, waits for yes", r["pending"] and "*" not in r["t"]
      and len(ledger.entries(limit=1000)) == before, r)
check("…said with 'Should I save it?' (no buttons in a chat)", r["say"] and r["say"].endswith("Should I save it?"), r)
r = ask("yes")
check("…'yes' saves it", r["t"].startswith("Saved.") and len(ledger.entries(limit=1000)) == before + 1, r)

# 4. same-name customers: the choices as numbered lines; "2" picks the second
ledger.create_customer("Mama Titi")
ledger.create_customer("Mama Titi")
r = ask("Mama Titi took beans 5000 on credit", session="which")
check("'Which Mama Titi?' with the choices as numbered lines", "\n1. Mama Titi" in r["t"] and "\n2. Mama Titi"
      in r["t"] and "(say: new)" in r["t"], r)
r = ask("2", session="which")
check("…'2' picks the second one and reads the record back", r["pending"] and "Mama Titi" in r["t"], r)

# 5. the voice note: never made by itself (Intron costs money), only when the trader taps play
made = []
web._start_voice = lambda sid: made.append(sid)
import tts  # noqa: E402
calls = []
tts.speak = lambda text, lang="English", **k: calls.append(text)
r = ask("Who is late?", voice=True)
check("asked by voice: the answer is words, no voice made", r["t"].startswith("Nobody is late") and not made
      and not calls and "autoplay" not in r, r)
r = ask("Who is late?")
check("typed: no voice made either", not made and not calls, r)
c.get(f"/api/speak/{r['speak']}")
check("…the voice is made only when its play button asks for it", len(calls) == 1, calls)
s = c.post("/api/ask/say", json={"text": "Iya Bisi owes you ₦45,000.", "lang": "English"}).json()
check("play again: a fresh id, the amount said in words", s["speak"] and "forty-five thousand" in web.SPEAK[s["speak"]][0]
      or "forty five thousand" in web.SPEAK[s["speak"]][0], web.SPEAK.get(s.get("speak")))
check("…empty words refused", c.post("/api/ask/say", json={"text": " "}).status_code == 400)

# 6. a heard question carries the hearing check (unclear amount -> asked again)
web.HEARD_CHECKS[(ledger.book_path(), "Mama Ngozi took rice 5000 on credit")] = (9e12, {"amounts": [5000.0, 50000.0]})
r = ask("Mama Ngozi took rice 5000 on credit", session="heard", voice=True)
check("voice question with two amounts heard: 'Say the amount again.'", "Say the amount again" in r["t"], r)

# 7. Clear history: the server forgets the chat's follow-on memory
ask("How much does Oga Emeka owe me?", session="clear")
check("before clearing: the chat remembers who was talked about",
      web.SESSIONS.get((ledger.book_path(), "ask:clear"), {}).get("last_customer"))
c.post("/api/ask/reset", json={"session": "clear"})
check("after 'Clear history': forgotten", (ledger.book_path(), "ask:clear") not in web.SESSIONS)

# 8. a photo in the chat: read, never saved; the lines come back to check
photo.read = lambda path: {"rows": [{"save": True, "type": "sale", "amount": 5000, "item": "rice", "customer": None,
                                     "line": "rice 5000"}], "lines": "rice 5000", "engine": "test"}
before = len(ledger.entries(limit=1000))
r = c.post("/api/ask/photo", files={"file": ("p.jpg", b"jpg")}, data={"consent": "yes", "lang": "English"}).json()
check("photo: 'I found 1 line. Check it before I save.' + the line", r["t"] == "I found 1 line. Check it before I save."
      and r["act"] == "scan" and r["rows"][0]["amount"] == 5000, r)
check("…nothing saved yet", len(ledger.entries(limit=1000)) == before)
photo.read = lambda path: {"rows": [], "lines": "", "engine": "test"}
r = c.post("/api/ask/photo", files={"file": ("p.jpg", b"jpg")}, data={"consent": "yes", "lang": "Hausa"}).json()
check("an unreadable page, in Hausa", r["t"].startswith("Ban iya karanta") and not r["act"], r)


def broken(path):
    raise RuntimeError("no vision model")


photo.read = broken
r = c.post("/api/ask/photo", files={"file": ("p.jpg", b"jpg")}, data={"consent": "yes"}).json()
check("photo reader down: an honest line, no error page", r["t"] == "I can't read photos right now. Try again later.", r)
check("photo needs consent", c.post("/api/ask/photo", files={"file": ("p.jpg", b"x")}).status_code == 400)
check("an empty question is refused", c.post("/api/ask", json={"text": "  "}).status_code == 400)

# 9. Home's period (Today / 7D / 30D / 1Y / Custom): money in and out for those days only (v2 /api/v2/book)
import datetime as dt  # noqa: E402

import v2  # noqa: E402

T = dt.date.today()
ledger.add_entry({"type": "sale", "amount": 1000, "item": "salt"}, created_at=dt.datetime.combine(T - dt.timedelta(days=20),
                                                                                                    dt.time(10)))
money = lambda *q: ledger.money_between(*v2._span(*q, T)[1:])["money_in"]  # noqa: E731
check("Today: the old sale is not counted", money("today", "", "") == 10000, money("today", "", ""))
check("7D: still not, from 6 days ago", money("7", "", "") == 10000 and v2._span("7", "", "", T)[1] == T - dt.timedelta(days=6))
check("30D: counted (₦11,000)", money("30", "", "") == 11000, money("30", "", ""))
check("1Y: from 364 days ago", v2._span("365", "", "", T)[1] == T - dt.timedelta(days=364))
a, b = str(T - dt.timedelta(days=21)), str(T - dt.timedelta(days=19))
d = v2._span("custom", b, a, T)
check("Custom, dates the wrong way round: put in order, only those days (₦1,000)",
      d == ("custom", dt.date.fromisoformat(a), dt.date.fromisoformat(b)) and money("custom", b, a) == 1000, d)
check("Custom into the future: ends today", v2._span("custom", str(T), str(T + dt.timedelta(days=40)), T)[2] == T)
check("Custom with bad dates: Today", v2._span("custom", "x", "", T) == ("today", T, T))
check("an unknown period: Today", v2._span("week", "", "", T)[0] == "today")

# 10. N-ATLaS waking up (slow): one chat message never waits longer than its AI time (ASK_AI_SECONDS)
import time  # noqa: E402

import llm  # noqa: E402

calls = []


def slow_client(kind, timeout, retries=0, model=None):
    def create(**kw):
        calls.append(timeout)
        time.sleep(min(timeout, 4))
        raise TimeoutError("waking up")
    from types import SimpleNamespace
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


os.environ.update(NATLAS_URL="http://natlas/v1", ASK_AI_SECONDS="6", ASK_LLM_SECONDS="6", NATLAS_TIMEOUT="60")
real_client, llm._client, llm._resting = llm._client, slow_client, {}
t0 = time.time()
r = ask("Sold 2 bags of rice for 90000", session="slow")
took = time.time() - t0
check(f"a slow AI: answered in {took:.0f} s (the model's 6 s + the rules' 6 s at most), by the rules", took < 16 and r["pending"]
      and "90,000" in r["t"], (took, r))
check("…every AI call got only what was left of the 6 s", calls and max(calls) <= 6, calls)
llm._client = real_client
for k in ("NATLAS_URL", "ASK_AI_SECONDS", "ASK_LLM_SECONDS", "NATLAS_TIMEOUT"):
    os.environ.pop(k)

# 11. live voice speed: N-ATLaS writes the record as guided JSON (short), and the reply is spoken in two parts
import json as _json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import extract  # noqa: E402

SEEN = []


def json_client(kind, timeout, retries=0, model=None):
    def create(**kw):
        SEEN.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=_json.dumps(
            {"type": "credit_sale", "item": "rice", "quantity": None, "unit": None, "amount": 20000, "each": False,
             "customer": "Mama Ngozi", "due_date": None, "confidence": 0.9, "note": None})))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


os.environ["NATLAS_URL"] = "http://natlas/v1"
llm._client, llm._resting = json_client, {}
rec, meta = extract.extract("Mama Ngozi took rice 20000 on credit")
kw = SEEN[-1] if SEEN else {}
check("the record: N-ATLaS must answer in the record's JSON shape (guided, no thinking out loud first)",
      kw.get("response_format", {}).get("type") == "json_schema" and "credit_sale" in _json.dumps(kw["response_format"]),
      list(kw))
check("…and short: at most 250 tokens (each costs ~55 ms on the L4)", kw.get("max_tokens", 999) <= 250, kw.get("max_tokens"))
check("…the record is still right", rec["customer"] == "Mama Ngozi" and rec["amount"] == 20000
      and rec["type"] == "credit_sale" and meta["engine"].startswith("llm:"), (rec, meta))
llm._client = real_client
os.environ.pop("NATLAS_URL")
started = []
web._start_voice = lambda sid: started.append(sid)
d = c.post("/api/say", json={"session": "two", "text": "Mama Ngozi took rice 20000 on credit", "lang": "English"}).json()
ps = web.VOICES[d["speak"]].parts if d.get("speak") in web.VOICES else []
check("live talk: the reply's voice comes in pieces (the first plays while the rest is made)",
      d["parts"] == len(ps) >= 2 and not started, (d.get("parts"), ps, started))
check("…the first piece is the record, the last the question", "twenty thousand" in ps[0] and ps[-1].endswith("?"), ps)
d = c.post("/api/say", json={"session": "two", "text": "yes", "lang": "English"}).json()
ps = web.VOICES[d["speak"]].parts
check("…'yes': every piece is 10+ characters (a short opener like 'Done.' rides with the saved line)",
      all(len(p) >= 10 for p in ps) and "twenty thousand" in " ".join(ps[:2]), ps)
d = c.post("/api/say", json={"session": "two2", "text": "How much does Oga Emeka owe me?", "lang": "English"}).json()
check("…a one-sentence reply is one piece", d["parts"] == 1 and "Oga Emeka" in web.VOICES[d["speak"]].parts[0],
      web.VOICES[d["speak"]].parts)
r = c.post("/api/ask", json={"session": "two-ask", "text": "Who is late?", "lang": "English"}).json()
check("the Ask chat's voice note stays one clip (made only on a tap)", "parts" not in r and r["say"]
      and r["speak"] not in web.VOICES, r)

# 12. live talk answers at once: no model wait for a book question or a record the rules read fully
def slow_model(messages, **k):
    time.sleep(3)
    raise TimeoutError("slow")


llm.chat, os.environ["NATLAS_URL"] = slow_model, "http://natlas/v1"
for said in ["how much did I sell today?", "how much does Oga Emeka owe me?", "Mama Ngozi took rice 20000 on credit",
             "yes", "Iya Bisi paid 5000"]:
    t0 = time.time()
    d = c.post("/api/say", json={"session": "fast", "text": said, "lang": "English"}).json()
    check(f"live, at once (no 3 s model wait): '{said}'", time.time() - t0 < 1 and d["text"], (time.time() - t0, d["text"]))
t0 = time.time()
d = c.post("/api/say", json={"session": "fast2", "text": "Baba Kunle collect beans 8k, him go pay 2 weeks time",
                             "lang": "English"}).json()
check("…but a record with a date the rules can't read still goes to the model (it waited)", time.time() - t0 >= 3, d)
os.environ.pop("NATLAS_URL")

print(f"\n{passed}/{total} checks pass")
sys.exit(0 if passed == total else 1)
