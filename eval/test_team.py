"""Interaction log + /team dashboard: real WhatsApp flow through the webhook, then the counts, the N-ATLaS share,
privacy (no names/amounts/messages/phone numbers stored) and access (ADMIN_TOKEN only). No keys needed.

python eval/test_team.py
"""
import hashlib
import hmac
import json
import re
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["BOOKS_DIR"] = tempfile.mkdtemp()
os.environ["ACCOUNTS_DB"] = os.path.join(tempfile.mkdtemp(), "a.db")
os.environ["TRAIN_DIR"] = tempfile.mkdtemp()
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith("LOCAL_") or k.startswith("WHATSAPP_") or k.startswith("NATLAS"):
        os.environ.pop(k)
os.environ.update(WHATSAPP_TOKEN="test", WHATSAPP_PHONE_ID="123", WHATSAPP_VERIFY_TOKEN="tv-verify",
                  WHATSAPP_APP_SECRET="s3cret", TRADEVOICE_ADMIN="0", ADMIN_TOKEN="team-secret-1",
                  AUTO_REMINDERS="0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import events  # noqa: E402
import llm  # noqa: E402
import web  # noqa: E402
import whatsapp  # noqa: E402

whatsapp.graph_post = lambda p: {"messages": [{"id": "x"}]}
whatsapp.send_voice = lambda to, text, lang: None
client = TestClient(web.app)
PHONE = "2348000000007"
passed = total = 0
n = 0


def check(name, cond, got=""):
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"{'✓' if cond else '✗'} {name}" + ("" if cond else f"\n    got: {got}"))


def post(msg):
    global n
    n += 1
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"from": PHONE, "id": f"m{n}", **msg}]}}]}]})
    sig = "sha256=" + hmac.new(b"s3cret", body.encode(), hashlib.sha256).hexdigest()
    r = client.post("/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": sig,
                                                                "Content-Type": "application/json"})
    assert r.status_code == 200, r.text


# 0. off by default (tests/benchmarks never pollute the evidence); the server turns it on
events.log("message", PHONE, "whatsapp")
check("event log is OFF unless the server turned it on", events.rows() == [])
events.ENABLED = True

# 1. a real WhatsApp sign-up and a record, through the webhook (offline rules, no AI)
post({"type": "text", "text": {"body": "hi"}})
post({"type": "interactive", "interactive": {"type": "list_reply", "list_reply": {"id": "lang:English"}}})
post({"type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": "consent:yes"}}})
post({"type": "text", "text": {"body": "Mama Tunde owe me 45k for rice"}})
post({"type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": "yes"}}})
# 2. which model answered (as llm.chat logs it)
llm._event("llm", "natlas:NCAIR1/N-ATLaS", True, 0)
llm._event("llm", "natlas:NCAIR1/N-ATLaS", True, 0)
llm._event("llm", "natlas", False, 0)
llm._event("llm", "nvidia/nemotron-3-super-120b-a12b", True, 0)

s = events.summary()
check("one trader, on WhatsApp", s["traders_total"] == 1 and s["channels"]["whatsapp"] == 1, s)
check("funnel: message -> language -> consent -> record saved",
      s["funnel"]["first message / visit"] == 1 and s["funnel"]["chose language"] == 1
      and s["funnel"]["agreed (consent)"] == 1 and s["funnel"]["saved a record"] == 1, s["funnel"])
check("5 interactions counted, 1 record saved", s["interactions"] == 5 and s["records_saved"] == 1, s)
check("N-ATLaS share = N-ATLaS answers / all answers (2 of 3 = 67%), failures shown apart",
      s["natlas_share"] == 67 and s["understanding"].get("natlas (failed)") == 1, s["understanding"])
check("licence counter: 1 active trader in 30 days, no warning yet",
      s["active_30d"] == 1 and not s["licence_warn"], s)

# 3. privacy: nothing identifying in the log
dump = json.dumps(events.rows(), ensure_ascii=False)
check("no phone number, name, amount or message text stored",
      PHONE not in dump and "Tunde" not in dump and not re.search(r"45,?000|45k", dump) and "rice" not in dump,
      dump[:300])

# 4. access
check("/team without the key -> 403", client.get("/team").status_code == 403)
check("/team with a wrong key -> 403", client.get("/team?key=nope").status_code == 403)
page = client.get("/team?key=team-secret-1")
check("/team with ADMIN_TOKEN -> the dashboard, with the N-ATLaS attribution",
      page.status_code == 200 and "N-ATLaS share" in page.text and "powered by Awarri Technologies" in page.text)
check("dashboard shows no phone number or name", PHONE not in page.text and "Tunde" not in page.text)
csv = client.get("/team/export.csv", headers={"x-admin-key": "team-secret-1"})
check("CSV export (header key works too): anonymised rows", csv.status_code == 200
      and csv.text.startswith("ts,who,channel,kind") and PHONE not in csv.text)

# 5. the live dashboard's data: team key on every call; actions for everyone, words only for traders who said yes
import team  # noqa: E402
import training  # noqa: E402
K = {"x-admin-key": "team-secret-1"}
check("dashboard data needs the team key", all(client.get(u).status_code == 403 for u in (
    "/team/api/overview", "/team/api/feed", "/team/api/conversations", "/team/media/0123456789abcdef/x.wav")))
o = client.get("/team/api/overview?period=today", headers=K).json()
check("overview: today's numbers, by the hour (24), with the day before to compare",
      len(o["series"]) == 24 and o["kpi"]["conversations"] >= 1 and "prev" in o and o["kpi"]["active"] == 1, o["kpi"])
