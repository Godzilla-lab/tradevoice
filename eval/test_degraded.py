"""Safe without Modal: when the N-ATLaS servers are asleep, broken or gone (no credits left), a trader waits once,
briefly, then never. The backups answer (NVIDIA) and hear (Intron), ONE background check brings N-ATLaS back as soon
as it answers, and NATLAS_MODE=off runs the whole app with no Modal at all. No network: fake servers.

python eval/test_degraded.py
"""
import datetime as dt
import os
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith(("API_KEY", "_URL")) or k.startswith(("NATLAS", "LOCAL_", "WHATSAPP_", "TELEGRAM_", "ASR_", "TEAM_")) \
            or k in ("AUTH_DEMO", "PUBLIC_URL", "LLM_MODELS", "LLM_SHOTS_FOR"):
        os.environ.pop(k)
os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "shared.db"), BOOKS_DIR=tempfile.mkdtemp(),
                  ACCOUNTS_DB=os.path.join(tempfile.mkdtemp(), "a.db"), TRAIN_DIR=tempfile.mkdtemp(), AUTH_DEMO="1",
                  TRADEVOICE_ADMIN="0", AUTH_REQUIRED="1", AUTO_REMINDERS="0", NATLAS_WATCH="0",
                  NVIDIA_API_KEY="x", INTRON_API_KEY="x", NATLAS_URL="https://natlas.test/v1",
                  NATLAS_ASR_URL="https://asr.test", NATLAS_KEY="k")
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import requests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import asr  # noqa: E402
import events  # noqa: E402
import llm  # noqa: E402
import natlas_watch  # noqa: E402
import team  # noqa: E402
import web  # noqa: E402
import whatsapp  # noqa: E402

CHECKS = []


def check(name, ok, got=""):
    ok = bool(ok)
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def until(cond, secs=3.0):
    end = time.time() + secs
    while time.time() < end and not cond():
        time.sleep(0.02)
    return cond()


# ---------------------------------------------------------------- fakes: N-ATLaS, the cloud, the hearing server
class APITimeoutError(Exception):   # the name llm._model_gone looks for
    pass


BRAIN = {"down": False, "calls": []}   # calls: (model, wait given)


def fake_client(kind, timeout, retries=0, model=None):
    def create(**kw):
        BRAIN["calls"].append((kw["model"], timeout))
        if kw["model"] == "natlas" and BRAIN["down"]:
            raise APITimeoutError("Request timed out.")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f"answer from {kw['model']}"))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


llm._client = fake_client
llm.LLM_MODELS[:] = ["cloud/a", "cloud/b"]

PROBE = {"ok": False, "calls": 0}
GATE = threading.Event()


def fake_probe(part):   # the background check: waits until the test says, then answers PROBE["ok"]
    PROBE["calls"] += 1
    GATE.wait(5)
    return PROBE["ok"], "test"


natlas_watch._probe = fake_probe
natlas_watch._ping = lambda part, timeout: (PROBE["ok"], "test")   # Talk-opened pings and market-hours checks

EAR = {"mode": "up", "posts": []}      # up | asleep | gone | loop


class FakeResp:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.body


def fake_post(url, files=None, data=None, headers=None, timeout=None):
    EAR["posts"].append(timeout)
    if EAR["mode"] == "asleep":
        raise requests.exceptions.Timeout("read timed out")
    if EAR["mode"] == "gone":
        return FakeResp(402, {"error": "workspace billing limit reached"})
    if EAR["mode"] == "loop":
        return FakeResp(200, {"text": "kaka nan, kaka nan, kaka nan, kaka nan.", "model": "NCAIR1/Hausa-ASR", "seconds": 2})
    return FakeResp(200, {"text": "Mama Tunde paid 5000", "model": "NCAIR1/NigerianAccentedEnglish", "seconds": 2})


real_post, real_get = requests.post, requests.get
requests.post = fake_post
requests.get = lambda url, headers=None, timeout=None: FakeResp(200, {})
INTRON = []
asr._intron_transcribe = lambda path, language, vocab=None: INTRON.append(language) or {
    "text": "Mama Tunde paid 5000", "language": "pcm", "engine": "intron:sahara"}


def models_called():
    return [m for m, _ in BRAIN["calls"]]


