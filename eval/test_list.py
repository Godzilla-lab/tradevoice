"""A list pasted into the chat (the owner's test, 4 Oct: 42 people and what they owe, all on one line). N-ATLaS reads
every record (faked here, with mistakes on purpose); code checks each amount was really written, adds the total,
marks lines to look at; nothing is saved until the trader ticks and saves. Chat brain, /api/ask, WhatsApp. No keys.

python eval/test_list.py
"""
import hashlib
import hmac
import json
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
os.environ.update(TRADEVOICE_ADMIN="0", AUTO_REMINDERS="0", AUTH_REQUIRED="0", WHATSAPP_TOKEN="test",
                  WHATSAPP_PHONE_ID="123", WHATSAPP_VERIFY_TOKEN="tv-verify", WHATSAPP_APP_SECRET="s3cret")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import converse  # noqa: E402
import extract  # noqa: E402
import ledger  # noqa: E402
import llm  # noqa: E402
import web  # noqa: E402
import whatsapp  # noqa: E402

passed = total = 0


def check(name, cond, got=""):
    global passed, total
    total += 1
    passed += bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  got: {got!r}"))


PASTE = ("# Name Amount owed Chinedu ₦15,000 Aisha ₦45,000 Tunde ₦8,500 Emeka ₦120,000 Blessing ₦25,000 Ibrahim ₦65,000 "
         "Favour ₦12,000 Daniel ₦35,500 Esther ₦75,000 Samuel ₦18,000 Amarachi ₦50,000 Yusuf ₦22,500 David ₦150,000 "
         "Mercy ₦7,000 Abdulrahman ₦90,000 Kemi ₦32,000 Chisom ₦14,500 Michael ₦60,000 Zainab ₦27,000 Segun ₦10,000 "
         "Adaeze ₦85,000 Mustapha ₦40,000 Tolulope ₦5,500 Ngozi ₦110,000 Hassan ₦20,000 Funmi ₦55,000 Kingsley ₦30,000 "
         "Hadiza ₦17,500 Akinwande ₦200,000 Rita ₦9,000 Seyi ₦42,000 Halima ₦70,000 Obinna ₦16,000 Yetunde ₦95,000 "
         "Bashir ₦33,000 Ifeanyi ₦125,000 Patricia ₦11,500 Abdulaziz ₦48,000 Modupeola ₦23,000 Victor ₦175,000 "
         "Victor 500,000 mike 7m")
PAIRS = re.findall(r"([A-Za-z]+) (₦?[\d,]+m?)", PASTE.split("owed ", 1)[1])
CALLS = []


def fake_chat(messages, **kw):
    """N-ATLaS with two mistakes: it skips Rita and writes Seyi's ₦42,000 as ₦43,000."""
    CALLS.append(kw)
    if messages[0]["content"] != extract.LIST_PROMPT:
        raise TimeoutError("only the list reader is faked")
    said = messages[-1]["content"]
    pairs = re.findall(r"([A-Za-z]+) (₦?[\d,]+m?)", said.split("owed ", 1)[-1])
    entries = [{"customer": n, "item": None, "amount": "₦43,000" if n == "Seyi" else a, "type": "credit_sale"}
               for n, a in pairs if n != "Rita"]
    return json.dumps({"entries": entries}), "natlas"


check("the paste has 42 people", len(PAIRS) == 42, len(PAIRS))
check("it is a list (3+ amounts)", extract.is_list(PASTE))
for one in ["Aunty Kemi paid 26k out of the 80k she owes, 54k remaining", "I sell 4 carton malt give Chief Okoro 17k, "
            "no be 17k, na 19k", "Deaconess Funmi bought rice for 78,000 and paid 50k, she will balance me 28k",
            "Mama Tunde took rice 20k"]:
    check(f"one record, not a list: '{one[:40]}…'", not extract.is_list(one))

# 1. no AI: says so, never one guessed number (the old ₦200,000 "sale")
st = converse.new_state()
r = converse.reply(PASTE, st)
check("N-ATLaS off: 'I can't read a long list right now…', no draft, nothing saved",
      r["text"].startswith("I can't read a long list right now") and not st.get("pending")
      and not ledger.entries(limit=10), r["text"])

# 2. N-ATLaS reads it, code checks it
os.environ["NATLAS_URL"] = "http://natlas/v1"
llm.chat = fake_chat
st = converse.new_state()
r = converse.reply(PASTE, st)
rows = r.get("rows") or []
check("41 lines (the model's), shown to check, nothing saved, no draft", len(rows) == 41 and r.get("act") == "scan"
      and not st.get("pending") and not ledger.entries(limit=10), (len(rows), r["text"][:80]))
check("the model was asked with a JSON schema and given time for a long list",
      CALLS[-1].get("schema") is extract.LIST_SCHEMA and CALLS[-1].get("long") and CALLS[-1]["max_tokens"] > 1500,
      CALLS[-1:] and {k: v for k, v in CALLS[-1].items() if k != "schema"})
total_said = sum(r_["amount"] for r_ in rows)
check("the total is added by code: 'I found 41 people who owe you, ₦…'", r["text"].startswith(
      f"I found 41 people who owe you, ₦{total_said:,.0f} in all. Check them before I save."), r["text"][:90])
by = {}
for x in rows:
    by.setdefault(x["customer"], []).append(x)
