"""Backend for the TradeVoice 2.0 design (design/tradevoice-2.0/app.html): accounts and the book, shaped the way
the design's screens use them. The design is the master: every endpoint here backs one of its screens.

Accounts (the design's sign-up): WhatsApp number -> 6-digit code on WhatsApp -> password -> business details.
- The browser sends sha256("tv:pw:"+password) (the design hashes before anything leaves the phone); we store only
  PBKDF2(salt, that), 200,000 rounds. Never the password.
- Codes go by WhatsApp (accounts.start + whatsapp.send_text). They are never shown on screen, unless AUTH_DEMO=1 is
  set on purpose for an internal test with made-up numbers.
- Delete = scheduled: everything is erased 7 days later unless the trader logs in and keeps the account.
Open endpoints live under /api/auth/v2/ (no login needed); the rest under /api/v2/ (logged in, own book only).
"""
import datetime as dt
import hashlib
import json
import os
import secrets
import shutil
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import accounts
import ledger
import training

router = APIRouter()
COOKIE = "tv_auth"
CODE_TICKETS = {}   # login_id -> (phone, purpose, verified_at): a checked code, valid for 15 minutes
FAILS = {}          # phone -> (count, locked_until): 5 wrong passwords -> wait 30 s
_lock = threading.Lock()
DELETE_DAYS = int(os.getenv("DELETE_DAYS", "90"))   # a deleted account is kept this long (the delete screen says so)
TYPES = ["Foodstuff", "Fashion and fabric", "Electronics", "Building materials", "Provisions", "Other"]


# ---------------------------------------------------------------- storage (extra columns on accounts.users)

COLS = {"pw_hash": "TEXT", "biz_type": "TEXT", "market": "TEXT", "address": "TEXT", "rc": "TEXT", "photo": "TEXT",
        "email": "TEXT", "email_ok": "INTEGER DEFAULT 0", "notif": "TEXT", "delete_at": "TEXT"}
SESSION_COLS = {"device": "TEXT", "last_used": "TEXT", "keep": "INTEGER DEFAULT 1"}


def _db():
    c = accounts.db()
    have = {r[1] for r in c.execute("PRAGMA table_info(users)")}
    for k, t in COLS.items():
        if k not in have:
            c.execute(f"ALTER TABLE users ADD COLUMN {k} {t}")
    have = {r[1] for r in c.execute("PRAGMA table_info(sessions)")}
    for k, t in SESSION_COLS.items():
        if k not in have:
            c.execute(f"ALTER TABLE sessions ADD COLUMN {k} {t}")
    return c


def _now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _pw_hash(secret, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), 200_000).hex()
    return f"pbkdf2$200000${salt}${h}"


def _pw_ok(secret, stored):
    try:
        _, rounds, salt, h = (stored or "").split("$")
        return secrets.compare_digest(hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), int(rounds)).hex(), h)
    except ValueError:
        return False


def _user(phone):
    with _db() as c:
        r = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    return dict(r) if r else None


def _has_account(phone):
    u = _user(phone)
    return bool(u and u.get("pw_hash"))


def _phone(request):
    phone = request.scope.get("state", {}).get("phone")
    if not phone:
        raise HTTPException(401, "Please log in.")
    return phone


def _local(phone):
    """2348031234567 -> 8031234567 (what the design shows after +234)."""
    return phone[3:] if phone.startswith("234") else phone


def _norm(p):
    return accounts.normalize(p or "")


def _device(request):
    ua = request.headers.get("user-agent", "")
    return "iPhone" if ("iPhone" in ua or "iPad" in ua) else "Android phone" if "Android" in ua else "This browser"


def _login_response(request, phone, keep=True, extra=None):
    """Session cookie (90 days with 'keep me logged in', else until the browser closes)."""
    token = accounts.new_session(phone)
    with _lock, _db() as c:
        c.execute("UPDATE sessions SET device=?, last_used=?, keep=? WHERE token_hash=?",
                  (_device(request), _now().isoformat(), int(keep), accounts._h(token)))
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    r = JSONResponse({"ok": True, "me": _me(phone, token)} | (extra or {}))
    r.set_cookie(COOKIE, token, max_age=accounts.SESSION_DAYS * 86400 if keep else None, httponly=True,
                 samesite="lax", secure=secure)
    return r


