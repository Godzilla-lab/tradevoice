"""Tools v1 (E10): the safe calculator (number provenance), Nigerian dates, market units, the cash check and the
book query; the chat uses them; N-ATLaS only picks a tool (guided JSON) and code does the work; the tool-call set
per language (eval/cases_tools.jsonl) stays at or above today's accuracy. No keys needed.

python eval/test_tools.py
"""
import datetime as dt
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
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "NATLAS")):
        os.environ.pop(k)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import converse  # noqa: E402
import extract  # noqa: E402
import ledger  # noqa: E402
import llm  # noqa: E402
import tools  # noqa: E402

passed = total = 0
T = dt.date(2026, 10, 3)   # a Saturday


def check(name, cond, got=""):
    global passed, total
    total += 1
    passed += bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  got: {got!r}"))


# 1. calculate: plain arithmetic only, every number from the words or the book
v, w = tools.safe_eval("45000 - 45000 * 10%", {45000, 10})
check("10% off ₦45,000 = ₦40,500, working shown the trader's way", v == 40500 and w == "₦45,000 - 10%", (v, w))
v, w = tools.safe_eval("3 x 45,000", {3, 45000})
check("'3 x 45,000' = ₦135,000", v == 135000 and w == "3 × ₦45,000", (v, w))
v, _ = tools.safe_eval("(20000 + 5000) / 5", {20000, 5000, 5})
check("brackets and division", v == 5000)
for bad, why in [("45000 * 0.9", "a number nobody said (0.9)"), ("__import__('os')", "code, not arithmetic"),
                 ("45000 ** 2", "powers"), ("45000 / 0", "divide by zero"), ("9" * 300, "too long")]:
    try:
        tools.safe_eval(bad, {45000, 0, 2})
        check(f"refused: {why}", False)
    except tools.Refused:
        check(f"refused: {why}", True)
r = tools.answer("If I give 10% discount on 45000, how much?")
check("chat: 'That comes to ₦40,500.' + the working", r["text"] == "That comes to ₦40,500.\n₦45,000 - 10% = ₦40,500"
      and r["spoken"] == "That comes to ₦40,500.", r)
ledger.add_entry({"type": "credit_sale", "amount": 63600, "customer": "Mama Tunde", "item": "eggs"})
r = tools.answer("If I give Mama Tunde 10% off what she owes, how much she go pay?")
check("a book number may be used: Mama Tunde owes ₦63,600 -> she will pay ₦57,240",
      r["text"].startswith("Mama Tunde will pay ₦57,240.") and "₦63,600 - 10%" in r["text"], r)
r = tools.run({"tool": "calculate", "expression": "63600 * 0.85"}, "give her small discount", "English")
check("the AI writing a number nobody said: refused, honestly", r["text"].startswith("I can't work that out yet"), r)
r = tools.answer("Wetin be 18000 times 3?", "Pidgin")
check("Pidgin: 'E come be ₦54,000.'", r["text"].startswith("E come be ₦54,000."), r)

# 2. Nigerian dates
check("Easter 2027 = 28 March (computed)", tools.easter(2027) == dt.date(2027, 3, 28))
r = tools.run({"tool": "resolve_date", "holiday": "christmas"}, "When is Christmas?", "English", T)
check("'Christmas is on Friday 25 December, in 83 days.'", r["text"] == "Christmas is on Friday 25 December, in 83 days.",
      r)
r = tools.run({"tool": "resolve_date", "holiday": "sallah"}, "When is Sallah?", "English", T)
check("Sallah: the next Eid, said as EXPECTED (the moon decides)", "expected on Wednesday 10 March 2027" in r["text"]
      and "moon" in r["text"], r)
r = tools.run({"tool": "resolve_date", "holiday": "eid_kabir"}, "Yaushe ne Babbar Sallah?", "Hausa", T)
check("Hausa: Babbar Sallah, 17 May 2027", r["text"].startswith("Ana sa ran Babbar Sallah ranar") and "17 Mayu 2027"
      in r["text"], r)
r = tools.run({"tool": "resolve_date", "holiday": "independence_day"}, "x", "English", dt.date(2026, 10, 1))
check("on the day: 'Independence Day is today.'", r["text"] == "Independence Day is today.", r)
r = tools.run(tools.pick("What date is next Friday?", today=T), "What date is next Friday?", "English", T)
check("'next Friday' = Friday 9 October", r["value"] == "2026-10-09", r)
check("records: 'she go pay after Sallah' = due the day after the expected Eid",
      extract.parse_due("Mama Ngozi took rice 20000, she go pay after Sallah", T) == "2027-03-11")
check("records: 'by Christmas' = 25 Dec", extract.parse_due("I will pay by Christmas", T) == "2026-12-25")
check("records: 'on credit' is not a date", extract.parse_due("Iya Bisi took 5000 on credit", T) is None)

# 3. market units (taught by the trader, kept in their own book) + the fixed ones
r = tools.answer("1 bag of rice is 40 mudu")
check("teach: 'Okay, I'll remember: 1 bag of rice is 40 mudu.'", r["text"] == "Okay, I'll remember: 1 bag of rice is 40 mudu.",
      r)
check("…kept in the trader's own book", ledger.recall("unit", "rice|bag|mudu") == "40.0")
r = tools.answer("How many mudu are in 3 bags of rice?")
check("'3 bags of rice is 120 mudu.'", r["text"] == "3 bags of rice is 120 mudu.", r)
r = tools.answer("If a bag of rice is 45000, how much is one mudu?")
check("price per measure: ₦45,000 ÷ 40 = ₦1,125", r["value"] == 1125 and "₦45,000 ÷ 40 = ₦1,125" in r["text"], r)
check("fixed: 3 crates of eggs = 90", tools.answer("How many eggs in 3 crates?")["value"] == 90)
r = tools.answer("how many cups in a paint?")
check("unknown measure: asks to be taught", r["text"].startswith("I don't know how many cups are in 1 paint yet"), r)

