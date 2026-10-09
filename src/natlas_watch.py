"""Keeps N-ATLaS warm when it matters, notices at once when it is down, and tells the TEAM (never traders).

One health record for the whole app (llm._resting): "natlas" = the brain, "natlas_asr" = the hearing server.
- A failed call (a message, a voice note) marks that part down (down()). From the next call nothing waits on it:
  the backups answer and hear. ONE background check asks that server every NATLAS_RECHECK seconds (120) until it
  answers, then N-ATLaS leads again. A sleeping GPU is woken by that same check; a Modal account with no credits
  left costs traders one short wait, then none.
- Every NATLAS_WATCH_EVERY minutes in market hours (NATLAS_WATCH_HOURS, Nigeria time, default 7-20) it asks both
  servers if they are up. That ping also keeps the Modal GPUs awake (they sleep after 60 idle minutes), so traders
  don't wait for the first reply of the day. It costs GPU hours, so NATLAS_WATCH_DATES (e.g.
  "2026-10-11,2026-10-15..2026-10-17") keeps them warm only on those days; on other days the first message wakes
  them and the backups answer meanwhile.
- 2 failed checks in a row -> one message to the team (TEAM_TELEGRAM / TEAM_WHATSAPP); one more when it is back.
- NATLAS_MODE=off: no checks, no wake-ups, N-ATLaS is not used at all (the app runs on the backups).
Note: WhatsApp only delivers a free-form message if that team number messaged the bot in the last 24 hours.
"""
import datetime as dt
import os
import threading
import time

STATE = {"ok": None, "fails": 0, "alerted": False, "last_check": None, "last_ms": None, "last_error": None,
         "down": []}
PARTS = {"natlas": ("NATLAS_URL", "/models"), "natlas_asr": ("NATLAS_ASR_URL", "/health")}
NAMES = {"natlas": "N-ATLaS (answers)", "natlas_asr": "N-ATLaS hearing (voice notes)"}
_PROBING, _LOCK = set(), threading.Lock()


def _nigeria_now():
    return dt.datetime.utcnow() + dt.timedelta(hours=1)  # Nigeria = UTC+1, no daylight saving


def _market_hours(now=None):
    start, end = (int(x) for x in os.getenv("NATLAS_WATCH_HOURS", "7-20").split("-"))
    now = now or _nigeria_now()
    return start <= now.hour < end


def _watch_day(now=None):
    """NATLAS_WATCH_DATES unset: every day. Else only those dates ("2026-10-11,2026-10-15..2026-10-17")."""
    days = os.getenv("NATLAS_WATCH_DATES", "").strip()
    if not days:
        return True
    today = (now or _nigeria_now()).date()
    for part in days.split(","):
        a, _, b = part.strip().partition("..")
        try:
            if dt.date.fromisoformat(a.strip()) <= today <= dt.date.fromisoformat((b or a).strip()):
                return True
        except ValueError:
            continue
    return False


def _on(part):
    import llm
    return llm.natlas_on() if part == "natlas" else llm.natlas_hearing_on()


def _ping(part, timeout):
    """Does this N-ATLaS server answer? (a sleeping one is woken by the same request and answers when up)"""
    import requests
    env, path = PARTS[part]
    try:
        r = requests.get(os.environ[env].rstrip("/") + path, timeout=timeout,
                         headers={"Authorization": f"Bearer {os.getenv('NATLAS_KEY', 'none')}"})
        return r.status_code == 200 and (part != "natlas" or "natlas" in r.text), f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def check():
    """One health check of both servers. Returns True if every N-ATLaS server that is set up answered."""
    t = time.perf_counter()
    ok, STATE["last_error"], STATE["down"] = True, None, []
    for part in PARTS:
        if not _on(part):
            continue
        up, why = _ping(part, 300)
        if not up:
            ok = False
            STATE["down"].append(part)
            STATE["last_error"] = why if part == "natlas" else f"speech server {why}"
    STATE["last_check"], STATE["last_ms"] = time.time(), round((time.perf_counter() - t) * 1000)
    return ok


def _log(kind, part, ok, note="", ms=None):
    """For /team. Logged from the background thread, so it isn't put on the trader whose message found it down."""
    try:
        import events
        events.log(kind, engine=f"{part} {note}".strip(), ok=ok, ms=ms)
    except Exception:  # noqa: BLE001
        pass


def down(part, why=""):
    """A call to N-ATLaS failed (or a check did): stop waiting on it now, and start ONE background check that brings
    it back as soon as it answers. Never waits, never raises."""
    import llm
    llm._resting[part] = max(llm._resting.get(part, 0), time.time() + float(os.getenv("NATLAS_RECHECK", "120")) + 30)
    with _LOCK:
        if part in _PROBING or not _on(part):
            return
        _PROBING.add(part)
    threading.Thread(target=_recover, args=(part, time.time(), why), daemon=True).start()