def _me(phone, token=None):
    u = _user(phone) or {"phone": phone}
    notif = {"morning": True, "hour": 8, "pay": True, "remind": True}
    try:
        notif.update(json.loads(u.get("notif") or "{}"))
    except ValueError:
        pass
    with _db() as c:
        sess = [dict(r) for r in c.execute("SELECT token_hash, device, created_at, last_used FROM sessions "
                                           "WHERE phone=? AND expires>? ORDER BY created_at DESC",
                                           (phone, _now().isoformat()))]
    this = accounts._h(token) if token else None
    dev = [{"id": s["token_hash"][:12], "name": s["device"] or "A browser", "this": s["token_hash"] == this,
            "t": s["last_used"] or s["created_at"]} for s in sess]
    return {"phone": _local(phone), "name": u.get("name") or "", "biz": u.get("shop") or "", "type": u.get("biz_type") or "",
            "mk": u.get("market") or "", "addr": u.get("address") or "", "rc": u.get("rc") or "",
            "photo": u.get("photo") or "", "email": u.get("email") or "", "emailOk": bool(u.get("email_ok")),
            "bank": u.get("bank_name") or "", "acctNo": u.get("account_number") or "",
            "acctName": u.get("account_name") or "", "lang": u.get("lang") or "", "notif": notif, "dev": dev,
            "delAt": u.get("delete_at"), "created": u.get("created_at"),
            "train": training.answer(phone), "trainAsked": training.asked(phone)}


# ---------------------------------------------------------------- codes (WhatsApp)

class CodeStart(BaseModel):
    phone: str
    purpose: str = "signup"     # signup | login | reset | phone
    lang: str | None = None


@router.post("/api/auth/v2/code/start")
def code_start(b: CodeStart, request: Request):
    phone = _norm(b.phone)
    if not phone:
        raise HTTPException(400, "Enter a valid Nigerian number, like 803 123 4567.")
    exists = _has_account(phone)
    if b.purpose == "signup" and exists:
        return JSONResponse({"error": "exists"}, 409)
    if b.purpose in ("login", "reset") and not exists:
        return JSONResponse({"error": "missing"}, 404)
    if b.purpose == "phone":
        _phone(request)  # changing your number needs you logged in
        if exists:
            return JSONResponse({"error": "taken"}, 409)
    if _too_many(phone, request):
        return JSONResponse({"error": "too_many"}, 429)
    login = accounts.start(phone)
    sent, bot = False, ""
    if os.getenv("WHATSAPP_TOKEN") and (os.getenv("WHATSAPP_PHONE_ID") or os.getenv("WHATSAPP_PHONE_NUMBER_ID")):
        import whatsapp
        try:   # inside Meta's 24-hour window, or with the approved code template: the code goes by WhatsApp
            sent = whatsapp.send_code(phone, login["code"])
        except Exception as e:  # noqa: BLE001
            print(f"code not sent by WhatsApp: {type(e).__name__}")
        # the other way, always open: the trader sends "LOGIN MANGO-123" to the bot from that phone (they write first,
        # so no template is needed); the page continues by itself (/api/auth/v2/code/poll)
        bot = whatsapp.bot_number() if whatsapp.login_by_message_ok() else ""
    demo = accounts.demo_mode()
    if not sent and not demo and not bot:
        return JSONResponse({"error": "nosend"}, 503)
    return {"login_id": login["id"], "sent": sent, "demo_code": login["code"] if demo else None,
            "word": login["word"] if bot else None, "bot": bot or None}


SENDS = {}   # phone or IP -> times codes were asked for (the last hour)


