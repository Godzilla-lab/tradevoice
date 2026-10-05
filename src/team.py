"""/team: the team's live dashboard (web/team.html) and the anonymised CSV export behind the NAIC "real-world
validation" PDF. Team only: /team?key=<ADMIN_TOKEN> (or header X-Admin-Key) on every page, API call and file.

What it shows, in three tiers:
  - everyone: every action as it happens (who as a code, what, channel, language, how long, failed or not). No
    names, amounts, words or audio: the usage log never holds them (src/events.py).
  - traders who said yes to "help make TradeVoice better" (src/training.py): also what they said and sent (live-talk
    audio, voice notes, photos, chats and TradeVoice's replies), and their business name.
  - traders who said no or haven't answered: actions only.
The team's own phones (TEAM_PHONES) are marked "Team" in the feed and left out of the numbers.
"""
import csv
import datetime as dt
import hmac
import io
import mimetypes
import os
import sqlite3
import statistics

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

import events
import training

router = APIRouter()
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAT = dt.timezone(dt.timedelta(hours=1), "WAT")   # Nigeria: days and hours on the dashboard are Lagos time
PRIVATE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex", "Referrer-Policy": "no-referrer"}


def _allowed(request: Request):
    want = os.getenv("ADMIN_TOKEN", "")
    got = request.query_params.get("key") or request.headers.get("x-admin-key", "")
    if not want or not hmac.compare_digest(want, got):
        raise HTTPException(403, "Team only")


# ---------------------------------------------------------------- what each logged event means, in words

CATS = ("people", "conversations", "voice", "records", "ai")
_MSG = {"text": "text", "audio": "voice note", "image": "photo", "interactive": "button", "button": "button"}
_KEPT = {"voice": "voice note", "photo": "photo", "live": "live-talk audio"}


def describe(r):
    """(category, words) for one event row. Category "errors" for anything that failed."""
    k, e = r["kind"], r["engine"] or ""
    if k == "message":
        cat, words = "conversations", f"WhatsApp message ({_MSG.get(e, e or 'other')})"
    elif k == "understand":
        cat, words = "conversations", {"live talk": "Live talk: answered", "voice": "Voice question: answered"}.get(
            e, "Ask chat: answered")
    elif k == "unanswered":
        cat, words = "conversations", "A question nothing could answer"
    elif k == "web_visit":
        cat, words = "people", "Opened the app"
    elif k == "signup":
        cat, words = "people", "New trader signed up"
    elif k == "login":
        cat, words = "people", "Logged in"
    elif k == "lang_set":
        cat, words = "people", f"Chose {r['lang'] or 'a language'}"
    elif k == "consent":
        cat, words = "people", "Agreed to the terms"
    elif k == "training_answer":
        cat, words = "people", "Said yes to helping improve TradeVoice" if e == "yes" else "Said no to helping improve TradeVoice"
    elif k == "store_wait":
        cat, words = "people", "Asked to hear when the app is in the store"
    elif k == "training_kept":
        cat, words = "records", ("Disk nearly full: stopped keeping audio and photos" if e == "disk low"
                                 else f"Kept a {_KEPT.get(e, e)} for improving TradeVoice")
    elif k == "record_saved":
        cat, words = "records", "Saved a record"
    elif k == "customer_added":
        cat, words = "records", "Added a customer" + (" by hand" if e == "by hand" else "")
    elif k == "hear":
        cat, words = "voice", "Heard speech"
    elif k == "hear_merge":
        cat, words = "voice", "Compared two hearings"
    elif k == "voice":
        cat, words = "voice", "Replayed a saved voice reply" if e == "cache" else "Spoke a reply"
    elif k == "llm":
        cat, words = "ai", "AI answered"
    elif k == "ask_brain":
        cat, words = "ai", "Ask chat model step"
    elif k == "tool":
        cat, words = "ai", f"Used a tool: {e}" if e else "Used a tool"
    else:
        cat, words = "ai", k.replace("_", " ").capitalize()
    if not r["ok"]:
        cat, words = "errors", words.replace(": answered", "") + ": failed"
    return cat, words


def _labels():
    """Code -> how the dashboard names a trader: the business name for traders who said yes, "Team" for the team's
    own phones, else nothing (the page shows the code)."""
    import accounts
    out = {}
    try:
        with training._db() as c:
            yes = [r["phone"] for r in c.execute("SELECT phone FROM training WHERE answer=1")]
        with sqlite3.connect(accounts.ACCOUNTS_DB, timeout=5) as c:
            c.row_factory = sqlite3.Row
            names = {r["phone"]: r["shop"] or r["name"] for r in c.execute("SELECT phone, name, shop FROM users")}
        for p in yes:
            out[events._hash(p)] = names.get(p) or "Helping improve"
    except Exception:  # noqa: BLE001 - no accounts yet
        pass
    for p in events.team_phones():
        out[events._hash(p)] = "Team"
    return out


