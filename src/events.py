"""Interaction log for the team dashboard (/team) and the NAIC evidence (real interactions, N-ATLaS share).

Privacy: no amounts, names, message text or audio, ever. A trader is a salted hash of their number (the salt lives
only in accounts.db), so the export can be shared without identifying anyone. Logging never breaks the app.

One row per event: ts, who (hash or ""), channel (whatsapp/web/""), kind, lang, engine, ok, ms.
Kinds: message (a trader's WhatsApp message: detail in engine = text/audio/image/interactive), web_visit,
lang_set, consent, record_saved, llm, hear, voice.
"""
import contextvars
import datetime as dt
import hashlib
import os
import secrets
import sqlite3
import threading

CHANNEL = contextvars.ContextVar("channel", default="")
# Only the running server records events (web.py turns this on at startup). Tests and benchmarks never do, so test
# traffic can't pollute the NAIC evidence.
ENABLED = False
_lock = threading.Lock()
_salt = None


def _db():
    import accounts
    c = sqlite3.connect(accounts.ACCOUNTS_DB, timeout=5)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, who TEXT, channel TEXT, kind TEXT NOT NULL,
                                       lang TEXT, engine TEXT, ok INTEGER, ms INTEGER);
    CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    return c


def _hash(phone):
    global _salt
    if not phone:
        return ""
    if _salt is None:
        with _db() as c:
            row = c.execute("SELECT value FROM meta WHERE key='salt'").fetchone()
            if not row:
                c.execute("INSERT OR IGNORE INTO meta VALUES ('salt', ?)", (secrets.token_hex(16),))
                row = c.execute("SELECT value FROM meta WHERE key='salt'").fetchone()
            _salt = row["value"]
    return hashlib.sha256((_salt + phone).encode()).hexdigest()[:16]


def _current_phone():
    """The trader whose book is open right now (web request or WhatsApp message), if any."""
    try:
        import ledger
        path = ledger._BOOK.get()
    except Exception:  # noqa: BLE001
        return None
    name = os.path.splitext(os.path.basename(path or ""))[0]
    return name if name.isdigit() else None


def log(kind, phone=None, channel=None, lang=None, engine=None, ok=True, ms=None):
    """Record one event. Never raises."""
    if not ENABLED:
        return
    try:
        import accounts
        phone = phone or _current_phone()
        if phone and accounts.is_guest(phone):
            who = "g" + _hash(phone)[:15]          # guests counted, marked as such
        else:
            who = _hash(phone)
        with _lock, _db() as c:
            c.execute("INSERT INTO events (ts, who, channel, kind, lang, engine, ok, ms) VALUES (?,?,?,?,?,?,?,?)",
                      (dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), who,
                       channel if channel is not None else CHANNEL.get(), kind, lang, (engine or "")[:80],
                       int(bool(ok)), None if ms is None else int(ms)))
    except Exception as e:  # noqa: BLE001
        print(f"event log failed: {type(e).__name__}: {e}")


def team_phones():
    """The team's own numbers (TEAM_PHONES + TEAM_WHATSAPP): their testing is not traders' use, so the NAIC numbers
    (/team, the CSV, the speed report) leave it out."""
    import accounts
    out = set()
    for env in ("TEAM_PHONES", "TEAM_WHATSAPP"):
        for n in os.getenv(env, "").split(","):
            p = n.strip() and accounts.normalize(n.strip())
            if p:
                out.add(p)
    return out


def rows(since_days=None, team=False):
    """The log, oldest first. team=False (the default) leaves out what the team's own phones did."""
    with _db() as c:
        if since_days:
            since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=since_days)).isoformat(timespec="seconds")
            out = [dict(r) for r in c.execute("SELECT * FROM events WHERE ts >= ? ORDER BY id", (since,))]
        else:
            out = [dict(r) for r in c.execute("SELECT * FROM events ORDER BY id")]
    if team:
        return out
    hashes = {_hash(p) for p in team_phones()}
    hashes |= {"g" + h[:15] for h in hashes}
    return [r for r in out if r["who"] not in hashes] if hashes else out


def summary(now=None):
    """Counts for /team. Traders = people who sent a WhatsApp message or opened the web app."""
    now = now or dt.datetime.now(dt.timezone.utc)
    ev = rows()

    def ago(r):
        return now - dt.datetime.fromisoformat(r["ts"])
    traders = [r for r in ev if r["who"] and r["kind"] in ("message", "web_visit")]
    first = {}
    days = {}
    for r in traders:
        first.setdefault(r["who"], r)
        days.setdefault(r["who"], set()).add(r["ts"][:10])
    real = [w for w in first if not w.startswith("g")]
    active30 = {r["who"] for r in traders if ago(r) <= dt.timedelta(days=30)}
    lang = {}
    for r in ev:
        if r["who"] and r["lang"]:
            lang[r["who"]] = r["lang"]
    kinds = {}
    for r in ev:
        if r["who"]:
            kinds.setdefault(r["kind"], set()).add(r["who"])

    def share(kind):
        out = {}
        for r in ev:
            if r["kind"] == kind:
                key = (r["engine"] or "?").split(":")[0] + ("" if r["ok"] else " (failed)")
                out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))
    llm = share("llm")
    llm_ok = sum(v for k, v in llm.items() if "failed" not in k)
    msgs = [r for r in ev if r["kind"] == "message"]
    return {
        "active_30d": len(active30), "licence_cap": 1000, "licence_warn": len(active30) >= 800,
        "traders_total": len(real), "guests_total": len(first) - len(real),
        "new_today": sum(1 for w in real if ago(first[w]) <= dt.timedelta(days=1)),
        "new_7d": sum(1 for w in real if ago(first[w]) <= dt.timedelta(days=7)),
        "active_7d": len({r["who"] for r in traders if ago(r) <= dt.timedelta(days=7)}),
        "channels": {ch: len({r["who"] for r in traders if (r["channel"] or "web") == ch}) for ch in ("whatsapp", "web")},
        "languages": {l: list(lang.values()).count(l) for l in sorted(set(lang.values()))},
        "funnel": {"first message / visit": len(first), "chose language": len(kinds.get("lang_set", ())),
                   "agreed (consent)": len(kinds.get("consent", ())), "saved a record": len(kinds.get("record_saved", ())),
                   "came back another day": sum(1 for w in days if len(days[w]) > 1)},
        "interactions": len(msgs) + sum(1 for r in ev if r["kind"] == "web_visit"),
        "messages_by_type": {k: sum(1 for r in msgs if r["engine"] == k) for k in sorted({r["engine"] for r in msgs})},
        "records_saved": sum(1 for r in ev if r["kind"] == "record_saved"),
        "understanding": llm, "natlas_share": round(100 * llm.get("natlas", 0) / llm_ok) if llm_ok else None,
        "hearing": share("hear"), "voice_replies": share("voice"),
        "errors": sum(1 for r in ev if not r["ok"]),
        "team_left_out": len(team_phones()),
    }