def _too_many(phone, request):
    """At most 5 codes an hour for one number and 20 from one connection: nobody can flood a trader's WhatsApp."""
    now, ip = time.time(), (request.headers.get("x-forwarded-for") or (request.client.host if request.client else ""))
    ip = ip.split(",")[0].strip()
    for key, cap in ((phone, 5), ("ip:" + ip, 20)):
        recent = [t for t in SENDS.get(key, []) if now - t < 3600]
        if len(recent) >= cap:
            return True
        SENDS[key] = recent
    for key in (phone, "ip:" + ip):
        SENDS[key].append(now)
    return False


class CodePoll(BaseModel):
    login_id: str
    purpose: str = "signup"


@router.post("/api/auth/v2/code/poll")
def code_poll(b: CodePoll):
    """The page waits here while the trader sends LOGIN <word> to the bot: ok once WhatsApp confirmed this number."""
    phone = accounts.poll(b.login_id)
    if not phone:
        return {"ok": False}
    CODE_TICKETS[b.login_id] = (phone, b.purpose, time.time())
    return {"ok": True}


class CodeCheck(BaseModel):
    login_id: str
    code: str
    purpose: str = "signup"


@router.post("/api/auth/v2/code/check")
def code_check(b: CodeCheck):
    phone, why = accounts.check_code(b.login_id, b.code)
    if not phone:
        return JSONResponse({"error": why or "That code isn't right."}, 400)
    CODE_TICKETS[b.login_id] = (phone, b.purpose, time.time())
    return {"ok": True}


def _ticket(login_id, purpose):
    t = CODE_TICKETS.get(login_id or "")
    if not t or t[1] != purpose or time.time() - t[2] > 900:
        raise HTTPException(400, "Your code has expired. Start again.")
    return t[0]


# ---------------------------------------------------------------- sign up / log in / reset

class Signup(BaseModel):
    login_id: str
    pw: str
    name: str
    biz: str
    type: str = ""
    mk: str = ""
    lang: str | None = None


@router.post("/api/auth/v2/signup")
def signup(b: Signup, request: Request):
    phone = _ticket(b.login_id, "signup")
    if _has_account(phone):
        return JSONResponse({"error": "exists"}, 409)
    if len(b.name.strip()) < 2 or len(b.biz.strip()) < 2 or len(b.pw) < 32:
        raise HTTPException(400, "Missing details.")
    import ui_text
    with _lock, _db() as c:
        c.execute("INSERT INTO users (phone, created_at) VALUES (?,?) ON CONFLICT(phone) DO NOTHING",
                  (phone, _now().isoformat()))
        c.execute("UPDATE users SET pw_hash=?, name=?, shop=?, biz_type=?, market=?, lang=?, delete_at=NULL "
                  "WHERE phone=?", (_pw_hash(b.pw), b.name.strip()[:60], b.biz.strip()[:60],
                                    b.type if b.type in TYPES else "", b.mk.strip()[:80],
                                    ui_text.choose(b.lang) if b.lang else "English", phone))
    CODE_TICKETS.pop(b.login_id, None)
    _event("signup", phone)
    return _login_response(request, phone, keep=True)


class Login(BaseModel):
    phone: str
    pw: str
    keep: bool = True


@router.post("/api/auth/v2/login")
def login(b: Login, request: Request):
    phone = _norm(b.phone)
    n, until = FAILS.get(phone, (0, 0))
    if time.time() < until:
        return JSONResponse({"error": "locked", "wait": int(until - time.time()) + 1}, 429)
    u = _user(phone) if phone else None
    if not u or not u.get("pw_hash"):
        return JSONResponse({"error": "missing"}, 404)
    if not _pw_ok(b.pw, u["pw_hash"]):
        n += 1
        FAILS[phone] = (0, time.time() + 30) if n >= 5 else (n, 0)
        return JSONResponse({"error": "wrong", "fails": n, "locked": n >= 5}, 401)
    FAILS.pop(phone, None)
    _event("login", phone)
    return _login_response(request, phone, keep=b.keep, extra={"delAt": u.get("delete_at")})