def _row(r, labels):
    cat, words = describe(r)
    return {"id": r["id"], "ts": r["ts"], "who": r["who"] or "", "name": labels.get(r["who"] or "", ""),
            "channel": r["channel"] or "", "kind": r["kind"], "cat": cat, "what": words, "lang": r["lang"] or "",
            "engine": r["engine"] or "", "ok": bool(r["ok"]), "ms": r["ms"]}


# ---------------------------------------------------------------- the numbers for a period (today / 7 / 30 days)

def _window(period, now):
    local = now.astimezone(WAT)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        start = midnight
        return start, start - dt.timedelta(days=1), [start + dt.timedelta(hours=h) for h in range(24)], "hour"
    n = 30 if period == "30d" else 7
    start = midnight - dt.timedelta(days=n - 1)
    return start, start - dt.timedelta(days=n), [start + dt.timedelta(days=d) for d in range(n)], "day"


def _t(r):
    return dt.datetime.fromisoformat(r["ts"])


def _metrics(rows, first_seen, start, end):
    rs = [r for r in rows if start <= _t(r) < end]
    people = {r["who"] for r in rs if r["who"] and not r["who"].startswith("g")}
    talk = [r for r in rs if r["kind"] in ("understand", "message")]
    ms = [r["ms"] for r in rs if r["kind"] == "understand" and r["ms"] is not None]
    llm = [r for r in rs if r["kind"] == "llm" and r["ok"]]
    return {
        "new": sum(1 for w, t in first_seen.items() if not w.startswith("g") and start <= t < end),
        "active": len(people),
        "conversations": len(talk),
        "voice": sum(1 for r in rs if r["kind"] == "hear" and r["ok"]),
        "live": sum(1 for r in rs if r["kind"] == "understand" and r["engine"] == "live talk"),
        "records": sum(1 for r in rs if r["kind"] == "record_saved"),
        "customers": sum(1 for r in rs if r["kind"] == "customer_added"),
        "errors": sum(1 for r in rs if not r["ok"]),
        "reply_ms": int(statistics.median(ms)) if ms else None,
        "natlas_share": round(100 * sum(1 for r in llm if r["engine"] == "natlas") / len(llm)) if llm else None,
    }


