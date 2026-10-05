"""Log in with your phone number. Your WhatsApp number is your account, and each number has its own book
(books/<number>.db). The web app and the WhatsApp bot use the same book for the same number.

How a trader proves the number is theirs (no SMS provider needed):
  1. we send a 6-digit code to their WhatsApp (works when the bot can message them), or
  2. "Verify with WhatsApp": they send "LOGIN <word>" to the bot from that phone (free, always works), or
  3. demo mode (AUTH_DEMO=1, or WhatsApp not set up): the code is shown on screen, clearly marked.
Codes and session tokens are stored only as hashes. A code lasts 10 minutes and allows 5 tries.
"""
import datetime as dt
import hashlib
import os
import re
import secrets
import sqlite3
import threading

ACCOUNTS_DB = os.getenv("ACCOUNTS_DB", "accounts.db")
CODE_MINUTES, MAX_TRIES, SESSION_DAYS = 10, 5, 90
_lock = threading.Lock()
WORDS = ["MANGO", "PEPPER", "GARRI", "YAM", "RICE", "BEANS", "OKRA", "PLANTAIN", "COCOA", "KOLA", "TOMATO", "ONION",
         "AGEGE", "SUYA", "PUFF", "MOIMOI", "AKARA", "EWA", "ZOBO", "KUNU"]


def db():
    c = sqlite3.connect(ACCOUNTS_DB)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (phone TEXT PRIMARY KEY, name TEXT, shop TEXT, lang TEXT, created_at TEXT,
                                      last_login TEXT);
    CREATE TABLE IF NOT EXISTS logins (id TEXT PRIMARY KEY, phone TEXT NOT NULL, code_hash TEXT NOT NULL,
                                       word TEXT NOT NULL, expires TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0,
                                       verified_at TEXT, used INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, phone TEXT NOT NULL, created_at TEXT,
                                         expires TEXT NOT NULL);
    """)
    return c


def _h(x):
    return hashlib.sha256(str(x).encode()).hexdigest()


def _now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def normalize(phone):
    """'0803 123 4567' / '+234 803…' / '234803…' -> '2348031234567'. Other countries: digits with country code.
    None if it can't be a phone number."""
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("00"):
        d = d[2:]
    if len(d) == 11 and d.startswith("0"):  # Nigerian local format
        d = "234" + d[1:]
    elif len(d) == 10 and d[0] in "789":    # 803… without the 0
        d = "234" + d
    return d if 10 <= len(d) <= 15 else None


def masked(phone):
    return f"+{phone[:3]} ••• ••• {phone[-4:]}" if phone else ""


def demo_mode():
    """Code shown on screen: ONLY when AUTH_DEMO=1 is set on purpose (local demos). Never on a public server:
    anyone could then open any phone number's book. (Before 2 Oct it also switched on when WhatsApp was missing.)
    TV_PUBLIC=1 (set by the live server's service file, deploy/server/setup.sh) keeps it off whatever .env says."""
    return os.getenv("AUTH_DEMO") == "1" and os.getenv("TV_PUBLIC") != "1"


# ---------------------------------------------------------------- one login attempt

def start(phone):
    """New login for `phone` -> {id, code (keep secret unless demo), word}."""
    code, word = f"{secrets.randbelow(10**6):06d}", f"{secrets.choice(WORDS)}-{secrets.randbelow(900) + 100}"
    lid = secrets.token_urlsafe(16)
    with _lock, db() as c:
        # a fresh login cancels older unused ones for this number
        c.execute("UPDATE logins SET used=1 WHERE phone=? AND used=0", (phone,))
        c.execute("INSERT INTO logins (id, phone, code_hash, word, expires) VALUES (?,?,?,?,?)",
                  (lid, phone, _h(code), word, (_now() + dt.timedelta(minutes=CODE_MINUTES)).isoformat()))
    return {"id": lid, "code": code, "word": word}


def _get(c, lid):
    r = c.execute("SELECT * FROM logins WHERE id=?", (lid,)).fetchone()
    if not r or r["used"]:
        return None, "This code is no longer valid. Ask for a new one."
    if dt.datetime.fromisoformat(r["expires"]) < _now():
        return None, "This code has expired. Ask for a new one."
    return r, None


def check_code(lid, code):
    """Typed code -> (phone, None) or (None, why)."""
    with _lock, db() as c:
        r, why = _get(c, lid)
        if not r:
            return None, why
        if r["tries"] >= MAX_TRIES:
            c.execute("UPDATE logins SET used=1 WHERE id=?", (lid,))
            return None, "Too many wrong codes. Ask for a new one."
        if not secrets.compare_digest(r["code_hash"], _h(re.sub(r"\D", "", code or ""))):
            c.execute("UPDATE logins SET tries=tries+1 WHERE id=?", (lid,))
            left = MAX_TRIES - r["tries"] - 1
            return None, f"That code is not right. {left} tr{'y' if left == 1 else 'ies'} left."
        c.execute("UPDATE logins SET used=1, verified_at=? WHERE id=?", (_now().isoformat(), lid))
        return r["phone"], None


