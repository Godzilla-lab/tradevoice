"""Nigeria time + "what time is it?" / "what day is today?" in 5 languages, said by code. No keys needed.

python eval/test_clock.py
"""
import datetime as dt
import os
import sys
import tempfile
import time

os.environ["TV_NO_DOTENV"] = "1"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["BOOKS_DIR"] = tempfile.mkdtemp()
os.environ["ACCOUNTS_DB"] = os.path.join(tempfile.mkdtemp(), "a.db")
os.environ.pop("TV_TZ", None)
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith("LOCAL_") or k.startswith("NATLAS"):
        os.environ.pop(k)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import assistant  # noqa: E402
import clock  # noqa: E402
import converse  # noqa: E402
import ledger  # noqa: E402
from extract import fold  # noqa: E402

passed = total = 0


def check(name, cond, got=""):
    global passed, total
    total += 1
    passed += bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  got: {got!r}"))


# Nigeria time: UTC+1 all year, whatever the server's clock says
check("process runs on Nigeria time (UTC+1)", time.localtime().tm_gmtoff == 3600, time.localtime().tm_gmtoff)
utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
check("now() is UTC + 1 hour", abs((clock.now() - utc) - dt.timedelta(hours=1)) < dt.timedelta(seconds=5),
      clock.now() - utc)
late = dt.datetime(2026, 10, 3, 23, 30, tzinfo=dt.timezone.utc)  # 00:30 on 4 Oct in Lagos
check("23:30 UTC is already the next day in Nigeria",
      dt.datetime.fromtimestamp(late.timestamp()).date() == dt.date(2026, 10, 4))
eid = ledger.add_entry({"type": "sale", "amount": 1000, "item": "rice"})
with ledger.conn() as c:
    when = c.execute("SELECT created_at FROM entries WHERE id=?", (eid,)).fetchone()[0]
check("a sale is saved with Nigeria time", abs(dt.datetime.fromisoformat(when) - clock.now()) < dt.timedelta(seconds=5),
      when)

# the answers, at a fixed moment: Saturday 3 Oct 2026, 14:05
AT = dt.datetime(2026, 10, 3, 14, 5)
want = {"English": ("It is 2:05 in the afternoon.", "Today is Saturday, 3 October."),
        "Pidgin": ("Time na 2:05 for afternoon.", "Today na Saturday, 3 October."),
        "Yoruba": ("Aago 2:05 ọ̀sán ni.", "Òní ni Àbámẹ́ta, 3 Ọkútóbà."),
        "Hausa": ("Yanzu ƙarfe 2:05 na rana.", "Yau Asabar ce, 3 ga Oktoba."),
        "Igbo": ("Ugbu a bụ elekere 2:05 n'ehihie.", "Taa bụ Satọdee, 3 Ọktoba.")}
for lang, (t, d) in want.items():
    check(f"{lang}: the time", clock.answer("time", lang, AT) == f"{t} {d}", clock.answer("time", lang, AT))
    check(f"{lang}: the day", clock.answer("date", lang, AT) == d, clock.answer("date", lang, AT))
check("morning / evening / night / midnight",
      [clock.time_text("English", AT.replace(hour=h, minute=0)) for h in (7, 18, 22, 0)]
      == ["It is 7:00 in the morning.", "It is 6:00 in the evening.", "It is 10:00 at night.",
          "It is 12:00 at night."])
check("the AI gets the time in its prompt", clock.now_line(AT) == "Now in Nigeria: Saturday 3 October 2026, 2:05 pm.",
      clock.now_line(AT))
check("who_line starts with Nigeria time", assistant.who_line().startswith("Now in Nigeria: "), assistant.who_line())

# questions it understands, and which language they are in
asks = {"What time is it?": ("time", "English"), "what's the time": ("time", "English"),
        "Wetin be the time?": ("time", "Pidgin"), "What day is today?": ("date", "English"),
        "What is today's date": ("date", "English"), "Today na which day?": ("date", "Pidgin"),
        "Aago mélòó ni?": ("time", "Yoruba"), "Ọjọ́ wo ni òní?": ("date", "Yoruba"),
        "Ƙarfe nawa?": ("time", "Hausa"), "Wace rana ce yau?": ("date", "Hausa"),
        "Kedu oge?": ("time", "Igbo"), "Ụbọchị ole ka taa?": ("date", "Igbo")}
for q, w in asks.items():
    check(f"understood: {q}", clock.asked(fold(q)) == w, clock.asked(fold(q)))
for q in ["What time did Mama Tunde come?", "How much did I sell today?", "Mama Tunde paid 5000 today",
          "Remind Iya Bisi on Friday", "who owes me the most?"]:
    check(f"not a time question: {q}", clock.asked(fold(q)) is None, clock.asked(fold(q)))

# through the chat brain and the Ask TradeVoice screen
r = converse.reply("Karfe nawa?", {})
check("chat: Hausa question gets a Hausa answer, English line under it",
      r["lang"] == "Hausa" and r["text"].startswith("Yanzu ƙarfe") and r["english"].startswith("It is "), r)
r = converse.reply("What day is today?", {"prefer": "Igbo"})
check("chat: the language they picked", r["text"].startswith("Taa bụ "), r["text"])
r = converse.reply("What time is it?", {})
check("chat: English time, no record language", r["text"].startswith("It is ") and "record" not in r["text"], r)
r = assistant.answer("What day is today?", "today", "Yoruba")
check("Ask TradeVoice screen answers the day", r["text"].startswith("Òní ni "), r)
r = converse.reply("Mama Ngozi paid 5000 today", {})
check("a record that says 'today' is still a record", "time" not in r["text"].lower() and r["lang"], r["text"])

print(f"\n{passed}/{total} checks pass")
sys.exit(0 if passed == total else 1)