class CodeLogin(BaseModel):
    login_id: str
    keep: bool = True


@router.post("/api/auth/v2/login_code")
def login_code(b: CodeLogin, request: Request):
    phone = _ticket(b.login_id, "login")
    CODE_TICKETS.pop(b.login_id, None)
    u = _user(phone) or {}
    _event("login", phone)
    return _login_response(request, phone, keep=b.keep, extra={"delAt": u.get("delete_at")})


class Reset(BaseModel):
    login_id: str
    pw: str


@router.post("/api/auth/v2/reset")
def reset(b: Reset, request: Request):
    phone = _ticket(b.login_id, "reset")
    u = _user(phone)
    if u and u.get("pw_hash") and _pw_ok(b.pw, u["pw_hash"]):
        return JSONResponse({"error": "same"}, 400)
    with _lock, _db() as c:
        c.execute("UPDATE users SET pw_hash=? WHERE phone=?", (_pw_hash(b.pw), phone))
        c.execute("DELETE FROM sessions WHERE phone=?", (phone,))   # every other phone is logged out
    CODE_TICKETS.pop(b.login_id, None)
    return {"ok": True}


@router.post("/api/auth/v2/logout")
def logout(request: Request):
    from fastapi import Response
    token = request.cookies.get(COOKIE)
    if token:
        accounts.end_session(token)
    r = Response(status_code=204)
    r.delete_cookie(COOKIE)
    return r


# ---------------------------------------------------------------- the logged-in trader

@router.get("/api/v2/me")
def me(request: Request):
    phone = _phone(request)
    if not _has_account(phone):
        return JSONResponse({"error": "no account"}, 401)   # old guest books: sign up first
    with _lock, _db() as c:
        c.execute("UPDATE sessions SET last_used=? WHERE token_hash=?",
                  (_now().isoformat(), accounts._h(request.cookies.get(COOKIE, ""))))
    return _me(phone, request.cookies.get(COOKIE))


class Profile(BaseModel):
    name: str | None = None
    biz: str | None = None
    type: str | None = None
    mk: str | None = None
    addr: str | None = None
    rc: str | None = None
    photo: str | None = None
    lang: str | None = None
    notif: dict | None = None


@router.post("/api/v2/profile")
def profile(b: Profile, request: Request):
    phone = _phone(request)
    if b.photo and (not b.photo.startswith("data:image/") or len(b.photo) > 300_000):
        raise HTTPException(400, "Choose a smaller photo.")
    f = {"name": b.name, "shop": b.biz, "biz_type": b.type, "market": b.mk, "address": b.addr, "rc": b.rc,
         "photo": b.photo, "notif": json.dumps(b.notif) if b.notif is not None else None}
    if b.lang:
        import ui_text
        f["lang"] = ui_text.choose(b.lang)
    f = {k: (v.strip()[:300_000] if isinstance(v, str) else v) for k, v in f.items() if v is not None}
    if ("name" in f and len(f["name"]) < 2) or ("shop" in f and len(f["shop"]) < 2):
        raise HTTPException(400, "Enter your name and business name.")
    if f:
        with _lock, _db() as c:
            c.execute(f"UPDATE users SET {', '.join(k + '=?' for k in f)} WHERE phone=?", (*f.values(), phone))
    return _me(phone, request.cookies.get(COOKIE))


class PwChange(BaseModel):
    current: str
    new: str


@router.post("/api/v2/password")
def password(b: PwChange, request: Request):
    phone = _phone(request)
    u = _user(phone) or {}
    if not _pw_ok(b.current, u.get("pw_hash")):
        return JSONResponse({"error": "wrong"}, 401)
    if _pw_ok(b.new, u.get("pw_hash")):
        return JSONResponse({"error": "same"}, 400)
    this = accounts._h(request.cookies.get(COOKIE, ""))
    with _lock, _db() as c:
        c.execute("UPDATE users SET pw_hash=? WHERE phone=?", (_pw_hash(b.new), phone))
        c.execute("DELETE FROM sessions WHERE phone=? AND token_hash!=?", (phone, this))  # other phones logged out
    return _me(phone, request.cookies.get(COOKIE))


