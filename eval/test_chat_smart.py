"""The chat must not be dumb: the owner's own test conversation (4 Oct) turn by turn, plus messy messages around the
same mistakes: profit talk, garbled and huge amounts, a list said one after the other ("save it all"), counting
customers, things TradeVoice can't see, and an AI that cheers instead of answering. Offline rules; no keys.

python eval/test_chat_smart.py
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
import assistant  # noqa: E402
import converse  # noqa: E402
import insights  # noqa: E402
import ledger  # noqa: E402

passed = total = 0


def check(name, cond, got=""):
    global passed, total
    total += 1
    passed += bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  got: {got!r}"))


def entries():
    return len(ledger.entries(limit=10_000))


ledger.add_entry({"type": "sale", "amount": 3000, "item": "rice"})   # a small book: ₦3,000 is its biggest line

# ---------------------------------------------------------------- 1. the owner's conversation, turn by turn
st = converse.new_state()
st["queue_ok"] = True      # the Ask chat
say = lambda t: converse.reply(t, st)["text"]  # noqa: E731

r = say("Today we make 50,0000 naira in profit and 20000k")
check("1. profit talk is not saved as spending; it explains profit is worked out", r.startswith("I work out your profit")
      and "Today your book says" in r and not st.get("pending"), r)
r = say("No 500,000k and spent 130,000")
check("2. the clear part is the record: 'You spent ₦130,000.' (no 'on expenses')",
      "I heard: You spent ₦130,000. Should I save it?" in r and "on expenses" not in r, r)
check("…and the garbled number is said to be left out, both readings shown",
      "I left out the other amount (₦500,000,000 or ₦500,000?)" in r, r)
n0 = entries()
r = say("Yes save it")
check("3. 'Yes save it' saves it, calmly", r == "Saved. You spent ₦130,000." and entries() == n0 + 1, r)
r = say("Dino owes me 5 million naira")
check("4. a very big amount is read back in words: 'That is five million naira. Is that right?'",
      "Dino will pay you ₦5,000,000" in r and "That is five million naira. Is that right?" in r, r)
r = say("and Mike owes me 300 million naira")
check("5. 'and Mike…' keeps Dino waiting (nothing thrown away), Mike named",
      "Mike will pay you ₦300,000,000" in r and "2 waiting to save: Dino ₦5,000,000, Mike ₦300,000,000" in r
      and "not saved" not in r, r)
n0 = entries()
r = say("Save it all")
check("6. 'Save it all' saves both, listed", r.startswith("Saved 2.") and "Dino will pay you ₦5,000,000" in r
      and "Mike will pay you ₦300,000,000" in r and entries() == n0 + 2, r)
r = say("How many customers do I have right now?")
check("7. 'How many customers do I have?' counted from the book", r.startswith("You have 2 customers.")
      and "2 of them owe you ₦305,000,000" in r, r)
r = say("I just share some list of customers now")
check("8. a list it can't see: says what to do (photo with +, or one by one), no chit-chat",
      r.startswith("I can't see that here.") and "+" in r and "?" not in r, r)

# ---------------------------------------------------------------- 2. yes, in all the ways people say it
for words in ["save it all", "save all", "save both", "save them", "save everything", "yes save it", "ok save am",
              "go ahead", "Yes, save both", "save it all please"]:
    s2 = converse.new_state()
    converse.reply("Mama Ngozi took rice 20000 on credit", s2)
    converse.reply("and Iya Bisi took beans 8000 on credit", s2)
    n0 = entries()
    r = converse.reply(words, s2)["text"]
    check(f"'{words}' saves the 2 waiting", entries() == n0 + 2 and r.startswith("Saved 2."), r)

# ---------------------------------------------------------------- 3. a list: save one only, cancel all, fix the last
s3 = converse.new_state()
s3["queue_ok"] = True
converse.reply("Mama Ngozi took rice 20000 on credit", s3)
converse.reply("Iya Bisi took beans 8000 on credit", s3)
converse.reply("Oga Emeka took garri 4000 on credit", s3)
r = converse.reply("save Iya Bisi only", s3)["text"]
check("'save Iya Bisi only': that one saved, the other 2 still waiting", r.startswith("Saved. Iya Bisi")
      and "Still waiting: Mama Ngozi ₦20,000, Oga Emeka ₦4,000" in r, r)
r = converse.reply("I mean 5000", s3)["text"]
check("a correction fixes the latest one (Oga Emeka 5,000), the list is kept", "Oga Emeka" in r and "₦5,000" in r
      and "2 waiting to save" not in r or "Mama Ngozi ₦20,000" in r, r)
n0 = entries()
r = converse.reply("no", s3)["text"]
check("'no' with 2 waiting drops them all", r == "OK, I didn't save any of them." and entries() == n0
      and not converse._drafts(s3), r)

s4 = converse.new_state()   # the card screen: a new note replaces a card nobody answered (one card at a time)
converse.reply("Mama Ngozi took rice 20000 on credit", s4)
r = converse.reply("Iya Bisi took beans 8000 on credit", s4)["text"]
check("card screen: a new record replaces the unanswered card (as before)", "not saved" in r
      and len(converse._drafts(s4)) == 1, r)
r = converse.reply("and Oga Emeka took garri 4000 on credit", s4)["text"]
check("…but 'and …' keeps the list even there", "2 waiting to save" in r, r)

# ---------------------------------------------------------------- 4. amounts: garbled, k after a full number, huge
for said, a, b in [("Mama Ngozi took rice 50,0000 on credit", "₦500,000", "₦50,000"),
                   ("Iya Bisi paid 20000k", "₦20,000,000", "₦20,000"),
                   ("I spent 500,000k on goods", "₦500,000,000", "₦500,000")]:
    s5 = converse.new_state()
    r = converse.reply(said, s5)["text"]
    first = r.split("\n")[0]
    check(f"garbled '{said}': asks {a} or {b}", first.startswith("I heard ") and a in first and b in first
          and first.endswith("Say the amount again."), r)
s5 = converse.new_state()
converse.reply("Mama Ngozi took rice 50,0000 on credit", s5)
r = converse.reply("50000", s5)["text"]
check("…the amount said again fixes it", "₦50,000" in r and s5["pending"]["amount"] == 50000, r)
for fine in ["Mama Ngozi took rice 50,000 on credit", "Iya Bisi paid 20k", "sold 2 bags for 90,000"]:
    s6 = converse.new_state()
    r = converse.reply(fine, s6)["text"]
    check(f"a clear amount is not doubted: '{fine}'", "Say the amount again" not in r and "left out" not in r, r)
ledger.add_entry({"type": "sale", "amount": 900_000, "item": "cement"})   # a big trader
s7 = converse.new_state()
r = converse.reply("Alhaji paid 2 million", s7)["text"]
check("₦2,000,000 for a trader whose biggest line is ₦300m: no doubt", "Is that right?" not in r, r)
import web  # noqa: E402

s8 = converse.new_state()
converse.reply("Dino owes me 5 billion naira", s8)
check("a very big amount marks the card's amount for a second look", "amount" in web._draft(s8)["unsure"],
      web._draft(s8))

# ---------------------------------------------------------------- 5. profit talk vs records and questions
for said in ["I made 20k profit today", "we gain 15000 today", "Profit today na 7k"]:
    r = converse.reply(said, converse.new_state())["text"]
    check(f"profit talk explained, not saved: '{said}'", r.startswith(("I work out your profit", "Na me dey calculate")), r)
for said in ["ere m akwa abuo 10800", "Mama Tunde gain 5k discount"]:   # Igbo "ere m" = I sold; not profit talk
    s9 = converse.new_state()
    converse.reply(said, s9)
    check(f"not profit talk, still a record: '{said}'", bool(s9.get("pending")), s9.get("pending"))
r = converse.reply("How much profit did I make today?", converse.new_state())["text"]
check("'How much profit did I make today?' is still answered from the book", "₦" in r and "I work out" not in r, r)
r = converse.reply("I sold rice 5000, profit 1000", converse.new_state())["text"]
check("a sale that mentions profit is still the sale", r.startswith("I heard: You sold") and "₦5,000" in r, r)

# ---------------------------------------------------------------- 6. things it can't see
for said in ["I just sent the list", "check my whatsapp", "I uploaded the excel", "see the picture I sent"]:
    r = converse.reply(said, converse.new_state())["text"]
    check(f"can't see: '{said}'", r.startswith("I can't see that here."), r)

# ---------------------------------------------------------------- 7. counting customers, in other words and languages
for said in ["how many customers I get?", "number of my customers", "Onibaara melo ni mo ni?"]:
    r = converse.reply(said, converse.new_state())["text"]
    check(f"counts customers: '{said}'", "2" in r and ("customers" in r or "oníbàárà" in r), r)
r = converse.reply("how many customers owe me?", converse.new_state())["text"]
check("'how many customers owe me' is a debt question, not the count", "You have" not in r, r)

# ---------------------------------------------------------------- 8. the AI's free answer must be calm and factual
for bad in ["That's great! How many new customers did you add?", "Well done, keep it up.", "How many did you add?"]:
    check(f"AI answer refused: '{bad}'", not assistant.calm_ok(bad))
for good in ["Mama Tunde owes you ₦45,000.", "You sold most on Saturday: ₦120,000."]:
    check(f"AI answer kept: '{good}'", assistant.calm_ok(good))
import llm  # noqa: E402

os.environ["NATLAS_URL"] = "http://natlas/v1"
llm.chat = lambda *a, **k: ("That's great! How many new customers did you add?", "natlas")
ans, eng = insights.ask("I just added some customers")
check("insights.ask: a cheering AI answer is replaced (the chat says the honest line)", ans is None and eng == "rules",
      (ans, eng))
r = converse.reply("tell me something nice", converse.new_state())["text"]
check("…and the chat says what it can help with (not about the shop: no AI answer at all)",
      r.startswith("I can only help with your shop"), r)
os.environ.pop("NATLAS_URL")

# ---------------------------------------------------------------- 9. calm wording everywhere
st9 = converse.new_state()
r = converse.reply("sold rice 5000", st9)
check("no praise in a read-back", "!" not in r["text"] and "Nice one" not in r["text"] and "!" not in r["spoken"], r)
r = converse.reply("yes", st9)
check("no praise after saving", "!" not in r["text"] and "!" not in r["spoken"], r)

# ---------------------------------------------------------------- 10. the owner's second conversation (4 Oct evening)
ledger.wipe()
st = converse.new_state()
st["queue_ok"] = True
say = lambda t: converse.reply(t, st)["text"]  # noqa: E731
r = say("how much have i made in the last month?")
check("10.1 'the last month' = the last 30 days, with numbers even when empty (never 'no record')",
      r.startswith("In the last 30 days, you sold ₦0") and "don't see" not in r, r)
r = say("dino owes me 20k")
check("10.2 a lower-case name is still a name (rules, N-ATLaS asleep): Dino", "Dino will pay you ₦20,000" in r, r)
say("yes")
r = say("mike also owes me 2,000,000")
check("10.3 'mike also owes me': Mike", "Mike will pay you ₦2,000,000" in r, r)
r = say("and tayo 3 million")
check("10.4 'and tayo 3 million' is Tayo's own record (same kind), Mike's keeps waiting, nothing 'changed'",
      "Tayo will pay you ₦3,000,000" in r and "2 waiting to save: Mike ₦2,000,000, Tayo ₦3,000,000" in r
      and "changed" not in r, r)
n0 = entries()
r = say("save it all")
check("10.5 'save it all' saves Mike AND Tayo", r.startswith("Saved 2.") and entries() == n0 + 2, r)
rows = {e["customer"]: e for e in ledger.entries(limit=50)}
check("…each with its own words (Mike's note is not Tayo's)", rows["Mike"]["raw_text"] == "mike also owes me 2,000,000"
      and rows["Tayo"]["raw_text"] == "and tayo 3 million", {k: v["raw_text"] for k, v in rows.items()})
r = say("no mike is diffrent from tayo?")
check("10.6 'no …' right after a save: says what was saved and how to undo (never a sales summary)",
      r.startswith("Sorry. I saved:") and "Mike will pay you ₦2,000,000" in r and "Tayo will pay you ₦3,000,000" in r
      and "undo" in r and "sold" not in r, r)
n0 = entries()
r = say("undo")
check("10.7 'undo' removes everything that one 'save it all' saved", r.startswith("Removed:") and entries() == n0 - 2, r)
r = say("undo")
check("…a second 'undo': nothing to undo", r.startswith("There is nothing to undo"), r)

# ---------------------------------------------------------------- 11. lists, names, undo, fixing after a save
s11 = converse.new_state()
s11["queue_ok"] = True
converse.reply("Mama Ngozi took rice 20000 on credit", s11)
r = converse.reply("Tayo 3k", s11)["text"]
check("'Tayo 3k' (capital, no 'and') while Mama Ngozi's draft waits: a new person", "2 waiting to save" in r
      and "Tayo ₦3,000" in r, r)
r = converse.reply("I mean 25000", s11)["text"]
check("…'I mean 25000' still fixes the latest", "Tayo will pay you ₦25,000" in r, r)
r = converse.reply("rice 5000", s11)["text"]
check("…'rice 5000' (not a person) is a fix, not a customer called Rice", "Rice" not in r, r)
converse.reply("no", s11)
s12 = converse.new_state()
converse.reply("sold rice 15k", s12)
r = converse.reply("and beans 3k", s12)["text"]
check("'and beans 3k' after a sale: another sale, of beans", "beans" in r and "₦3,000" in r and "will pay" not in r, r)
for said, who in [("tobi took 2 bags of rice 30k on credit", "Tobi"), ("emeka never pay 5k", "Emeka"),
                  ("chidi owes me 4500", "Chidi")]:
    s13 = converse.new_state()
    converse.reply(said, s13)
    check(f"lower-case name: '{said}' -> {who}", (s13.get("pending") or {}).get("customer") == who, s13.get("pending"))
for said in ["she owes me 5k", "somebody took 2 bags 10k on credit", "customer owe me 3k"]:
    s14 = converse.new_state()
    converse.reply(said, s14)
    check(f"not a name: '{said}'", not (s14.get("pending") or {}).get("customer"), s14.get("pending"))
dino = lambda: sorted(e["amount"] for e in ledger.entries(limit=500) if e["customer"] == "Dino")  # noqa: E731
before = dino()
s15 = converse.new_state()
converse.reply("dino owes me 20k", s15)
converse.reply("yes", s15)
n0 = entries()
r = converse.reply("no, 25k", s15)["text"]
check("'no, 25k' right after saving: the saved line comes back to change (not saved twice)",
      "Dino will pay you ₦25,000" in r and "Should I save it?" in r and entries() == n0 - 1, r)
converse.reply("yes", s15)
check("…'yes' saves the fixed one: Dino ₦25,000 once (the ₦20,000 is gone)", dino() == sorted(before + [25000]),
      (before, dino()))
for words in ["undo", "delete that", "remove the last one", "cancel that one", "Undo it", "comot am"]:
    s16 = converse.new_state()
    converse.reply("Iya Bisi took beans 8000 on credit", s16)
    converse.reply("yes", s16)
    n0 = entries()
    r = converse.reply(words, s16)["text"]
    check(f"'{words}' removes what was just saved", r.startswith("Removed:") and entries() == n0 - 1, r)
s17 = converse.new_state()
converse.reply("Iya Bisi took beans 8000 on credit", s17)
converse.reply("yes", s17)
s17["last_saved"][0]["at"] -= 11 * 60
n0 = entries()
r = converse.reply("undo", s17)["text"]
check("after 10 minutes 'undo' removes nothing", r.startswith("There is nothing to undo") and entries() == n0, r)
r = converse.reply("undo", converse.new_state(), )["text"]
check("'undo' with nothing saved", r.startswith("There is nothing to undo"), r)
r = converse.reply("Ko si nkan", converse.new_state())["text"]   # a "no" with nothing saved: unchanged behaviour
check("'no' with nothing waiting or saved is not the after-save line", not r.startswith("Sorry. I saved"), r)

# ---------------------------------------------------------------- 12. person questions, periods, the voice's 'he'
ledger.add_entry({"type": "credit_sale", "amount": 7000, "customer": "Kola", "item": "rice"})
for said in ["kola balance?", "check kola", "How much does Kola owe me?"]:
    r = converse.reply(said, converse.new_state())["text"]
    check(f"'{said}': what Kola owes, not what was sold to him", r.startswith("Kola owes you ₦7,000"), r)
for said in ["how much does zainab owe me?", "zainab balance"]:
    r = converse.reply(said, converse.new_state())["text"]
    check(f"'{said}': not in the book, said so (not someone else's debt)", r == "I don't see Zainab in your book yet.", r)
r = converse.reply("how much did i make last month?", converse.new_state())["text"]
check("'last month' alone = the calendar month: numbers, ₦0 when empty", r.startswith("Last month, you sold ₦0"), r)
r = converse.reply("how much have I made in the past 7 days?", converse.new_state())["text"]
check("'the past 7 days'", r.startswith("In the last 7 days, you sold"), r)
import tts  # noqa: E402

for who, word in [("Dino", "Dino still owes you"), ("Mama Ngozi", "she still owes you"), ("Alhaji Musa", "he still owes you")]:
    said = tts.confirmation_text({"type": "credit_sale", "amount": 5000, "customer": who}, "English", balance=9000,
                                 saved=True)
    check(f"the voice says '{word}' (no 'he' guessed from a name)", word in said, said)
os.environ["NATLAS_URL"] = "http://natlas/v1"
import extract  # noqa: E402

llm.chat = lambda *a, **k: ('{"type": "credit_sale", "item": "millions", "quantity": 2, "amount": 3000000, '
                            '"customer": "Mike", "each": true}', "natlas")
rec, _ = extract.extract("mike owes me 3 million")
check("N-ATLaS reading 'millions' as the item: cleared, amount not multiplied", rec["item"] is None
      and rec["quantity"] is None and rec["amount"] == 3000000, rec)
os.environ.pop("NATLAS_URL")

# ---------------------------------------------------------------- 13. never out of context (the live test, 4 Oct night)
# A misheard note came back as an answer about mental health. The AI is never asked about anything but the shop.
os.environ["NATLAS_URL"] = "http://natlas/v1"
ASKED = []


def medical_ai(messages, **k):
    ASKED.append(messages[-1]["content"])
    return ("To reduce stigma around seeking mental health support, it is important to educate people.", "natlas")


llm.chat = medical_ai
for said in ["How can we reduce stigma around seeking mental health support?", "tell me a joke",
             "who is the president of nigeria", "my head is aching, what drug should I take?"]:
    ASKED.clear()
    r = converse.reply(said, converse.new_state())["text"]
    check(f"off topic, the AI is not asked: '{said[:40]}'", r.startswith("I can only help with your shop") and not ASKED
          and "mental" not in r, (r, ASKED))
for lang, said, start in [("Yoruba", "Báwo ni mo ṣe lè sùn dáadáa?", "Ọ̀rọ̀ ṣọ́ọ̀bù rẹ nìkan"),
                          ("Hausa", "Yaya zan rage ciwon kai?", "Harkokin shagonka kawai")]:
    st = converse.new_state()
    st["lang"] = st["prefer"] = lang
    ASKED.clear()
    r = converse.reply(said, st)["text"]
    check(f"off topic in {lang}: said in {lang}, AI not asked", r.startswith(start) and not ASKED, (r, ASKED))
ASKED.clear()
r = assistant.answer("How can we reduce stigma around mental health?", "home", "English")
check("the screen assistant too: the fixed line, the AI not asked", r["text"].startswith("I can only help with your shop")
      and not ASKED, (r, ASKED))
check("insights.ask (any other caller): no answer for it", insights.ask("how do I treat malaria?") == (None, "rules"))
ASKED.clear()
converse.reply("which goods should I stock more for next month?", converse.new_state())
check("a shop question still reaches the AI", bool(ASKED), ASKED)
os.environ.pop("NATLAS_URL")
import asr  # noqa: E402

SENT = {}


class _R:
    status_code = 200

    def json(self):
        return {"data": {"transcript": "Mama Ngozi took rice"}}

    def raise_for_status(self):
        pass


import requests  # noqa: E402

real_post = requests.post
requests.post = lambda url, headers=None, data=None, files=None, timeout=None: SENT.update(data or {}) or _R()
os.environ["INTRON_API_KEY"] = "k"
import wave  # noqa: E402

f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
f.close()
with wave.open(f.name, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(b"\0\0" * 8000)
try:
    asr._intron_transcribe(f.name, "Yoruba")
except Exception as e:  # noqa: BLE001
    print("intron file call:", e)
requests.post = real_post
os.environ.pop("INTRON_API_KEY")
check("Intron file hearing: general, not its default telehealth (medical) mode, and no Intron AI rewriting",
      SENT.get("use_category") == "file_category_general" and SENT.get("use_disable_llm_corrections") == "TRUE", SENT)

print(f"\n{passed}/{total} checks pass")
sys.exit(0 if passed == total else 1)
