"""The Ask chat's server side (design 3, Ask tab): /api/ask, /api/ask/photo, /api/ask/say, /api/ask/reset.
No keys needed: the brain is the offline rules, the photo reader and the voice are faked.

python eval/test_ask.py
"""
import os
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

# 5. the voice note: made at once after a voice question, on request after a typed one
made = []
web._start_voice = lambda sid: made.append(sid)
r = ask("Who is late?", voice=True)
check("asked by voice: autoplay, and its voice is made at once", r["autoplay"] and r["speak"] in made, r)
r = ask("Who is late?")
check("typed: no autoplay, no voice made until a tap", not r["autoplay"] and r["speak"] not in made, r)
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

print(f"\n{passed}/{total} checks pass")
sys.exit(0 if passed == total else 1)
