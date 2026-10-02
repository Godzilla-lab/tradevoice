"""Back up every trader's book and the accounts: safe copies even while the app is running (SQLite's own backup).

    python scripts/backup.py                        one backup now, old ones pruned
    python scripts/backup.py --list                 the backups on this machine
    python scripts/backup.py --restore FILE|FOLDER  put a backup (or the files downloaded from Modal) back. Stop the app first.

A backup is one file: $BACKUP_DIR/tradevoice-YYYYMMDD-HHMMSS.tar.gz (accounts.db, tradevoice.db, books/<phone>.db).
Kept: every backup from the last 48 hours, and the newest of each day for 30 days.
BACKUP_UPLOAD_URL (optional, in .env): where each backup is also uploaded, so a copy lives off the server. Either an
Azure Blob Storage container SAS URL (https://ACCOUNT.blob.core.windows.net/CONTAINER?sv=…&sig=…) or an Oracle Object
Storage pre-authenticated request URL (ends in /o/). The file's name goes into the path, before any ?query. Backups hold traders' personal data: keep them private.
BACKUP_SUPABASE_URL + BACKUP_SUPABASE_KEY (optional): a copy in Supabase Storage (free, no card), see supabase_upload.
BACKUP_COPY_DIR (optional): a folder that also gets each backup, pruned the same way. On the Mac: a Google Drive
folder (Google Drive for desktop), so a copy lives off the Mac.
On the live server the hourly timer runs this (deploy/server/setup.sh); restore there with deploy/server/restore.sh.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import settings  # noqa: E402,F401  (loads .env)

NAME_RE = re.compile(r"^tradevoice-(\d{8}-\d{6})\.tar\.gz$")
MEMBER_RE = re.compile(r"^(accounts\.db|tradevoice\.db|books/\d+\.db)$")   # nothing else is ever restored
KEEP_ALL_HOURS, KEEP_DAILY_DAYS = 48, 30


def _path(env, default):
    p = os.getenv(env, default)
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def paths():
    return {"accounts.db": _path("ACCOUNTS_DB", "accounts.db"), "tradevoice.db": _path("DB_PATH", "tradevoice.db"),
            "books": _path("BOOKS_DIR", "books"), "backups": _path("BACKUP_DIR", "backups")}


def _copy_db(src, dst):
    """A consistent copy of a live SQLite file, then checked."""
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
        ok = d.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        s.close()
        d.close()
    if ok != "ok":
        raise RuntimeError(f"{os.path.basename(src)} copy failed its check: {ok}")


def backup(now=None):
    p = paths()
    now = now or dt.datetime.now()
    os.makedirs(p["backups"], mode=0o700, exist_ok=True)
    name = f"tradevoice-{now:%Y%m%d-%H%M%S}.tar.gz"
    work = tempfile.mkdtemp(dir=p["backups"], prefix=".work-")
    try:
        files = []
        for arc in ("accounts.db", "tradevoice.db"):
            if os.path.exists(p[arc]):
                _copy_db(p[arc], os.path.join(work, arc))
                files.append(arc)
        if os.path.isdir(p["books"]):
            os.makedirs(os.path.join(work, "books"))
            for f in sorted(os.listdir(p["books"])):
                if MEMBER_RE.match("books/" + f):
                    _copy_db(os.path.join(p["books"], f), os.path.join(work, "books", f))
                    files.append("books/" + f)
        tmp = os.path.join(p["backups"], "." + name)
        with tarfile.open(tmp, "w:gz") as t:
            for arc in files:
                t.add(os.path.join(work, arc), arcname=arc)
        os.chmod(tmp, 0o600)
        os.replace(tmp, os.path.join(p["backups"], name))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    books = sum(f.startswith("books/") for f in files)
    print(f"backup {name}: {books} book(s){', accounts' if 'accounts.db' in files else ''}")
    return os.path.join(p["backups"], name)


def to_prune(names, now=None):
    """Of these backup names: the ones to delete (older than 48 h, except the newest of each day for 30 days)."""
    now = now or dt.datetime.now()
    found = sorted((dt.datetime.strptime(m.group(1), "%Y%m%d-%H%M%S"), f) for f in names if (m := NAME_RE.match(f)))
    keep, newest_of_day = set(), {}
    for t, f in found:
        if now - t <= dt.timedelta(hours=KEEP_ALL_HOURS):
            keep.add(f)
        elif now - t <= dt.timedelta(days=KEEP_DAILY_DAYS):
            newest_of_day[t.date()] = f        # sorted, so the last one per day wins
    keep |= set(newest_of_day.values())
    return [f for _, f in found if f not in keep]


def prune(folder, now=None):
    """Delete the old backups in a folder (see to_prune). Returns what was deleted."""
    gone = to_prune(os.listdir(folder), now)
    for f in gone:
        os.remove(os.path.join(folder, f))
    return gone


def upload(path):
    url = os.getenv("BACKUP_UPLOAD_URL", "").strip()
    if not url:
        return False
    u = urllib.parse.urlsplit(url)   # the name goes into the path; an Azure SAS keeps its ?sv=…&sig=… after it
    target = urllib.parse.urlunsplit(u._replace(path=u.path.rstrip("/") + "/" + os.path.basename(path)))
    with open(path, "rb") as f:
        req = urllib.request.Request(target, data=f.read(), method="PUT",
                                     headers={"Content-Type": "application/gzip", "x-ms-blob-type": "BlockBlob"})
    urllib.request.urlopen(req, timeout=120).close()
    print("uploaded off the server ✅")
    return True


def _supabase(method, path, body=None, data=None, headers=None):
    base = os.getenv("BACKUP_SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("BACKUP_SUPABASE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}"} | (headers or {})
    if body is not None:
        data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    with urllib.request.urlopen(urllib.request.Request(base + path, data=data, method=method, headers=h), timeout=120) as r:
        return json.loads(r.read() or b"null")


def supabase_upload(path, now=None):
    """Supabase Storage (free, no card): BACKUP_SUPABASE_URL (https://PROJECT.supabase.co), BACKUP_SUPABASE_KEY
    (the project's secret / service_role key) and BACKUP_SUPABASE_BUCKET (default "backups", private). Old copies there
    are pruned the same way as here."""
    if not (os.getenv("BACKUP_SUPABASE_URL", "").strip() and os.getenv("BACKUP_SUPABASE_KEY", "").strip()):
        return False
    bucket = urllib.parse.quote(os.getenv("BACKUP_SUPABASE_BUCKET", "backups").strip() or "backups")
    with open(path, "rb") as f:
        _supabase("POST", f"/storage/v1/object/{bucket}/{os.path.basename(path)}", data=f.read(),
                  headers={"Content-Type": "application/gzip", "x-upsert": "true"})
    listed = _supabase("POST", f"/storage/v1/object/list/{bucket}",
                       {"prefix": "", "limit": 1000, "offset": 0, "sortBy": {"column": "name", "order": "asc"}}) or []
    old = to_prune([o.get("name", "") for o in listed], now)
    if old:
        _supabase("DELETE", f"/storage/v1/object/{bucket}", {"prefixes": old})
    print("copied to Supabase ✅")
    return True


def _app_running():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{os.getenv('PORT', '8000')}/api/status", timeout=3).close()
        return True
    except Exception:  # noqa: BLE001
        return False


def restore(source, force=False):
    """Puts accounts.db, tradevoice.db and books/ back from a backup file or a folder. The current files are moved
    to $BACKUP_DIR/before-restore-<time>/ first (never deleted)."""
    p = paths()
    if not force and _app_running():
        raise SystemExit("The app is running. Stop it first (on the server: sudo bash deploy/server/restore.sh FILE).")
    work = tempfile.mkdtemp(prefix="tv-restore-")
    try:
        if os.path.isdir(source):
            for dirpath, _, names in os.walk(source):
                for n in names:
                    arc = os.path.relpath(os.path.join(dirpath, n), source).replace(os.sep, "/")
                    if MEMBER_RE.match(arc):
                        os.makedirs(os.path.dirname(os.path.join(work, arc)), exist_ok=True)
                        shutil.copyfile(os.path.join(source, arc), os.path.join(work, arc))
        else:
            with tarfile.open(source, "r:gz") as t:
                for m in t.getmembers():
                    if not m.isfile() or not MEMBER_RE.match(m.name):
                        raise SystemExit(f"Refusing: unexpected file in the backup: {m.name!r}")
                    os.makedirs(os.path.dirname(os.path.join(work, m.name)) or work, exist_ok=True)
                    with t.extractfile(m) as src, open(os.path.join(work, m.name), "wb") as dst:
                        shutil.copyfileobj(src, dst)
        found = [a for a in ("accounts.db", "tradevoice.db") if os.path.exists(os.path.join(work, a))]
        books = sorted(os.listdir(os.path.join(work, "books"))) if os.path.isdir(os.path.join(work, "books")) else []
        if "accounts.db" not in found:
            raise SystemExit("Refusing: no accounts.db in that backup.")
        for arc in found + ["books/" + b for b in books]:
            c = sqlite3.connect(os.path.join(work, arc))
            ok = c.execute("PRAGMA integrity_check").fetchone()[0]
            c.close()
            if ok != "ok":
                raise SystemExit(f"Refusing: {arc} is damaged ({ok}).")

        os.makedirs(p["backups"], mode=0o700, exist_ok=True)
        keep = tempfile.mkdtemp(dir=p["backups"], prefix=f"before-restore-{dt.datetime.now():%Y%m%d-%H%M%S}-")
        for arc in ("accounts.db", "tradevoice.db"):
            for suffix in ("", "-wal", "-shm", "-journal"):
                if os.path.exists(p[arc] + suffix):
                    shutil.move(p[arc] + suffix, os.path.join(keep, arc + suffix))
        if os.path.isdir(p["books"]):
            shutil.move(p["books"], os.path.join(keep, "books"))
        os.makedirs(p["books"], mode=0o700)
        for arc in found:
            shutil.copyfile(os.path.join(work, arc), p[arc])
            os.chmod(p[arc], 0o600)
        for b in books:
            shutil.copyfile(os.path.join(work, "books", b), os.path.join(p["books"], b))
            os.chmod(os.path.join(p["books"], b), 0o600)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"restored {len(books)} book(s) and the accounts. The old files are in {keep}")
    return keep


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--list", action="store_true")
    a.add_argument("--restore", metavar="FILE_OR_FOLDER")
    a.add_argument("--force", action="store_true", help="restore even if the app answers (not recommended)")
    args = a.parse_args(argv)
    p = paths()
    if args.list:
        os.makedirs(p["backups"], exist_ok=True)
        for f in sorted(os.listdir(p["backups"])):
            if NAME_RE.match(f):
                print(f"{f}  {os.path.getsize(os.path.join(p['backups'], f)) // 1024} KB")
        return 0
    if args.restore:
        restore(args.restore, args.force)
        return 0
    path = backup()
    for f in prune(p["backups"]):
        print(f"pruned {f}")
    ok = True
    copy_dir = os.getenv("BACKUP_COPY_DIR", "").strip()
    if copy_dir:
        try:
            os.makedirs(copy_dir, exist_ok=True)
            shutil.copyfile(path, os.path.join(copy_dir, "." + os.path.basename(path)))
            os.replace(os.path.join(copy_dir, "." + os.path.basename(path)), os.path.join(copy_dir, os.path.basename(path)))
            prune(copy_dir)
            print("copied to the backup folder ✅")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ copy to BACKUP_COPY_DIR failed ({type(e).__name__}: {e}); the backup is still here")
            ok = False
    try:
        upload(path)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ upload off the server failed ({type(e).__name__}); the backup is still on this server")
        ok = False
    try:
        supabase_upload(path)
    except Exception as e:  # noqa: BLE001  (never print the key or the URL's secrets)
        print(f"⚠️ copy to Supabase failed ({type(e).__name__}: {getattr(e, 'code', '')}); the backup is still here")
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
