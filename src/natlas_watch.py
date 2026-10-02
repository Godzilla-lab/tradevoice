"""Keeps N-ATLaS warm in market hours and tells the TEAM (never traders) when it stops answering.

Runs inside the web app (started from web.py). Every NATLAS_WATCH_EVERY minutes during market hours
(NATLAS_WATCH_HOURS, Nigeria time, default 7-20) it asks the N-ATLaS server for its model list:
- that ping also keeps the Modal GPU awake (it sleeps after 60 idle minutes), so traders don't wait 4 minutes
  for the first reply of the day;
- 2 failed checks in a row -> one WhatsApp to TEAM_WHATSAPP (comma-separated numbers); one more when it is back.
Outside market hours it does nothing, so the GPU can sleep (no cost overnight).
Note: WhatsApp only delivers a free-form message if that team number messaged the bot in the last 24 hours.
"""
import datetime as dt
import os
import threading
import time

STATE = {"ok": None, "fails": 0, "alerted": False, "last_check": None, "last_ms": None, "last_error": None}


def _market_hours(now=None):
    start, end = (int(x) for x in os.getenv("NATLAS_WATCH_HOURS", "7-20").split("-"))
    now = now or dt.datetime.utcnow() + dt.timedelta(hours=1)  # Nigeria = UTC+1, no daylight saving
    return start <= now.hour < end


def check():
    """One health check. Returns True if N-ATLaS answered."""
    import requests
    t = time.perf_counter()
    try:
        r = requests.get(os.environ["NATLAS_URL"].rstrip("/") + "/models", timeout=300,
                         headers={"Authorization": f"Bearer {os.getenv('NATLAS_KEY', 'none')}"})
        ok = r.status_code == 200 and "natlas" in r.text
        STATE["last_error"] = None if ok else f"HTTP {r.status_code}"
        if os.getenv("NATLAS_ASR_URL"):   # the speech models too (same warm-up, same alert)
            a = requests.get(os.environ["NATLAS_ASR_URL"].rstrip("/") + "/health", timeout=300,
                             headers={"Authorization": f"Bearer {os.getenv('NATLAS_KEY', 'none')}"})
            if a.status_code != 200:
                ok, STATE["last_error"] = False, f"speech server HTTP {a.status_code}"
    except Exception as e:  # noqa: BLE001
        ok, STATE["last_error"] = False, type(e).__name__
    STATE["last_check"], STATE["last_ms"] = time.time(), round((time.perf_counter() - t) * 1000)
    return ok


_WOKEN = {"at": 0.0}


def wake():
    """Someone opened Talk: make sure both N-ATLaS servers are up BEFORE the voice note arrives (a sleeping server
    takes minutes to start; this way it starts while the trader is still talking). At most once a minute; never
    waits, never raises. Needs nothing in .env beyond the N-ATLaS links."""
    if not (os.getenv("NATLAS_URL") or os.getenv("NATLAS_ASR_URL")) or time.time() - _WOKEN["at"] < 60:
        return False
    _WOKEN["at"] = time.time()

    def ping(env, path):
        import requests

        import llm
        answered, ok = threading.Event(), False
        if env == "NATLAS_URL":   # no answer in 3 s = it is starting up: the backups answer until it is up, so
            def asleep():         # nobody waits 20 s for a brain that needs minutes (a warm one answers in ~0.2 s)
                if not answered.wait(3):
                    llm._resting["natlas"] = time.time() + 600
            threading.Thread(target=asleep, daemon=True).start()
        try:
            r = requests.get(os.environ[env].rstrip("/") + path, timeout=300,
                             headers={"Authorization": f"Bearer {os.getenv('NATLAS_KEY', 'none')}"})
            ok = r.status_code == 200
        except Exception:  # noqa: BLE001
            pass
        finally:
            answered.set()
        if env == "NATLAS_URL" and ok:
            llm._resting.pop("natlas", None)   # up: N-ATLaS answers again from the next message
    for env, path in (("NATLAS_URL", "/models"), ("NATLAS_ASR_URL", "/health")):
        if os.getenv(env):
            threading.Thread(target=ping, args=(env, path), daemon=True).start()
    return True


def _tell_team(text):
    import whatsapp
    for to in filter(None, (n.strip() for n in os.getenv("TEAM_WHATSAPP", "").split(","))):
        try:
            whatsapp.send_text(to, text)
        except Exception as e:  # noqa: BLE001
            print(f"team alert to WhatsApp failed: {type(e).__name__}")


def step(send=_tell_team):
    """Run one check and alert on changes (2 fails in a row = down; first success after = recovered)."""
    ok = check()
    if ok:
        if STATE["alerted"]:
            send("TradeVoice: N-ATLaS is answering again.")
        STATE.update(ok=True, fails=0, alerted=False)
        return
    STATE["fails"] += 1
    STATE["ok"] = False
    print(f"N-ATLaS health check failed ({STATE['fails']}x): {STATE['last_error']}")
    if STATE["fails"] >= 2 and not STATE["alerted"]:
        send(f"TradeVoice: N-ATLaS (text or speech) is not answering ({STATE['last_error']}). Traders are being served by the "
             "backup models. Check: modal app logs tradevoice-natlas, then python scripts/check_models.py --natlas")
        STATE["alerted"] = True


def start():
    if not os.getenv("NATLAS_URL") or os.getenv("NATLAS_WATCH", "1") != "1":
        return

    def loop():
        while True:
            if _market_hours():
                try:
                    step()
                except Exception as e:  # noqa: BLE001
                    print(f"N-ATLaS watch failed: {type(e).__name__}: {e}")
            time.sleep(60 * float(os.getenv("NATLAS_WATCH_EVERY", "10")))
    threading.Thread(target=loop, daemon=True).start()