# 4. the cash check
r = tools.answer("I counted 22000 in my hand, is it correct?")
check("nothing in money today -> it says so", "can't check your cash" in r["text"], r)
ledger.add_entry({"type": "sale", "amount": 30000, "item": "rice"})
ledger.add_entry({"type": "expense", "amount": 5000, "item": "transport"})
r = tools.answer("I counted 22000 in my hand, is it correct?")
check("book ₦25,000, counted ₦22,000 -> '₦3,000 is missing'", "should be in your hand today" in r["text"]
      and "₦3,000 is missing" in r["text"] and "₦30,000 - ₦5,000 = ₦25,000" in r["text"], r)
r = tools.answer("I started with 5000, now I have 30000 for my hand. E correct?", "Pidgin")
check("with the opening cash: Pidgin 'E correct.'", "E correct." in r["text"], r)
r = tools.answer("Kuɗin da ke hannuna 26000 ne, ya yi daidai?", "Hausa")
check("Hausa: ₦1,000 more than the book", "₦1,000 fiye da" in r["text"], r)

# 5. the book query (checked building blocks, never raw SQL)
for d, amt, who in [(1, 20000, "Mama Ngozi"), (2, 50000, "Iya Bisi"), (9, 8000, "Mama Ngozi"), (10, 7000, None)]:
    ledger.add_entry({"type": "sale", "amount": amt, "customer": who, "item": "rice"},
                     created_at=dt.datetime(2026, 9, d, 10, 0))
r = tools.run(tools.pick("Which week in September did I sell the most?", today=T), "x", "English", T)
check("which week in September: the week of 31 August (₦70,000)",
      r["text"] == "Your biggest week for sales was the week of 31 August: ₦70,000.", r)
r = tools.run(tools.pick("What was my biggest sale in September?", today=T), "x", "English", T)
check("biggest single sale: ₦50,000 (Iya Bisi)", "₦50,000 (Iya Bisi)" in r["text"], r)
r = tools.run(tools.pick("Which customer bought the most in September?", today=T), "x", "English", T)
check("which customer: Iya Bisi", r["text"] == "Your biggest customer is Iya Bisi: ₦50,000 in sales.", r)
r = tools.run(tools.pick("What is my average sales per day in September?", today=T), "x", "English", T)
check("average per day, with the working: ₦85,000 ÷ 4", r["text"].startswith("On average, you sell ₦21,250 a day")
      and "₦85,000 ÷ 4 = ₦21,250" in r["text"], r)
check("a query with a made-up block is refused", tools.check_spec({"kind": "sold", "metric": "drop table",
                                                                   "group": None}) is False)

# 6. the chat brain uses them, and still records records
st = converse.new_state()
r = converse.reply("When is Christmas?", st)
check("chat: 'When is Christmas?'", r["text"].startswith("Christmas is on"), r)
r = converse.reply("Mama Ngozi took 2 bags of rice for 90000 on credit, she go pay after Sallah", st)
check("…a record with 'after Sallah' is still a record, due after Sallah", st["pending"]["amount"] == 90000
      and st["pending"]["due_date"] == tools.holiday_due("after sallah", dt.date.today()), st.get("pending"))
st = converse.new_state()
r = converse.reply("I sold 3 bags of rice at 45000 each", st)
check("'I sold 3 bags at 45000 each' is a record, not a sum", bool(st.get("pending")), r)

# 7. N-ATLaS picks the tool (guided JSON); code does the work
CALLS = []


def fake_client(kind, timeout, retries=0, model=None):
    def create(**kw):
        CALLS.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
            {"tool": "calculate", "expression": "63600 - 63600 * 20%"})))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


llm._client = fake_client
os.environ["NATLAS_URL"] = "http://natlas/v1"
got = tools.ai_pick("Abeg reduce Mama Tunde debt by 20%, wetin she go pay?", T)
check("N-ATLaS is asked with a JSON schema (guided decoding: valid tool names only)",
      CALLS and CALLS[-1].get("response_format", {}).get("type") == "json_schema"
      and "calculate" in json.dumps(CALLS[-1]["response_format"]), CALLS[-1:] and list(CALLS[-1]))
check("…and gets the book's balances to use", "63600" in CALLS[-1]["messages"][0]["content"])
r = tools.run(got, "Abeg reduce Mama Tunde debt by 20%, wetin she go pay?", "Pidgin", T)
check("…code works it out from the book's number: ₦50,880", r["text"].startswith("E come be ₦50,880."), r)
os.environ.pop("NATLAS_URL")

# 8. the tool-call set (203 sentences, 5 languages): never below today's accuracy (rules only, offline)
sys.argv = [sys.argv[0]]
import run_tools_eval  # noqa: E402

FLOOR = {"English": 1.0, "Pidgin": 1.0, "Yoruba": 0.9, "Hausa": 0.9, "Igbo": 0.9}
table = run_tools_eval.main([])
for lang, (n, right_tool, all_right) in table.items():
    check(f"tool-call set, {lang}: {all_right}/{n} right (floor {FLOOR[lang]:.0%})", all_right / n >= FLOOR[lang])

print(f"\n{passed}/{total} checks pass")
sys.exit(0 if passed == total else 1)
