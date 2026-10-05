"""Voice notes, photos, live-talk audio and conversations kept to improve TradeVoice (the team reviews them on /team
and trains the models on them), ONLY for traders who said yes (asked once, separately
from the sign-up consent; saying no never limits the app). Everyone else's are deleted as soon as they are read.

Where: TRAIN_DIR (default: a "training" folder next to the books, /var/lib/tradevoice/training on the server), one
folder per trader named by the usage log's code for their number (events._hash), never the number itself:
    <code>/<time>-<id>.<ext>      the voice note (as it came), live-talk audio (WAV) or photo
    <code>/manifest.jsonl         one line each: file, kind (voice/live/photo, or a conversation turn with no file),
                                  language, what was heard or read, and TradeVoice's reply for a turn
Turning it off, or the account being erased, deletes that trader's folder. Not in the hourly backups.
"""
import datetime as dt
import io
import json
import os
import secrets
import shutil
import sqlite3
import threading
import wave

_lock = threading.Lock()


def _dir():
    import ledger
    return os.getenv("TRAIN_DIR") or os.path.join(os.path.dirname(os.path.abspath(ledger.BOOKS_DIR)), "training")


def _db():
    import accounts
    c = sqlite3.connect(accounts.ACCOUNTS_DB, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS training (phone TEXT PRIMARY KEY, answer INTEGER, asked_at TEXT, at TEXT)")
    return c


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _phone(phone=None):
    """The given number, or the trader whose book is open (web request, WhatsApp message, live talk)."""
    import events
    return phone or events._current_phone()


def answer(phone=None):
    """True (yes), False (no) or None (not answered)."""
    phone = _phone(phone)
    if not phone:
        return None
    with _db() as c:
        r = c.execute("SELECT answer FROM training WHERE phone=?", (phone,)).fetchone()
    return None if not r or r["answer"] is None else bool(r["answer"])


def asked(phone):
    with _db() as c:
        r = c.execute("SELECT asked_at FROM training WHERE phone=?", (phone,)).fetchone()
    return bool(r and r["asked_at"])


def mark_asked(phone):
    with _lock, _db() as c:
        c.execute("INSERT INTO training (phone, asked_at) VALUES (?,?) ON CONFLICT(phone) DO UPDATE SET "
                  "asked_at=COALESCE(asked_at, excluded.asked_at)", (phone, _now()))


def set_answer(phone, yes):
    """Yes: keep from now on. No: stop, and delete what was kept."""
    with _lock, _db() as c:
        c.execute("INSERT INTO training (phone, answer, asked_at, at) VALUES (?,?,?,?) ON CONFLICT(phone) DO UPDATE "
                  "SET answer=excluded.answer, at=excluded.at, asked_at=COALESCE(asked_at, excluded.asked_at)",
                  (phone, int(bool(yes)), _now(), _now()))
    if not yes:
        erase(phone, keep_answer=True)
    try:
        import events
        events.log("training_answer", phone, engine="yes" if yes else "no")
    except Exception:  # noqa: BLE001
        pass
    return bool(yes)


def folder(phone):
    import events
    return os.path.join(_dir(), events._hash(phone))


def _write(phone, data, ext, kind, lang, heard):
    d = folder(phone)
    os.makedirs(d, mode=0o700, exist_ok=True)
    name = f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}{ext}"
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
    if isinstance(heard, dict):
        heard = {k: v for k, v in heard.items() if k in ("text", "detected", "engine", "rows", "not_record")}
    with _lock, open(os.path.join(d, "manifest.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"file": name, "kind": kind, "lang": lang or "", "heard": heard, "at": _now()},
                           ensure_ascii=False, default=str) + "\n")
    try:
        import events
        events.log("training_kept", phone, engine=kind)
    except Exception:  # noqa: BLE001
        pass
    return name


def keep(path, kind, lang="", heard=None, phone=None):
    """Before a voice note or photo is deleted: a copy for training if this trader said yes. Never raises."""
    try:
        phone = _phone(phone)
        if not phone or not answer(phone) or not path or not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            data = f.read()
        return _write(phone, data, os.path.splitext(path)[1].lower() or ".bin", kind, lang, heard)
    except Exception as e:  # noqa: BLE001
        print(f"training copy not kept: {type(e).__name__}: {e}")
        return None