def confirm_from_whatsapp(sender, text):
    """The bot got 'LOGIN MANGO-123' from `sender`. True if that opened a login for this same number."""
    m = re.search(r"\blogin\s+([a-z]+-\d{3})\b", text or "", re.I)
    if not m:
        return None
    with _lock, db() as c:
        r = c.execute("SELECT * FROM logins WHERE word=? AND used=0 AND verified_at IS NULL ORDER BY expires DESC",
                      (m.group(1).upper(),)).fetchone()
        if not r or dt.datetime.fromisoformat(r["expires"]) < _now():
            return False
        if normalize(sender) != r["phone"]:  # someone else's phone sent it: not proof
            return False
        c.execute("UPDATE logins SET verified_at=? WHERE id=?", (_now().isoformat(), r["id"]))
        return True


def poll(lid):
    """Web page asks: has WhatsApp confirmed this login? -> phone once (then the login is used up)."""
    with _lock, db() as c:
        r, _ = _get(c, lid)
        if not r or not r["verified_at"]:
            return None
        c.execute("UPDATE logins SET used=1 WHERE id=?", (lid,))
        return r["phone"]


# ---------------------------------------------------------------- sessions (the browser stays logged in)

GUEST = "999"   # not a country code: books opened without a phone number are 999 + 12 random digits


def new_guest():
    return GUEST + "".join(secrets.choice("0123456789") for _ in range(12))


def is_guest(phone):
    return bool(phone) and phone.startswith(GUEST) and len(phone) == 15


def new_session(phone):
    token = secrets.token_urlsafe(32)
    now = _now()
    with _lock, db() as c:
        c.execute("INSERT INTO sessions (token_hash, phone, created_at, expires) VALUES (?,?,?,?)",
                  (_h(token), phone, now.isoformat(), (now + dt.timedelta(days=SESSION_DAYS)).isoformat()))
        c.execute("INSERT INTO users (phone, created_at, last_login) VALUES (?,?,?) "
                  "ON CONFLICT(phone) DO UPDATE SET last_login=excluded.last_login",
                  (phone, now.isoformat(), now.isoformat()))
    return token


def phone_for(token):
    if not token:
        return None
    with db() as c:
        r = c.execute("SELECT phone, expires FROM sessions WHERE token_hash=?", (_h(token),)).fetchone()
    if not r or dt.datetime.fromisoformat(r["expires"]) < _now():
        return None
    return r["phone"]


def end_session(token):
    with _lock, db() as c:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (_h(token or ""),))


def profile(phone):
    with db() as c:
        r = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    return dict(r) if r else {"phone": phone}


TITLES = {"mama", "iya", "baba", "papa", "alhaji", "alhaja", "hajia", "hajiya", "madam", "oga", "chief", "mr", "mrs",
          "aunty", "auntie", "uncle", "dr", "mallam", "malam", "sister", "brother", "nne", "nna", "ogbeni", "iyawo"}


def trader(phone=None):
    """Who TradeVoice is talking to right now (the owner of the open book): {"name": what to call them, "biz",
    "type", "market"}, only what they told us. "Ada Okafor" -> "Ada"; "Mama Ngozi" stays "Mama Ngozi"."""
    import events
    phone = phone or events._current_phone()
    if not phone:
        return {}
    try:
        p = profile(phone)
    except Exception:  # noqa: BLE001
        return {}
    words = (p.get("name") or "").split()
    name = " ".join(words[:2]) if len(words) > 1 and words[0].lower().rstrip(".") in TITLES else (words[0] if words else "")
    out = {"name": name.title() if name.islower() else name, "biz": p.get("shop"), "type": p.get("biz_type"),
           "market": p.get("market")}
    return {k: v.strip() for k, v in out.items() if isinstance(v, str) and v.strip()}


def update_profile(phone, **fields):
    fields = {k: v for k, v in fields.items() if k in ("name", "shop", "lang") and v is not None}
    if not fields:
        return
    with _lock, db() as c:
        c.execute("INSERT INTO users (phone, created_at) VALUES (?,?) ON CONFLICT(phone) DO NOTHING",
                  (phone, _now().isoformat()))
        c.execute(f"UPDATE users SET {', '.join(k + '=?' for k in fields)} WHERE phone=?", (*fields.values(), phone))


def delete_account(phone):
    """Everything for this number: sessions, profile, share and pay links, the store list, and the book file (which
    also holds its WhatsApp settings). The usage log keeps only an unreadable code, never the number."""
    import ledger

    with _lock, db() as c:
        have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("sessions", "logins", "users", "shares", "paylinks", "auto_runs", "store_wait"):
            if t in have:
                c.execute(f"DELETE FROM {t} WHERE phone=?", (phone,))
    try:
        import training
        training.erase(phone)   # voice notes and photos kept for training (only if they had said yes)
    except Exception as e:  # noqa: BLE001
        print(f"training copies not erased: {type(e).__name__}: {e}")
    path = ledger.book_file(phone)
    for f in (path, path + "-wal", path + "-shm", path + "-journal"):
        if os.path.exists(f):
            os.remove(f)