def up(part):
    import llm
    llm._resting.pop(part, None)


def _recover(part, since, why=""):
    import llm
    every = float(os.getenv("NATLAS_RECHECK", "120"))
    _log("natlas_down", part, False, why or "no answer")
    try:
        while part in llm._resting and _on(part):   # someone saw it answer (or the team switched it off): done
            llm._resting[part] = time.time() + 330         # still down while we ask (a waking GPU takes 1-3 min)
            ok, _ = _probe(part)
            if ok:
                up(part)
                _log("natlas_up", part, True, ms=(time.time() - since) * 1000)
                return
            if part not in llm._resting:
                return
            llm._resting[part] = time.time() + every + 30
            time.sleep(every)
    finally:
        with _LOCK:
            _PROBING.discard(part)


def _probe(part):
    return _ping(part, 300)


def backups():
    """What traders get while N-ATLaS is down, said plainly (team alert, /team, /api/status)."""
    import asr
    brain = ("the NVIDIA cloud models" if os.getenv("NVIDIA_API_KEY") else
             "our backup GPU model" if os.getenv("LOCAL_LLM_URL") else "the offline rules only (no AI)")
    hear = asr.down_backup_name()
    hear = f"{hear.title()}" if hear else "nobody (traders are asked to type)"
    return f"Answers come from {brain}; voice notes are heard by {hear}."


_WOKEN = {"at": 0.0}


def wake():
    """Someone opened Talk: make sure both N-ATLaS servers are up BEFORE the voice note arrives (a sleeping server
    takes minutes to start; this way it starts while the trader is still talking). At most once a minute; never
    waits, never raises. Needs nothing in .env beyond the N-ATLaS links."""
    parts = [p for p in PARTS if _on(p)]
    if not parts or time.time() - _WOKEN["at"] < 60:
        return False
    _WOKEN["at"] = time.time()

    def ping(part):
        import llm
        answered = threading.Event()

        def asleep():   # no answer in 3 s = it is starting up: the backups answer until it is up, so nobody waits
            if not answered.wait(3):   # 12 s per message for a server that needs minutes (a warm one: ~0.2 s)
                llm._resting[part] = max(llm._resting.get(part, 0), time.time() + 600)
        threading.Thread(target=asleep, daemon=True).start()
        try:
            ok, why = _ping(part, 300)
        finally:
            answered.set()
        if ok:
            up(part)   # up: N-ATLaS answers (and hears) again from the next message
        else:
            down(part, why)
    for part in parts:
        threading.Thread(target=ping, args=(part,), daemon=True).start()
    return True


def _tell_team(text):
    import telegram
    import whatsapp
    telegram.tell_team(text)   # TEAM_TELEGRAM chat ids, if set
    for to in filter(None, (n.strip() for n in os.getenv("TEAM_WHATSAPP", "").split(","))):
        try:
            whatsapp.send_first(to, "alert", text)   # 24 h window, else the alert template, else /team shows it
        except Exception as e:  # noqa: BLE001
            print(f"team alert to WhatsApp failed: {type(e).__name__}")


def step(send=_tell_team):
    """Run one check and alert on changes (2 fails in a row = down; first success after = recovered)."""
    ok = check()
    if ok:
        for part in PARTS:
            up(part)
        if STATE["alerted"]:
            send("TradeVoice: N-ATLaS is answering again.")
        STATE.update(ok=True, fails=0, alerted=False)
        return
    for part in STATE.get("down") or []:
        down(part, STATE["last_error"] or "")
    STATE["fails"] += 1
    STATE["ok"] = False
    print(f"N-ATLaS health check failed ({STATE['fails']}x): {STATE['last_error']}")
    if STATE["fails"] >= 2 and not STATE["alerted"]:
        which = " and ".join(NAMES[p] for p in STATE.get("down") or []) or "N-ATLaS"
        send(f"TradeVoice: {which} is not answering ({STATE['last_error']}). {backups()} "
             "Check: modal app logs tradevoice-natlas, then python scripts/check_models.py --natlas. "
             "To run without Modal: keys.sh NATLAS_MODE, then off.")
        STATE["alerted"] = True


def start():
    import llm
    if not (llm.natlas_on() or llm.natlas_hearing_on()) or os.getenv("NATLAS_WATCH", "1") != "1":
        return

    def loop():
        while True:
            if _market_hours() and _watch_day():
                try:
                    step()
                except Exception as e:  # noqa: BLE001
                    print(f"N-ATLaS watch failed: {type(e).__name__}: {e}")
            time.sleep(60 * float(os.getenv("NATLAS_WATCH_EVERY", "10")))
    threading.Thread(target=loop, daemon=True).start()