def _count(rows, kind, key, ok_only=False):
    out = {}
    for r in rows:
        if r["kind"] == kind and (r["ok"] or not ok_only):
            k = key(r)
            out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def overview(period="today", now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    start, prev, buckets, unit = _window(period, now)
    days = (now - prev).days + 2
    rows = events.rows(since_days=days)          # the team's own phones left out of the numbers
    with events._db() as c:
        first_seen = {r[0]: dt.datetime.fromisoformat(r[1]) for r in c.execute(
            "SELECT who, MIN(ts) FROM events WHERE who != '' GROUP BY who")}
    team = {events._hash(p) for p in events.team_phones()}
    first_seen = {w: t for w, t in first_seen.items() if w not in team}
    cur = [r for r in rows if _t(r) >= start]
    series = []
    for i, b in enumerate(buckets):
        e = buckets[i + 1] if i + 1 < len(buckets) else (b + (dt.timedelta(hours=1) if unit == "hour" else dt.timedelta(days=1)))
        n = sum(1 for r in cur if b <= _t(r) < e and r["kind"] in ("understand", "message"))
        series.append({"t": b.isoformat(), "label": b.strftime("%H:00") if unit == "hour" else b.strftime("%d %b"), "n": n})
    talk = [r for r in cur if r["kind"] in ("understand", "message")]
    s = events.summary(now)
    return {
        "period": period, "unit": unit, "now": now.astimezone(WAT).isoformat(timespec="seconds"),
        "kpi": _metrics(rows, first_seen, start, now + dt.timedelta(seconds=1)),
        "prev": _metrics(rows, first_seen, prev, start),
        "series": series,
        "languages": dict(sorted({l: sum(1 for r in talk if (r["lang"] or "Not set") == l)
                                  for l in {r["lang"] or "Not set" for r in talk}}.items(), key=lambda kv: -kv[1])),
        "channels": _count(cur, "understand", lambda r: "Web app") | (
            {"WhatsApp": n} if (n := sum(1 for r in cur if r["kind"] == "message")) else {}),
        "where": {"Live talk": sum(1 for r in cur if r["kind"] == "understand" and r["engine"] == "live talk"),
                  "Ask chat": sum(1 for r in cur if r["kind"] == "understand" and r["engine"] not in ("live talk", "voice")),
                  "Voice question": sum(1 for r in cur if r["kind"] == "understand" and r["engine"] == "voice"),
                  "WhatsApp": sum(1 for r in cur if r["kind"] == "message")},
        "models": _count(cur, "llm", lambda r: (r["engine"] or "?").split(":")[0] + ("" if r["ok"] else " (failed)")),
        "hearing": _count(cur, "hear", lambda r: (r["engine"] or "?").split(":")[0] + ("" if r["ok"] else " (failed)")),
        "voice_replies": _count(cur, "voice", lambda r: (r["engine"] or "?").split(":")[0] + ("" if r["ok"] else " (failed)")),
        "tools": _count(cur, "tool", lambda r: r["engine"] or "?"),
        "unanswered": _count(cur, "unanswered", lambda r: r["lang"] or "Not set"),
        "speed": [{"step": n, "count": c, "typical": m, "p90": p, "max": x}
                  for n, c, m, p, x in events._speed_table(cur)],
        "problems": [_row(r, {}) for r in sorted((r for r in cur if not r["ok"]), key=lambda r: r["id"], reverse=True)[:12]],
        "funnel": s["funnel"],
        "licence": {"active_30d": s["active_30d"], "cap": s["licence_cap"], "warn": s["licence_warn"]},
        "totals": {"traders": s["traders_total"], "guests": s["guests_total"], "team_left_out": s["team_left_out"]},
        "improve": training.stats(),
    }


# ---------------------------------------------------------------- pages and data (team key on every call)

@router.get("/team", response_class=HTMLResponse)
def team(request: Request):
    _allowed(request)
    page = open(os.path.join(HERE, "web", "team.html"), encoding="utf-8").read()
    return HTMLResponse(page, headers=PRIVATE)


@router.get("/team/api/overview")
def api_overview(request: Request, period: str = "today"):
    _allowed(request)
    return Response(_json(overview(period if period in ("today", "7d", "30d") else "today")),
                    media_type="application/json", headers=PRIVATE)


@router.get("/team/api/feed")
def api_feed(request: Request, after: int = 0, who: str = "", limit: int = 150):
    """Every action, newest first (only those after `after`, for the live view). All phones, the team's marked."""
    _allowed(request)
    limit = max(1, min(limit, 500))
    q, args = "SELECT * FROM events WHERE id > ?", [after]
    if who:
        q, args = q + " AND who = ?", args + [who]
    with events._db() as c:
        rows = [dict(r) for r in c.execute(q + " ORDER BY id DESC LIMIT ?", (*args, limit))]
        stats = None
        if who:   # one trader: their all-time numbers (the list itself stops at `limit`)
            stats = dict(c.execute("SELECT MIN(ts) AS first, MAX(ts) AS last, SUM(ok = 0) AS problems, "
                                   "SUM(kind IN ('understand', 'message')) AS conversations, "
                                   "SUM(kind = 'record_saved') AS records, SUM(kind = 'customer_added') AS customers "
                                   "FROM events WHERE who = ?", (who,)).fetchone())
    labels = _labels()
    return Response(_json({"rows": [_row(r, labels) for r in rows], "stats": stats}), media_type="application/json",
                    headers=PRIVATE)


@router.get("/team/api/conversations")
def api_conversations(request: Request, after: str = "", who: str = "", limit: int = 60):
    """What traders who said yes said and sent, newest first, with links to the audio and photos."""
    _allowed(request)
    labels = _labels()
    out = []
    for x in training.items(after=after, limit=2000 if who else max(1, min(limit, 300))):
        if who and x["who"] != who:
            continue
        out.append({"who": x["who"], "name": labels.get(x["who"], ""), "kind": x.get("kind"), "lang": x.get("lang"),
                    "at": x.get("at"), "said": (x.get("heard") or {}).get("text") if isinstance(x.get("heard"), dict) else x.get("heard"),
                    "read": (x.get("heard") or {}).get("rows") if isinstance(x.get("heard"), dict) else None,
                    "not_record": (x.get("heard") or {}).get("not_record") if isinstance(x.get("heard"), dict) else None,
                    "reply": x.get("reply"), "extra": x.get("extra") or {},
                    "file": f"/team/media/{x['who']}/{x['file']}" if x.get("file") else None,
                    "media": _media_kind(x.get("file"))})
        if len(out) >= limit:
            break
    return Response(_json({"items": out}), media_type="application/json", headers=PRIVATE)


@router.get("/team/media/{code}/{name}")
def media(code: str, name: str, request: Request):
    _allowed(request)
    p = training.media_path(code, name)
    if not p:
        raise HTTPException(404)
    return FileResponse(p, media_type=mimetypes.guess_type(p)[0] or "application/octet-stream", headers=PRIVATE)


@router.get("/team/export.csv")
def export(request: Request):
    _allowed(request)
    out = io.StringIO()
    w = csv.writer(out)
    cols = ["ts", "who", "channel", "kind", "lang", "engine", "ok", "ms"]
    w.writerow(cols)
    for r in events.rows():
        w.writerow([r[c] for c in cols])
    return Response(out.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=tradevoice-interactions.csv", "Cache-Control": "no-store"})


def _media_kind(name):
    ext = os.path.splitext(name or "")[1].lower()
    return "audio" if ext in (".wav", ".flac", ".ogg", ".webm", ".mp3", ".m4a", ".opus", ".aac") else \
        "image" if ext in (".jpg", ".jpeg", ".png", ".webp", ".heic") else ("file" if name else None)


def _json(x):
    import json
    return json.dumps(x, ensure_ascii=False, default=str)
