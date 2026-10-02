"""scripts/backup.py: safe copies of the books + accounts, pruning, and restore (from a backup or Modal's files).

python eval/test_backup.py
"""
import datetime as dt
import io
import os
import sqlite3
import sys
import tarfile
import shutil
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
os.environ.pop("BACKUP_UPLOAD_URL", None)
D = tempfile.mkdtemp()
os.environ.update(ACCOUNTS_DB=os.path.join(D, "accounts.db"), DB_PATH=os.path.join(D, "tradevoice.db"),
                  BOOKS_DIR=os.path.join(D, "books"), BACKUP_DIR=os.path.join(D, "backups"), PORT="1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import backup  # noqa: E402

CHECKS = []


def check(name, ok, got=""):
    ok = bool(ok)
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:300]}"))


def db(path, rows):
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode=WAL")   # like a live book: data still in the -wal file
    c.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    c.executemany("INSERT INTO t VALUES (?)", [(r,) for r in rows])
    c.commit()
    return c   # left open on purpose: the backup must work while the app holds the file


def rows(path):
    c = sqlite3.connect(path)
    try:
        return [r[0] for r in c.execute("SELECT v FROM t ORDER BY rowid")]
    finally:
        c.close()


def main():
    os.makedirs(os.path.join(D, "books"))
    live = [db(os.environ["ACCOUNTS_DB"], ["ada"]), db(os.environ["DB_PATH"], ["shared"]),
            db(os.path.join(D, "books", "2348030000521.db"), ["Iya Bisi 60000"]),
            db(os.path.join(D, "books", "2348030000522.db"), ["Oga Emeka 25000"])]
    open(os.path.join(D, "books", "notes.txt"), "w").write("not a book")

    path = backup.backup()
    with tarfile.open(path) as t:
        names = sorted(t.getnames())
    check("backup holds accounts, shared db and both books (nothing else)",
          names == ["accounts.db", "books/2348030000521.db", "books/2348030000522.db", "tradevoice.db"], names)
    check("backup file is private (owner only)", oct(os.stat(path).st_mode & 0o777) == "0o600", oct(os.stat(path).st_mode))
    with tarfile.open(path) as t:
        x = os.path.join(D, "x.db")
        open(x, "wb").write(t.extractfile("books/2348030000521.db").read())
    check("the copy has the data that was only in the live -wal file", rows(x) == ["Iya Bisi 60000"], rows(x))

    # the copy off the server: one PUT of the file to BACKUP_UPLOAD_URL + its name
    import http.server
    import threading
    got = {}

    class Put(http.server.BaseHTTPRequestHandler):
        def do_PUT(self):
            got[self.path] = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), Put)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["BACKUP_UPLOAD_URL"] = f"http://127.0.0.1:{srv.server_port}/p/SECRET/n/ns/b/tradevoice-backups/o/"
    backup.upload(path)
    want = "/p/SECRET/n/ns/b/tradevoice-backups/o/" + os.path.basename(path)
    check("upload: the backup lands off the server, whole", got.get(want) == open(path, "rb").read(), list(got))
    srv.shutdown()
    os.environ.pop("BACKUP_UPLOAD_URL")

    # pruning: everything for 48 h, then the newest of each day for 30 days (a pretend "today" 18 days on)
    folder = os.environ["BACKUP_DIR"]
    path = shutil.copy(path, os.path.join(D, "saved.tar.gz"))
    now = dt.datetime(2026, 10, 20, 12, 0, 0)
    made = []
    for h in range(0, 24 * 40, 6):
        t = now - dt.timedelta(hours=h)
        f = f"tradevoice-{t:%Y%m%d-%H%M%S}.tar.gz"
        open(os.path.join(folder, f), "w").close()
        made.append((t, f))
    backup.prune(folder, now)
    left = {f for f in os.listdir(folder) if backup.NAME_RE.match(f)}
    recent = {f for t, f in made if now - t <= dt.timedelta(hours=48)}
    check("prune keeps every backup from the last 48 hours", recent <= left, sorted(recent - left))
    days = {t.date() for t, f in made if f in left and now - t > dt.timedelta(hours=48)}
    per_day = [sum(1 for t, f in made if f in left and t.date() == d and now - t > dt.timedelta(hours=48)) for d in days]
    check("…then one per day", per_day and max(per_day) == 1, per_day)
    check("…and nothing older than 30 days", all(now - t <= dt.timedelta(days=30) for t, f in made if f in left))
    for t, f in made:
        if f in left:
            os.remove(os.path.join(folder, f))

    # restore refuses while the app answers
    real = backup._app_running
    backup._app_running = lambda: True
    try:
        backup.restore(path)
        check("restore refuses while the app is running", False)
    except SystemExit:
        check("restore refuses while the app is running", True)
    backup._app_running = real

    # restore a backup: data back, old files kept aside
    for c in live:
        c.close()
    sqlite3.connect(os.path.join(D, "books", "2348030000521.db")).execute("DELETE FROM t").connection.commit()
    keep = backup.restore(path)
    check("restore brings the book back", rows(os.path.join(D, "books", "2348030000521.db")) == ["Iya Bisi 60000"])
    check("restore keeps the replaced files aside, not deleted",
          os.path.exists(os.path.join(keep, "books", "2348030000521.db")) and os.path.exists(os.path.join(keep, "accounts.db")))

    # restore from a folder (the files downloaded from the Modal volume)
    modal = os.path.join(D, "modal-data")
    os.makedirs(os.path.join(modal, "books"))
    db(os.path.join(modal, "accounts.db"), ["from modal"]).close()
    db(os.path.join(modal, "books", "2348030000999.db"), ["Hajiya Amina 5000"]).close()
    backup.restore(modal)
    check("restore from Modal's folder: accounts + books in place",
          rows(os.environ["ACCOUNTS_DB"]) == ["from modal"]
          and os.listdir(os.path.join(D, "books")) == ["2348030000999.db"], os.listdir(os.path.join(D, "books")))

    # a tampered backup is refused
    bad = os.path.join(D, "bad.tar.gz")
    with tarfile.open(bad, "w:gz") as t:
        data = b"x"
        info = tarfile.TarInfo("../../etc/evil")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    try:
        backup.restore(bad)
        check("a backup with strange paths is refused", False)
    except SystemExit:
        check("a backup with strange paths is refused", True)

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} backup checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
