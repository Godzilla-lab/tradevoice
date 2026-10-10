"""Intron keys: the main one and up to two spares, so voice replies, live talk and the backup hearing keep going
when a key runs out of credit or is refused.

INTRON_API_KEY, INTRON_API_KEY_2, INTRON_API_KEY_3 (keys.sh). The first key that is not resting is used. When Intron
refuses a key (401/402/403, or its message says auth, credit, quota, balance...), that key rests for INTRON_KEY_REST
minutes (default 60) and the next one is used at once. The team is told once per change (Telegram / WhatsApp, the same
alerts as N-ATLaS), and /team shows it. A key is never printed, logged or sent anywhere but to Intron: they are
"key 1", "key 2" and "key 3" everywhere else.
"""
import os
import re
import threading
import time

NAMES = ("INTRON_API_KEY", "INTRON_API_KEY_2", "INTRON_API_KEY_3")
_REFUSAL = re.compile(r"\b(401|402|403)\b|auth|credit|quota|exhaust|insufficient|forbidden|unauthori|balance|"
                      r"permission|access.key|payment", re.I)
_lock = threading.Lock()
_rest = {}            # label -> (until, why)
_told = {"last": None}   # the last state the team was told about (one alert per change)


def _keys():
    """[(label, value)] for the keys that are set, in order."""
    return [(f"key {i}", os.getenv(n, "").strip()) for i, n in enumerate(NAMES, 1) if os.getenv(n, "").strip()]


def available():
    """Is any Intron key set?"""
    return bool(_keys())


def count():
    return len(_keys())


def _resting(label, now=None):
    until = _rest.get(label, (0, ""))[0]
    return (now or time.time()) < until


def pick(skip=()):
    """(label, value) of the first key that is not resting (and not in skip), or None when all are resting."""
    now = time.time()
    with _lock:
        for label, value in _keys():
            if label not in skip and not _resting(label, now):
                return label, value
    return None


def head(picked):
    return {"Authorization": f"Bearer {picked[1]}"}


def refusal(what):
    """Does this status code or message mean Intron refused the key itself (auth, credit, quota)?"""
    return bool(_REFUSAL.search(str(what or "")))


def _scrub(text):
    text = str(text or "")
    for _, value in _keys():
        text = text.replace(value, "***")
    return text[:120]


def refused(label, why):
    """Intron refused this key: it rests, the next key is used. Tells the team once per change. Never raises."""
    why = _scrub(why)
    minutes = float(os.getenv("INTRON_KEY_REST", "60"))
    with _lock:
        _rest[label] = (time.time() + minutes * 60, why)
    nxt = pick()
    try:
        import events
        events.log("intron_key", engine=f"{label}: {why[:60]}", ok=False)
    except Exception:  # noqa: BLE001
        pass
    state = (label, nxt[0] if nxt else None)
    if _told["last"] == state:
        return nxt
    _told["last"] = state
    if nxt:
        msg = f"TradeVoice: Intron {label} was refused ({why}). Using {nxt[0]} now."
    else:
        msg = (f"TradeVoice: every Intron key was refused ({label}: {why}). Voice replies are text and live talk "
               "uses the N-ATLaS hearing until a key works again. Top up Intron, or add a key: "
               "sudo bash /opt/tradevoice/app/deploy/server/keys.sh INTRON_API_KEY_2")
    print(msg)
    threading.Thread(target=_tell, args=(msg,), daemon=True).start()
    return nxt


def _tell(msg):
    try:
        import natlas_watch
        natlas_watch._tell_team(msg)
    except Exception as e:  # noqa: BLE001
        print(f"Intron key alert not sent: {type(e).__name__}")


def ok(label):
    """A key worked: if it had been the reason for an alert, the next refusal alerts again."""
    if _told["last"] and _told["last"][0] == label:
        _told["last"] = None


def states():
    """[{"key": "key 1", "state": "in use" | "spare" | "resting until 14:05 (credit)"}] (no key values)."""
    now, current = time.time(), pick()
    out = []
    for label, _ in _keys():
        if _resting(label, now):
            until, why = _rest[label]
            state = f"resting until {time.strftime('%H:%M', time.localtime(until))} ({why[:40]})"
        else:
            state = "in use" if current and current[0] == label else "spare"
        out.append({"key": label, "state": state})
    return out


def reset():
    """Tests: forget every rest and alert."""
    with _lock:
        _rest.clear()
    _told["last"] = None