check("overview: N-ATLaS's share counts its real answers ('natlas:NCAIR1/N-ATLaS'): 2 of 3 answers = 67%",
      o["kpi"]["natlas_share"] == 67, o["kpi"])
sp = {name: n for name, n, *_ in events.speed(1)}
check("speed table: N-ATLaS's answers are 'brain (N-ATLaS)', not counted as the backup AI",
      sp.get("brain (N-ATLaS)") == 2 and sp.get("brain (backup AI)") == 1, sp)
check("overview: 7 and 30 days, by the day", len(client.get("/team/api/overview?period=7d", headers=K).json()["series"]) == 7
      and len(client.get("/team/api/overview?period=30d", headers=K).json()["series"]) == 30)
f = client.get("/team/api/feed", headers=K)
rows = f.json()["rows"]
check("live activity: every action in words, newest first, never the phone number",
      rows and rows[0]["id"] > rows[-1]["id"] and any(r["what"].startswith("WhatsApp message") for r in rows)
      and PHONE not in f.text, [r["what"] for r in rows[:5]])
check("live activity: only what is new after the last one seen",
      client.get(f"/team/api/feed?after={rows[0]['id']}", headers=K).json()["rows"] == [])
me = events._hash(PHONE)
st = client.get(f"/team/api/feed?who={me}", headers=K).json()["stats"]
check("one trader: their all-time numbers", st["conversations"] >= 1 and st["first"] <= st["last"], st)
check("a failed step reads as a problem, in words", team.describe({"kind": "llm", "engine": "natlas", "ok": 0, "lang": ""})
      == ("errors", "N-ATLaS didn't answer in time (a backup AI answered)")
      and team.describe({"kind": "hear", "engine": "intron", "ok": 0, "lang": ""}) == ("errors", "Heard speech: failed"))
check("what traders said: nothing for a trader who hasn't said yes",
      client.get("/team/api/conversations", headers=K).json()["items"] == [])
training.set_answer(PHONE, True)
training.keep_turn("live_turn", "Iya Bisi took rice", "Iya Bisi took rice. How much was it?", "English", phone=PHONE)
wav = os.path.join(tempfile.mkdtemp(), "v.wav")
open(wav, "wb").write(b"RIFF....WAVEfake")
training.keep(wav, "voice", "English", {"text": "Iya Bisi took rice"}, phone=PHONE)
items = client.get("/team/api/conversations", headers=K).json()["items"]
check("…after yes: what they said, TradeVoice's reply, and their voice note to play",
      {x["kind"] for x in items} == {"live_turn", "voice"} and any(x["reply"] for x in items)
      and any(x["media"] == "audio" and x["file"] for x in items), items)
link = next(x["file"] for x in items if x["file"])
check("…the voice note plays only with the team key, and no path leaves the trader's folder",
      client.get(link).status_code == 403 and client.get(link, headers=K).status_code == 200
      and client.get(f"/team/media/{me}/manifest.jsonl", headers=K).status_code == 404
      and client.get(f"/team/media/{me}/..%2F..%2Fa.db", headers=K).status_code == 404)
page = client.get("/team?key=team-secret-1")
check("the page itself holds no data (it loads it with the key) and is never indexed or cached",
      PHONE not in page.text and page.headers.get("cache-control") == "no-store"
      and page.headers.get("x-robots-tag") == "noindex")

os.environ["ADMIN_TOKEN"] = ""
check("no ADMIN_TOKEN set -> /team closed for everyone", client.get("/team?key=").status_code == 403)

# speed report (scripts/speed.py, deploy/server/speed.sh): times per step of a voice turn, nothing else
import contextlib  # noqa: E402
import io  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import speed  # noqa: E402

events.ENABLED = True
for ms in (2100, 2500, 9000):
    events.log("hear", engine="natlas:NCAIR1/NigerianAccentedEnglish", ms=ms)
for ms in (3000, 3400):
    events.log("llm", engine="natlas", ms=ms)
events.log("voice", engine="intron", lang="English", ms=1800)
events.log("voice", engine="cache", lang="English")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    speed.main(["--days", "1"])
txt = out.getvalue()
line = next((x for x in txt.splitlines() if x.startswith("hearing")), "")
check("speed report: typical / slow / slowest per step, in seconds",
      line.split()[1:] == ["3", "2.5", "9.0", "9.0"] and "brain (N-ATLaS)" in txt and "voice (Intron)" in txt)
check("speed report: times only (no phone, no words)", PHONE not in txt)

# the team's own phones are left out of the NAIC numbers (TEAM_PHONES, and TEAM_WHATSAPP)
before = events.summary()["interactions"]
events.log("message", "2348000000771", "whatsapp", engine="text")    # a trader
events.log("message", "2348000000772", "whatsapp", engine="text")    # the team, testing
events.log("web_visit", "2348000000772", "web")
os.environ["TEAM_PHONES"] = "08000000772"
s2 = events.summary()
check("team phones (TEAM_PHONES) are left out of interactions and traders; the trader still counts",
      s2["interactions"] == before + 1 and s2["team_left_out"] == 1)
check("…and out of the CSV export and the speed report's rows", all(
    r["who"] != events._hash("2348000000772") for r in events.rows()) and any(
    r["who"] == events._hash("2348000000772") for r in events.rows(team=True)))
os.environ.pop("TEAM_PHONES")

print(f"\n{passed}/{total} team dashboard checks pass")
sys.exit(0 if passed == total else 1)