class DevOut(BaseModel):
    id: str   # first 12 characters of the session hash, or "all" (= every other device)


@router.post("/api/v2/devices/logout")
def devices_logout(b: DevOut, request: Request):
    phone = _phone(request)
    this = accounts._h(request.cookies.get(COOKIE, ""))
    with _lock, _db() as c:
        if b.id == "all":
            c.execute("DELETE FROM sessions WHERE phone=? AND token_hash!=?", (phone, this))
        else:
            c.execute("DELETE FROM sessions WHERE phone=? AND substr(token_hash,1,12)=? AND token_hash!=?",
                      (phone, b.id, this))
    return _me(phone, request.cookies.get(COOKIE))


class Email(BaseModel):
    email: str = ""


@router.post("/api/v2/email")
def email(b: Email, request: Request):
    """Stored, not verified: TradeVoice has no email sending yet (the design's 'verify' step waits for it)."""
    phone = _phone(request)
    e = b.email.strip().lower()
    if e and ("@" not in e or "." not in e.split("@")[-1]):
        raise HTTPException(400, "That email doesn't look right.")
    with _lock, _db() as c:
        if e and c.execute("SELECT 1 FROM users WHERE lower(email)=? AND phone!=?", (e, phone)).fetchone():
            return JSONResponse({"error": "taken"}, 409)
        c.execute("UPDATE users SET email=?, email_ok=0 WHERE phone=?", (e or None, phone))
    return _me(phone, request.cookies.get(COOKIE))


class PhoneChange(BaseModel):
    login_id: str


@router.post("/api/v2/phone")
def phone_change(b: PhoneChange, request: Request):
    """Move the account and its book to a new (verified) number."""
    old = _phone(request)
    new = _ticket(b.login_id, "phone")
    if _has_account(new):
        return JSONResponse({"error": "taken"}, 409)
    with _lock, _db() as c:
        c.execute("DELETE FROM users WHERE phone=? AND pw_hash IS NULL", (new,))
        for table in ("users", "sessions"):
            c.execute(f"UPDATE {table} SET phone=? WHERE phone=?", (new, old))
        for table in ("shares", "paylinks"):
            try:
                c.execute(f"UPDATE {table} SET phone=? WHERE phone=?", (new, old))
            except Exception:  # noqa: BLE001 - table not created yet
                pass
    src, dst = ledger.book_file(old), ledger.book_file(new)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.move(src, dst)
    CODE_TICKETS.pop(b.login_id, None)
    return _me(new, request.cookies.get(COOKIE))


class Delete(BaseModel):
    biz: str
    pw: str


@router.post("/api/v2/delete")
def delete(b: Delete, request: Request):
    phone = _phone(request)
    u = _user(phone) or {}
    if b.biz.strip().lower() != (u.get("shop") or "").strip().lower():
        return JSONResponse({"error": "biz"}, 400)
    if not _pw_ok(b.pw, u.get("pw_hash")):
        return JSONResponse({"error": "wrong"}, 401)
    return {"delAt": schedule_delete(phone)}


def schedule_delete(phone):
    """Close the account now and erase it after DELETE_DAYS (logging in before then and tapping Keep undoes it)."""
    at = (_now() + dt.timedelta(days=DELETE_DAYS)).isoformat()
    with _lock, _db() as c:
        c.execute("UPDATE users SET delete_at=? WHERE phone=?", (at, phone))
    return at


def closing(phone):
    """The date this account will be erased, if its owner deleted it; else None."""
    u = _user(phone) or {}
    return dt.datetime.fromisoformat(u["delete_at"]).date() if u.get("delete_at") else None


class Train(BaseModel):
    yes: bool | None = None   # None: the question was closed without an answer (not asked again; Me can change it)