check("all credit_sale (they owe you), names as written, 'mike' -> Mike", all(x["type"] == "credit_sale" for x in rows)
      and "Mike" in by and by["Chinedu"][0]["amount"] == 15000, sorted(by)[:5])
check("Seyi's ₦43,000 is not in the message: not ticked, said", not by["Seyi"][0]["save"]
      and "Seyi: This amount is not in your message." in r["text"], by["Seyi"])
check("Victor twice: the second not ticked", by["Victor"][0]["save"] and not by["Victor"][1]["save"]
      and "Victor is on the list twice." in r["text"], by["Victor"])
check("mike ₦7,000,000 is far bigger than the rest: not ticked", not by["Mike"][0]["save"]
      and "Mike: ₦7,000,000 is much bigger than the others." in r["text"], by["Mike"])
check("Rita (skipped by the model) and Seyi's real ₦42,000 are named as left out",
      "These amounts are in your message but not in any line: ₦9,000, ₦42,000." in r["text"], r["text"][-160:])
check("the rest are ticked", sum(x["save"] for x in rows) == 38, sum(x["save"] for x in rows))

# 3. the Ask chat: rows + "Check the lines"; save_rows saves only the ticked ones, as debts
c = TestClient(web.app)
d = c.post("/api/ask", json={"session": "list", "text": PASTE, "lang": "English"}).json()
check("/api/ask: rows + act 'scan', no big number on top", len(d["rows"]) == 41 and d["act"] == "scan" and d["n"] is None
      and not d["pending"], {k: d[k] for k in ("act", "n", "pending")})
s = c.post("/api/save_rows", json={"rows": d["rows"]}).json()
book = {e["customer"]: e for e in ledger.entries(limit=100)}
check("Save ticked: 38 debts saved, the 3 to look at are not", s["saved"] == 38 and len(book) == 38
      and "Mike" not in book and book["Chinedu"]["type"] == "credit_sale", s)
d = c.post("/api/ask", json={"session": "list2", "text": PASTE, "lang": "English"}).json()
again = {x["customer"]: x for x in d["rows"]}
check("pasted again: people already owing are not ticked ('Chinedu already owes you ₦15,000; ticking adds ₦15,000')",
      not again["Chinedu"]["save"] and "Chinedu already owes you ₦15,000; ticking adds ₦15,000." in d["t"], again["Chinedu"])
r = converse.reply("Chinedu ₦15,000 Aisha ₦45,000 Tunde ₦8,500", converse.new_state(), )
check("a short list (3 people) reads too", len(r.get("rows") or []) == 3, r["text"][:60])
st = converse.new_state()
st["lang"] = "Hausa"
r = converse.reply("Na Musa ₦15,000 Bello ₦4,000 Sani ₦8,500 bashi", st)
check("Hausa list: Hausa words", r["text"].startswith(("Na ga mutum", "Ban iya")) or "Na ga" in r["text"], r["text"][:60])

started = []
web._start_voice = lambda sid: started.append(sid)
d = c.post("/api/say", json={"session": "live", "text": "Ladi 5,000 naira, Bisi 6,000 naira, Kunle 7,000 naira",
                             "lang": "English"}).json()
check("live voice: a list said in one go comes back as lines to check (spoken summary, nothing saved, no draft)",
      len(d["rows"]) == 3 and d["act"] == "scan" and not d["pending"] and d["speak"] and d["parts"] >= 1
      and d["text"].startswith("I found 3 people who owe you, ₦18,000 in all"), {k: d[k] for k in ("text", "act")})

# 4. WhatsApp: the same lines, numbered; "no 2" skips; "yes" saves
SENT = []
whatsapp.graph_post = lambda p: SENT.append(p) or {"messages": [{"id": "x"}]}
whatsapp.send_voice = lambda to, text, lang: None
n = 0


def wa(text):
    global n
    n += 1
    msg = ({"type": "interactive", "interactive": {"type": "list_reply", "list_reply": {"id": text}}}
           if text.startswith("lang:") else
           {"type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": text}}}
           if text.startswith("consent:") else {"type": "text", "text": {"body": text}})
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"from": "2348000000009", "id": f"l{n}",
                                                                        **msg}]}}]}]})
    sig = "sha256=" + hmac.new(b"s3cret", body.encode(), hashlib.sha256).hexdigest()
    SENT.clear()
    c.post("/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    return json.dumps([p for p in SENT if p.get("status") != "read"], ensure_ascii=False)


wa("hi")
wa("lang:English")
wa("consent:yes")
out = wa("Ladi ₦5,000 Bisi ₦6,000 Kunle ₦7,000")
check("WhatsApp: 'I found 3 people who owe you, ₦18,000 in all' + numbered lines + Save button",
      "I found 3 people who owe you, ₦18,000 in all" in out and "1. " in out and "p_save" in out, out[:300])
out = wa("no 2")
check("WhatsApp: 'no 2' marks Bisi *Skip*", "*Skip* " in out and "Bisi" in out, out[:300])
out = wa("yes")
tok = ledger.use_book("2348000000009")
names = {e["customer"] for e in ledger.entries(limit=1000)}
ledger.done_with_book(tok)
check("WhatsApp: 'yes' saves Ladi and Kunle to that phone's book, not Bisi ('Saved 2 records from your list.')",
      names == {"Ladi", "Kunle"} and "Saved 2 records from your list." in out, (names, out[:200]))
os.environ.pop("NATLAS_URL")

print(f"\n{passed}/{total} checks pass")
sys.exit(0 if passed == total else 1)
