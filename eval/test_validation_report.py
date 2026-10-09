"""The NAIC validation page (scripts/validation_report.py) from a made-up pilot log: the team's own phone is left out,
N-ATLaS's share counts its real answers, the window is respected, nothing personal is on the page, and it carries the
N-ATLaS attribution. Made-up numbers only. python eval/test_validation_report.py
"""
import datetime as dt
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
D = tempfile.mkdtemp()
os.environ.update(ACCOUNTS_DB=os.path.join(D, "a.db"), BOOKS_DIR=os.path.join(D, "books"), DB_PATH=os.path.join(D, "t.db"),
                  TEAM_PHONES="2348030000999", TEAM_WHATSAPP="")
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import events  # noqa: E402
import validation_report as vr  # noqa: E402

CHECKS = []


def check(name, ok, got=""):
    CHECKS.append(bool(ok))
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def log(when, kind, phone, channel="web", lang=None, engine=None, ok=True, ms=None):
    events.log(kind, phone, channel, lang=lang, engine=engine, ok=ok, ms=ms)
    with events._db() as c:   # back-date the row just written to the pilot day we want
        c.execute("UPDATE events SET ts=? WHERE id=(SELECT MAX(id) FROM events)", (when.isoformat(timespec="seconds"),))


def main():
    events.ENABLED = True
    day = lambda d, h=10: dt.datetime(2026, 10, d, h, tzinfo=dt.timezone.utc)  # noqa: E731
    A, B, TEAM = "2348030000901", "2348030000902", "2348030000999"
    log(day(6), "web_visit", A); log(day(6), "signup", A, engine="no code")
    log(day(6), "understand", A, lang="Yoruba", engine="live talk", ms=4200)
    log(day(6), "llm", None, engine="natlas:NCAIR1/N-ATLaS", ms=3000)
    log(day(6), "record_saved", A)
    log(day(7), "understand", A, lang="Yoruba", engine="voice", ms=5000)
    log(day(7), "hear", A, lang="Yoruba", engine="natlas:NCAIR1/Yoruba-ASR", ms=2000)
    log(day(7), "llm", None, engine="natlas:NCAIR1/N-ATLaS", ms=3500)
    log(day(7), "message", B, channel="telegram", lang="Hausa", engine="audio")
    log(day(7), "llm", None, engine="natlas", ok=False, ms=20000)
    log(day(7), "llm", None, engine="nvidia/nemotron-3-super-120b-a12b", ms=1500)
    log(day(8), "understand", TEAM, lang="English", engine="ask")      # the team's own testing: left out
    log(day(8), "signup", TEAM)
    log(day(20), "understand", A, lang="Yoruba", engine="ask")         # after the window: left out
    start = dt.datetime(2026, 10, 6, tzinfo=vr.WAT)
    end = dt.datetime(2026, 10, 13, tzinfo=vr.WAT)
    d = vr.collect(start, end)
    check("traders and sign-ups: the team's phone left out", d["traders"] == 2 and d["signups"] == 1 and d["signups_nocode"] == 1, d)
    check("conversations in the window only (the 20 Oct one and the team's left out)", d["conversations"] == 3, d)
    check("N-ATLaS's share counts its real answers: 2 of 3 AI answers", d["natlas_share"] == 67 and d["natlas_failed"] == 1, d)
    check("where they talked: live talk, voice question, Telegram", d["where"] == {"Live talk": 1, "Voice question": 1, "Telegram": 1},
          d["where"])
    check("languages and per day", d["languages"].get("Yoruba") == 2 and list(d["per_day"].values())[:2] == [1, 2], d)
    check("the funnel: opened, signed up, saved, came back", dict(d["funnel"]) == {
        "Opened the app or wrote to a bot": 2, "Signed up": 1, "Saved a record": 1, "Came back another day": 1}, d["funnel"])
    out = os.path.join(D, "v.html")
    vr.main(["--start", "2026-10-06", "--end", "2026-10-12", "--out", out])
    page = open(out, encoding="utf-8").read()
    check("the page: headline numbers and charts", "real-world validation" in page and "<svg" in page and "67%" in page)
    check("…carries the N-ATLaS attribution", vr.ATTRIBUTION in page)
    check("…and nothing personal: no phone numbers", "2348030000" not in page and "08030000" not in page)
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} validation report checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