@router.post("/api/v2/training")
def train(b: Train, request: Request):
    """Help improve TradeVoice: keep my voice notes, photos and chats for the team (yes), or not (no: what was kept is
    deleted). Saying no never limits the app."""
    phone = _phone(request)
    if b.yes is None:
        training.mark_asked(phone)
    else:
        training.set_answer(phone, b.yes)
    return {"train": training.answer(phone)}


@router.post("/api/v2/restore")
def restore(request: Request):
    phone = _phone(request)
    with _lock, _db() as c:
        c.execute("UPDATE users SET delete_at=NULL WHERE phone=?", (phone,))
    return _me(phone, request.cookies.get(COOKIE))


def purge_deleted():
    """Erase accounts whose DELETE_DAYS are up (everything for the number). Called by the hourly scheduler."""
    with _db() as c:
        due = [r["phone"] for r in c.execute("SELECT phone FROM users WHERE delete_at IS NOT NULL AND delete_at<?",
                                             (_now().isoformat(),))]
    for phone in due:
        accounts.delete_account(phone)
    return due


# ---------------------------------------------------------------- the book, shaped for the design

KIND = {"sale": ("Cash sale", -1), "credit_sale": ("Sold on credit", 1), "payment_received": ("Paid me", -1),
        "expense": ("Spent", 0), "credit_purchase": ("I took on credit", 0), "payment_made": ("I paid back", 0)}


def _day_label(iso, today):
    d = dt.date.fromisoformat(str(iso)[:10])
    if d == today:
        return "Today"
    if (today - d).days < 7 and d < today:
        return d.strftime("%a")
    return f"{d.day} {d.strftime('%b')}"


def _due_label(iso, today):
    d = dt.date.fromisoformat(str(iso)[:10])
    if d < today:
        return "Last week" if (today - d).days >= 7 else d.strftime("%A")
    if d == today:
        return "Today"
    if (d - today).days < 7:
        return d.strftime("%A")
    return f"{d.day} {d.strftime('%b')}"


PERIODS = {"today": 0, "7": 6, "30": 29, "365": 364}   # Today / 7D / 30D / 1Y: days back from today (inclusive)


def _span(period, start, end, today):
    """The dates Home adds up: a fixed span back from today, or the trader's own from-to (Custom). Bad or future
    dates fall back to today; a custom span is at most 3 years."""
    if period == "custom":
        try:
            a, b = dt.date.fromisoformat(start or ""), dt.date.fromisoformat(end or "")
        except ValueError:
            return "today", today, today
        a, b = min(a, b), min(max(a, b), today)
        if a > today:
            return "today", today, today
        return "custom", max(a, b - dt.timedelta(days=3 * 366)), b
    period = period if period in PERIODS else "today"
    return period, today - dt.timedelta(days=PERIODS[period]), today


@router.get("/api/v2/book")
def book(request: Request, period: str = "today", start: str = "", end: str = ""):
    """The customers and Home's money in / money out for the period the trader picked (Today, 7D, 30D, 1Y, or
    Custom with start and end dates)."""
    _phone(request)
    today = dt.date.today()
    out = []
    with ledger.conn() as c:   # each customer's latest record: the Customers filters' "last activity" and sorts
        last = {e["customer_id"]: dict(e) for e in c.execute(
            "SELECT customer_id, type, amount, created_at FROM entries WHERE id IN "
            "(SELECT max(id) FROM entries WHERE customer_id IS NOT NULL GROUP BY customer_id)")}
    for r in ledger.conversations(today):
        if r.get("i_owe") and not r.get("owes_me"):
            continue   # the design's Customers are people who owe ME (suppliers show in the book, not here)
        due = ""
        with ledger.conn() as c:
            d = c.execute("SELECT min(due_date) FROM entries WHERE customer_id=? AND type='credit_sale' AND "
                          "due_date IS NOT NULL AND due_date>=?", (r["id"], (today - dt.timedelta(days=60)).isoformat())
                          ).fetchone()[0]
        if d and r.get("owes_me"):
            due = _due_label(d, today)
        e = last.get(r["id"])
        out.append({"id": r["id"], "n": r["name"], "b": round(r.get("owes_me") or 0), "late": r.get("days_late") or 0,
                    "due": due, "h": [], "last": _h_row(e, today) if e else None})
    period, a, b = _span(period, start, end, today)
    s = ledger.money_between(a, b)
    return {"customers": out, "in": round(s["money_in"]), "out": round(s["money_out"]), "count": s["count"],
            "period": period, "from": a.isoformat(), "to": b.isoformat()}