def main():
    events.ENABLED = True   # a temporary accounts.db: /team's log is checked below
    # ============================================================ 1. the brain (N-ATLaS on Modal)
    BRAIN["down"] = True
    with llm.budget(20):   # one chat message's time for the AI (ASK_AI_SECONDS)
        out, used = llm.chat([{"role": "user", "content": "hi"}])
    natlas_wait = next(w for m, w in BRAIN["calls"] if m == "natlas")
    check("N-ATLaS asleep or gone: one short wait (12 s), with time kept for the backup, which answers",
          natlas_wait <= 12 and used == "cloud/a" and models_called() == ["natlas", "cloud/a"], (natlas_wait, BRAIN["calls"]))
    check("…N-ATLaS is marked down for the whole app", llm.natlas_resting("natlas"))
    BRAIN["calls"].clear()
    t0 = time.perf_counter()
    out, used = llm.chat([{"role": "user", "content": "hi again"}])
    check("…the next message doesn't wait on it at all", "natlas" not in models_called() and used == "cloud/a"
          and time.perf_counter() - t0 < 1, BRAIN["calls"])
    BRAIN["calls"].clear()
    out, used = llm.chat([{"role": "user", "content": "Ṣé mo ní gbèsè?"}], models=["natlas", "cloud/a"])
    check("…the Ask chat's own model list (Yoruba: N-ATLaS first) skips it too", models_called() == ["cloud/a"],
          BRAIN["calls"])
    BRAIN["calls"].clear()
    try:
        llm.chat([{"role": "user", "content": "OK?"}], models=["natlas"], timeout=5, deadline=5)
    except RuntimeError:
        pass
    check("…but a check that names N-ATLaS alone (preflight) still asks it", models_called() == ["natlas"])
    check("ONE background check, however many calls failed", PROBE["calls"] == 1, PROBE)

    BRAIN["down"], PROBE["ok"] = False, True
    GATE.set()
    check("the background check finds it answering -> N-ATLaS leads again, by itself",
          until(lambda: not llm.natlas_resting("natlas")))
    BRAIN["calls"].clear()
    out, used = llm.chat([{"role": "user", "content": "hi"}])
    check("…the next message is N-ATLaS's again", llm.is_natlas(used) and models_called() == ["natlas"], BRAIN["calls"])
    rows = [r for r in events.rows(team=True) if r["kind"] in ("natlas_down", "natlas_up")]
    said = [team.describe(r) for r in rows]
    check("/team shows when it stopped (an error, with the backups named) and when it came back",
          len(said) == 2 and said[0][0] == "errors" and "backups took over" in said[0][1]
          and said[1] == ("ai", "N-ATLaS answering again"), said)
    check("…logged as the system's, not on a trader's book", all(not r["who"] for r in rows), rows)

    # ============================================================ 2. hearing voice notes (through the app, logged in)
    c = TestClient(web.app)
    st = c.post("/api/auth/start", json={"phone": "0803 555 0123"}).json()
    c.post("/api/auth/verify", json={"login_id": st["login_id"], "code": st["demo_code"]})
    c.post("/api/auth/me", json={"shop": "Ada Stores", "lang": "English"})

    def hear():
        return c.post("/api/hear", files={"file": ("note.webm", b"0" * 400)},
                      data={"lang": "English", "consent": "yes"})
    PROBE.update(ok=False, calls=0)
    GATE.clear()
    EAR["mode"] = "asleep"
    r = hear()
    check("hearing server asleep: one short try (15 s), then Intron hears this note",
          r.status_code == 200 and r.json().get("heard") == "Mama Tunde paid 5000" and EAR["posts"] == [15.0]
          and INTRON, (r.status_code, r.text, EAR["posts"]))
    EAR["posts"].clear()
    r = hear()
    check("…the next note goes straight to Intron (no try at N-ATLaS while it is down)",
          r.status_code == 200 and EAR["posts"] == [] and len(INTRON) >= 2, (r.text, EAR["posts"]))
    s = c.get("/api/status").json()
    check("/api/status says so (hearing down, Intron hears), with no detail or key in it",
          s["natlas_hearing_down"] and s["hearing_backup"] == "intron" and not s["natlas_down"], s)
    PROBE["ok"] = True
    GATE.set()
    until(lambda: not llm.natlas_resting("natlas_asr"))
    n = len(INTRON)
    EAR["mode"] = "up"
    r = hear()
    check("…back up (the background check): N-ATLaS hears again", r.status_code == 200 and EAR["posts"]
          and len(INTRON) == n, (r.text, EAR["posts"]))

    PROBE.update(ok=False)
    GATE.clear()
    EAR.update(mode="gone", posts=[])
    r = hear()
    check("Modal account with no credits (HTTP 402 at once): Intron hears it, no waiting",
          r.status_code == 200 and len(INTRON) == n + 1 and llm.natlas_resting("natlas_asr"), (r.text, len(INTRON) - n))
    PROBE["ok"] = True
    GATE.set()
    until(lambda: not llm.natlas_resting("natlas_asr"))

    EAR.update(mode="loop", posts=[])
    n = len(INTRON)
    r = hear()
    check("unclear audio while N-ATLaS is up: NOT sent to Intron (team decision), the trader is asked again",
          r.status_code == 502 and len(INTRON) == n and not llm.natlas_resting("natlas_asr"), (r.status_code, r.text))

    os.environ["ASR_DOWN_BACKUP"] = "none"
    PROBE["ok"] = False
    GATE.clear()
    EAR["mode"] = "asleep"
    r = hear()
    check("server down and no backup: 'type it for now', not 'I couldn't hear you' (it isn't their voice)",
          r.status_code == 503 and r.json().get("hearing_down") and r.json()["error"] == web.HEAR_DOWN, r.text)
    check("…WhatsApp and Telegram say the same", "type it" in whatsapp.SAY["hear_down"])
    os.environ.pop("ASR_DOWN_BACKUP")
    PROBE["ok"] = True
    GATE.set()
    until(lambda: not llm.natlas_resting("natlas_asr"))

    # ============================================================ 3. NATLAS_MODE=off: no Modal at all
    os.environ["NATLAS_MODE"] = "off"
    BRAIN["calls"].clear()
    EAR.update(mode="up", posts=[])
    probes = PROBE["calls"]
    out, used = llm.chat([{"role": "user", "content": "hi"}])
    out2, _ = llm.chat([{"role": "user", "content": "Ṣé mo ní gbèsè?"}], models=["natlas", "cloud/a"])
    check("NATLAS_MODE=off: N-ATLaS is never asked, not even first in the Yoruba list", "natlas" not in models_called()
          and used == "cloud/a", BRAIN["calls"])
    n = len(INTRON)
    r = hear()
    check("…voice notes are heard by Intron, no call to the speech server", r.status_code == 200 and EAR["posts"] == []
          and len(INTRON) == n + 1, r.text)
    s = c.get("/api/status").json()
    check("…/api/status: brain NVIDIA, hearing Intron, mode off, nothing kept awake",
          s["brain"] == "nvidia" and s["hearing"] == "intron" and s["natlas_mode"] == "off" and not s["keep_awake"], s)
    natlas_watch._WOKEN["at"] = 0
    natlas_watch.down("natlas", "test")
    check("…opening Talk wakes nothing, and nothing is checked in the background",
          natlas_watch.wake() is False and PROBE["calls"] == probes)
    llm._resting.clear()
    os.environ.pop("NATLAS_MODE")

    # ============================================================ 4. keep-warm days and the team alert
    os.environ["NATLAS_WATCH_DATES"] = "2026-10-11,2026-10-15..2026-10-17"
    on = [natlas_watch._watch_day(dt.datetime(2026, 10, d, 10)) for d in (11, 12, 15, 16, 17, 18)]
    check("NATLAS_WATCH_DATES: kept awake only on the chosen days (saves Modal credits)",
          on == [True, False, True, True, True, False], on)
    os.environ.pop("NATLAS_WATCH_DATES")
    check("…unset: every day, as before", natlas_watch._watch_day(dt.datetime(2026, 10, 12, 10)))
    sent = []
    real_check = natlas_watch.check

    def failing():
        natlas_watch.STATE.update(down=["natlas_asr"], last_error="speech server HTTP 402")
        return False
    natlas_watch.check = failing
    natlas_watch.STATE.update(fails=0, alerted=False)
    PROBE["ok"] = False   # the background check started by the failed check finds it still down
    GATE.clear()
    natlas_watch.step(send=sent.append)
    natlas_watch.step(send=sent.append)
    check("2 failed checks: the team is told which part, and what traders get meanwhile (honestly)",
          len(sent) == 1 and "N-ATLaS hearing" in sent[0] and "NVIDIA" in sent[0] and "Intron" in sent[0]
          and "NATLAS_MODE" in sent[0], sent)
    check("…and the failing part is marked down at once (not only on the next voice note)",
          llm.natlas_resting("natlas_asr") and not llm.natlas_resting("natlas"))
    os.environ.pop("NVIDIA_API_KEY")
    check("no NVIDIA key: the alert says the offline rules answer (not 'the backup models')",
          "offline rules" in natlas_watch.backups())
    os.environ["NVIDIA_API_KEY"] = "x"
    natlas_watch.check = lambda: True
    natlas_watch.step(send=sent.append)
    GATE.set()
    check("back: one 'answering again', both parts cleared", len(sent) == 2 and "again" in sent[1]
          and not llm.natlas_resting("natlas_asr"), sent)
    natlas_watch.check = real_check

    # ============================================================ 5. the pilot check (preflight)
    import preflight
    llm.chat = lambda *a, **k: ("OK", "natlas:NCAIR1/N-ATLaS")
    st_, detail = preflight.natlas_brain()
    check("preflight: N-ATLaS answering is a PASS (it read its own label as a failure before)", st_ == "PASS", detail)
    os.environ["NATLAS_MODE"] = "off"
    st_, detail = preflight.natlas_brain()
    check("…NATLAS_MODE=off: a WARN that says how to turn it back on", st_ == "WARN" and "NATLAS_MODE" in detail, detail)
    os.environ.pop("NATLAS_MODE")
    st_, detail = preflight.without_modal()
    check("'If Modal stops': PASS with NVIDIA and Intron set", st_ == "PASS" and "NVIDIA" in detail
          and "Intron" in detail, detail)
    os.environ.pop("INTRON_API_KEY")
    st_, detail = preflight.without_modal()
    check("…WARN without Intron: says nobody would hear voice notes", st_ == "WARN" and "nobody" in detail, detail)
    os.environ["INTRON_API_KEY"] = "x"

    requests.post, requests.get = real_post, real_get
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} without-Modal checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