def keep_pcm(pcm, lang="", heard=None, phone=None, rate=16000):
    """Live talk: the 16-bit mono audio the page streamed, as a WAV. Never raises."""
    try:
        phone = _phone(phone)
        if not phone or not pcm or not answer(phone):
            return None
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm)
        data, ext = _flac(b.getvalue())
        return _write(phone, data, ext, "live", lang, heard)
    except Exception as e:  # noqa: BLE001
        print(f"training copy not kept: {type(e).__name__}: {e}")
        return None


def keep_turn(kind, said, reply, lang="", extra=None, phone=None):
    """One conversation turn (live talk, Ask chat, a voice question, WhatsApp): what the trader said and what
    TradeVoice answered, kept only if this trader said yes. No file, one manifest line. Never raises."""
    try:
        phone = _phone(phone)
        if not phone or not (said or reply) or not answer(phone):
            return None
        d = folder(phone)
        os.makedirs(d, mode=0o700, exist_ok=True)
        line = {"file": None, "kind": kind, "lang": lang or "", "heard": {"text": said}, "reply": reply,
                "at": _now()} | ({"extra": extra} if extra else {})
        with _lock, open(os.path.join(d, "manifest.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"conversation turn not kept: {type(e).__name__}: {e}")
        return None


def items(after="", limit=100):
    """For the team dashboard: what consenting traders said and sent, newest first: (code, line) pairs."""
    root, out = _dir(), []
    if not os.path.isdir(root):
        return out
    for code in os.listdir(root):
        m = os.path.join(root, code, "manifest.jsonl")
        if not os.path.exists(m):
            continue
        for line in open(m, encoding="utf-8"):
            try:
                x = json.loads(line)
            except ValueError:
                continue
            if x.get("at", "") > after:
                out.append({"who": code, **x})
    out.sort(key=lambda x: x.get("at", ""), reverse=True)
    return out[:limit]


def media_path(code, name):
    """The file for the dashboard's player, or None (only a kept file inside that trader's folder)."""
    import re
    if not re.fullmatch(r"[0-9a-f]{16}", code or "") or not re.fullmatch(r"[\w.-]+", name or "") or ".." in name:
        return None
    p = os.path.join(_dir(), code, name)
    return p if name != "manifest.jsonl" and os.path.isfile(p) else None


def _flac(wav_bytes):
    """Lossless and about half the size of WAV (live talk adds up fast on the server's disk). WAV if ffmpeg is missing."""
    import subprocess
    import tempfile
    if not shutil.which("ffmpeg"):
        return wav_bytes, ".wav"
    d = tempfile.mkdtemp()
    try:
        src, out = os.path.join(d, "in.wav"), os.path.join(d, "out.flac")
        with open(src, "wb") as f:
            f.write(wav_bytes)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-c:a", "flac", out], check=True, timeout=60)
        with open(out, "rb") as f:
            return f.read(), ".flac"
    except Exception:  # noqa: BLE001
        return wav_bytes, ".wav"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def erase(phone, keep_answer=False):
    """Delete everything kept for this trader (and their answer, unless keep_answer)."""
    shutil.rmtree(folder(phone), ignore_errors=True)
    if not keep_answer:
        with _lock, _db() as c:
            c.execute("DELETE FROM training WHERE phone=?", (phone,))


def stats():
    """For /team: how many said yes / no, and what is kept (counts and size only)."""
    with _db() as c:
        yes = c.execute("SELECT COUNT(*) FROM training WHERE answer=1").fetchone()[0]
        no = c.execute("SELECT COUNT(*) FROM training WHERE answer=0").fetchone()[0]
    kinds, size = {}, 0
    root = _dir()
    if os.path.isdir(root):
        for d in os.listdir(root):
            m = os.path.join(root, d, "manifest.jsonl")
            if os.path.exists(m):
                for line in open(m, encoding="utf-8"):
                    k = json.loads(line).get("kind", "?")
                    kinds[k] = kinds.get(k, 0) + 1
            for f in os.listdir(os.path.join(root, d)):
                size += os.path.getsize(os.path.join(root, d, f))
    return {"yes": yes, "no": no, "kept": kinds, "mb": round(size / 1e6, 1)}
