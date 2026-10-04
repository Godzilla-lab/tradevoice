"""The Ask chat's brain is a real model (agent.py): NVIDIA first, N-ATLaS backup; it uses the book's tools, code checks
every number it says. A fake model plays the part (good and bad turns). Also: long answers as background jobs, and a
photo that isn't a record book. No keys.

python eval/test_agent.py
"""
import json
import os
import sys
import tempfile
import time

os.environ["TV_NO_DOTENV"] = "1"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["BOOKS_DIR"] = tempfile.mkdtemp()
os.environ["ACCOUNTS_DB"] = os.path.join(tempfile.mkdtemp(), "a.db")
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "NATLAS", "WHATSAPP_", "INTRON", "ASK_")):
        os.environ.pop(k)
os.environ.update(TRADEVOICE_ADMIN="0", AUTO_REMINDERS="0", AUTH_REQUIRED="0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import agent  # noqa: E402
import ledger  # noqa: E402
import llm  # noqa: E402
import photo  # noqa: E402
import web  # noqa: E402

passed = total = 0


def check(name, cond, got=""):
    global passed, total
    total += 1
    passed += bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  got: {got!r}"))


ledger.add_entry({"type": "credit_sale", "amount": 45000, "customer": "Iya Bisi", "item": "rice"})
ledger.add_entry({"type": "credit_sale", "amount": 33000, "customer": "Mama Ngozi", "item": "beans"})
ledger.add_entry({"type": "sale", "amount": 8000, "item": "garri"})
c = TestClient(web.app)
ask = lambda text, session="a", **kw: c.post("/api/ask", json=dict({"session": session, "text": text,  # noqa: E731
                                                                     "lang": "English"}, **kw)).json()

# 1. no model set up: the rules answer, as before
check("no NVIDIA key, no N-ATLaS: the model brain is off", not agent.available())
r = ask("Who owes me the most?")
check("…the rules still answer", "Iya Bisi" in r["t"] and "45,000" in r["t"], r)

# 2. a model that uses the tools
os.environ["NVIDIA_API_KEY"] = "test"
CALLS, SCRIPT = [], []


def fake_chat(messages, **kw):
    CALLS.append({"messages": messages, **{k: v for k, v in kw.items() if k != "schema"}, "schema": bool(kw.get("schema"))})
    step = SCRIPT.pop(0)
    return (step(messages) if callable(step) else json.dumps(step)), "nvidia/nemotron-3-super-120b-a12b"


llm.chat = fake_chat
check("NVIDIA key set: the model brain is on, NVIDIA first, N-ATLaS the backup",
      agent.available() and agent.models("English")[0].startswith("nvidia/") and agent.models("English")[-1] == "natlas")
check("…in Yoruba, Hausa, Igbo: N-ATLaS first", agent.models("Yoruba")[0] == "natlas")
SCRIPT[:] = [{"tool": "who_owes", "args": {"name": None}},
             lambda m: json.dumps({"reply": "Iya Bisi owes you the most: " + "₦{:,}".format(
                 json.loads(m[-1]["content"].split(": ", 1)[1])["people"][0]["owes"]) + "."})]
r = ask("who's carrying the biggest debt for me abeg?", session="m1")
check("a messy question: the model asks the book (who_owes), then answers with the book's number",
      r["t"] == "Iya Bisi owes you the most: ₦45,000." and r["n"] == "₦45,000", r)
check("…the model got the tool's result, and a JSON schema to answer in", "TOOL RESULT who_owes" in
      CALLS[-1]["messages"][-1]["content"] and CALLS[-1]["schema"], CALLS[-1]["messages"][-1]["content"][:80])
check("…models asked: NVIDIA first", CALLS[-1]["models"][0].startswith("nvidia/"), CALLS[-1].get("models"))

# 3. a number nobody gave -> refused; the rules answer instead
SCRIPT[:] = [{"reply": "Iya Bisi owes you ₦99,999."}]
r = ask("Who owes me the most?", session="m2")
check("the model invents ₦99,999: refused, the rules answer from the book", "45,000" in r["t"] and "99,999" not in r["t"], r)

# 4. cheering refused; off topic -> the fixed line, whatever the model says
SCRIPT[:] = [{"reply": "Great job! Your shop is doing amazing!"}]
r = ask("How is my shop doing?", session="m3")
check("cheering: refused (calm only)", "Great job" not in r["t"] and "amazing" not in r["t"], r)
SCRIPT[:] = [{"reply": "To reduce stigma around mental health, educate people."}]
r = ask("How can we reduce stigma around mental health?", session="m4")
check("off topic: never the model's words, the fixed line", r["t"].startswith("I can only help with your shop"), r)

# 5. the calculator: only numbers that were said or came from a tool
SCRIPT[:] = [{"tool": "who_owes", "args": {"name": "ngozi"}},
             {"tool": "calculate", "args": {"expression": "33000 - 30000"}},
             lambda m: json.dumps({"reply": "If Mama Ngozi pays ₦30,000, she will still owe you ₦" +
                                   "{:,}".format(int(json.loads(m[-1]["content"].split(": ", 1)[1])["result"])) + "."})]
r = ask("if ngozi pays 30k how much go remain?", session="m5")
check("'if ngozi pays 30k': book (33,000) + calculator (code) -> ₦3,000", r["t"] ==
      "If Mama Ngozi pays ₦30,000, she will still owe you ₦3,000.", r)
ctx = {"today": __import__("datetime").date.today(), "text": "x", "lang": "English", "state": {}, "numbers": {33000.0}}
out = agent.run_tool("calculate", {"expression": "33000 * 0.85"}, ctx)
check("…a number nobody gave (0.85): the calculator refuses", "error" in out, out)

# 6. a record: the model hands it to the record flow (read back, "Should I save it?"); "yes" saves
SCRIPT[:] = [{"tool": "record", "args": {}}]
n0 = len(ledger.entries(limit=1000))
r = ask("Mama Tunde collect 2 bags rice 90k on credit", session="m6")
check("a new record: the record flow reads it back and waits (nothing saved by the model)",
      r["pending"] and "Should I save it?" in (r["say"] or r["t"]) and len(ledger.entries(limit=1000)) == n0, r)
r = ask("yes", session="m6")
check("…'yes' goes straight to the record flow (no model needed) and saves", r["t"].startswith("Saved.")
      and len(ledger.entries(limit=1000)) == n0 + 1 and not SCRIPT, r)

# 7. the conversation is remembered ("she" = the person talked about)
SCRIPT[:] = [{"tool": "who_owes", "args": {"name": "ngozi"}}, {"reply": "Mama Ngozi owes you ₦33,000."},
             lambda m: json.dumps({"reply": "seen" if any("ngozi" in x["content"].lower() for x in m[1:-1])
                                   else "no memory"})]
ask("how much does ngozi owe?", session="m7")
r = ask("when will she pay?", session="m7")
check("the earlier turns go to the model (it knows who 'she' is)", r["t"] == "seen", r)

# 8. the model fails (timeout): the rules answer, nothing lost
SCRIPT[:] = [lambda m: (_ for _ in ()).throw(TimeoutError("slow"))]
r = ask("Who owes me the most?", session="m8")
check("model down: the rules answer (from the book: Mama Tunde's ₦90,000 is now the biggest)",
      r["t"] == "Mama Tunde owes you the most: ₦90,000.", r)

# 9. a long answer: the page gets a job id at once and collects the answer (never "No network")
os.environ["ANSWER_WAIT_SECONDS"] = "0.3"
SCRIPT[:] = [lambda m: (time.sleep(1.2), json.dumps({"tool": "who_owes", "args": {"name": "bisi"}}))[1],
             {"reply": "Iya Bisi owes you ₦45,000."}]
r = ask("Who owes me the most, abeg?", session="m9")
check("slower than the wait: {job} at once", set(r) == {"job"}, r)
j = c.get(f"/api/job/{r['job']}").json()
check("…/api/job gives the answer when it is ready", j.get("t") == "Iya Bisi owes you ₦45,000.", j)
check("…and then it is gone", c.get(f"/api/job/{r['job']}").status_code == 404)
os.environ.pop("ANSWER_WAIT_SECONDS")

# 10. a photo that isn't a record book: the vision model says what it is
import vision  # noqa: E402

vision.read_notebook = lambda path: {"text": "NOT_A_RECORD: an advert for a ring", "latency_ms": 5, "engine": "vision:x"}
r = c.post("/api/ask/photo", files={"file": ("p.jpg", b"jpg")}, data={"consent": "yes", "lang": "English"}).json()
check("an advert: 'This looks like an advert for a ring, not a page from your record book…'",
      r["t"].startswith("This looks like an advert for a ring, not a page from your record book") and not r["rows"], r)
check("…the vision prompt asks for that", "NOT_A_RECORD" in vision.PROMPT)

print(f"\n{passed}/{total} checks pass")
sys.exit(0 if passed == total else 1)