@router.get("/api/v2/customer/{cid}")
def customer(cid: int, request: Request):
    _phone(request)
    today = dt.date.today()
    h = []
    for e in reversed(ledger.thread(cid)):
        if e["event"] == "record":
            h.append(_h_row(e, today))
    return {"h": h}


def _h_row(e, today):
    """One line of a customer's history, as the design reads it: [label, amount (- = money in), day, days ago]."""
    label, sign = KIND.get(e["type"], (e["type"], 0))
    return [label, (-1 if sign < 0 else 1) * round(e["amount"]), _day_label(e["created_at"], today),
            max((today - dt.date.fromisoformat(str(e["created_at"])[:10])).days, 0)]


def _event(kind, phone):
    try:
        import events
        events.log(kind, phone, "web")
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- small helpers the design's screens need

class Exists(BaseModel):
    phone: str


@router.post("/api/auth/v2/exists")
def exists(b: Exists):
    """'This number already has an account' (sign-up) / 'We couldn't find an account' (log in)."""
    phone = _norm(b.phone)
    return {"exists": bool(phone) and _has_account(phone)}


@router.post("/api/v2/undo_last")
def undo_last(request: Request):
    """The design's 'Undo' after Save: removes the record saved in the last 2 minutes (only that one)."""
    _phone(request)
    since = (dt.datetime.now() - dt.timedelta(minutes=2)).isoformat(timespec="seconds")
    with ledger.conn() as c:
        r = c.execute("SELECT id FROM entries WHERE created_at>=? ORDER BY id DESC LIMIT 1", (since,)).fetchone()
    return {"undone": bool(r and ledger.delete_entry(r[0]))}


_BANK_CODES = {}


class Resolve(BaseModel):
    bank: str
    account: str


@router.post("/api/v2/bank_resolve")
def bank_resolve(b: Resolve, request: Request):
    """Payout account: the account holder's name from Paystack ('Is this you?'). None when Paystack isn't set up."""
    _phone(request)
    key = os.getenv("PAYSTACK_SECRET_KEY")
    if not key or len(b.account) != 10 or not b.account.isdigit():
        return {"name": None}
    try:
        import requests
        h = {"Authorization": f"Bearer {key}"}
        if not _BANK_CODES:
            for x in requests.get("https://api.paystack.co/bank?country=nigeria&perPage=200", headers=h,
                                  timeout=15).json().get("data", []):
                _BANK_CODES[x["name"].lower()] = x["code"]
        code = next((c for n, c in _BANK_CODES.items() if b.bank.lower() in n or n in b.bank.lower()), None)
        if not code:
            return {"name": None}
        r = requests.get("https://api.paystack.co/bank/resolve", params={"account_number": b.account, "bank_code": code},
                         headers=h, timeout=15).json()
        return {"name": (r.get("data") or {}).get("account_name")}
    except Exception:  # noqa: BLE001
        return {"name": None}


@router.get("/api/v2/report")
def report(request: Request):
    """Lender report numbers: money in over the last 30 days, customers, owed to the shop."""
    _phone(request)
    today = dt.date.today()
    since = (today - dt.timedelta(days=30)).isoformat()
    with ledger.conn() as c:
        money_in = c.execute("SELECT coalesce(sum(amount),0) FROM entries WHERE type IN ('sale','payment_received') "
                             "AND substr(created_at,1,10)>=?", (since,)).fetchone()[0]
    rows = ledger.conversations(today)
    return {"in30": round(money_in), "customers": len(rows), "owed": round(sum(r.get("owes_me") or 0 for r in rows))}
