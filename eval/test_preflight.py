"""The pilot check (scripts/preflight.py): with nothing reachable every line fails or warns with a clear reason, keys
and tokens never appear in the output (even inside an error), and the local checks pass when things are in place.
No network needed: every service points at a closed local port. python eval/test_preflight.py
"""
import contextlib
import datetime as dt
import io
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith(("API_KEY", "_TOKEN", "_SECRET", "_URL")) or k.startswith(("NATLAS", "WHATSAPP_", "INTRON", "BACKUP_", "TEAM_", "TTS_")):
        os.environ.pop(k)
D = tempfile.mkdtemp()
SECRET = "sekrit-key-0042"
os.environ.update(ACCOUNTS_DB=os.path.join(D, "a.db"), BOOKS_DIR=os.path.join(D, "books"), DB_PATH=os.path.join(D, "t.db"),
                  BACKUP_DIR=os.path.join(D, "backups"), PORT="9", PUBLIC_URL="http://127.0.0.1:9",
                  NATLAS_URL="http://127.0.0.1:9/v1", NATLAS_KEY=SECRET, NVIDIA_API_KEY=SECRET, INTRON_API_KEY=SECRET,
                  INTRON_STT_WS="ws://127.0.0.1:9/stt/v1/stream", INTRON_TTS_WS="ws://127.0.0.1:9/tts/v1/stream",
                  INTRON_TTS_URL="http://127.0.0.1:9", WHATSAPP_TOKEN=SECRET, WHATSAPP_PHONE_ID="123",
                  WHATSAPP_GRAPH_VERSION="v0", NVIDIA_BASE_URL="http://127.0.0.1:9/v1", LLM_DEADLINE="5", NATLAS_TIMEOUT="3")
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import preflight  # noqa: E402
import whatsapp  # noqa: E402

whatsapp.GRAPH = "http://127.0.0.1:9"
CHECKS = []


def check(name, ok, got=""):
    CHECKS.append(bool(ok))
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def main():
    check("keys are masked inside any error text", preflight.scrub(f"401 for Bearer {SECRET}") == "401 for Bearer ***")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = preflight.main()
    txt = out.getvalue()
    print(txt)
    rows = {line[6:].split("  ")[0].strip(): line[:4] for line in txt.splitlines() if line[:4] in ("PASS", "WARN", "FAIL")}
    check("every check prints one line", len(rows) == len(preflight.CHECKS), rows)
    check("nothing reachable: the services fail", all(rows.get(n) == "FAIL" for n in (
        "App answering", "Public link", "N-ATLaS brain", "NVIDIA models", "Intron voice replies", "Intron live hearing",
        "WhatsApp bot", "Backups")), rows)
    check("…with the reason in plain words", "no backup yet" in txt and "NATLAS" not in txt.split("N-ATLaS brain")[0][-5:])
    check("…and the summary says what to do, exit code 1", "to fix first (FAIL)" in txt and code == 1)
    check("no key or token appears anywhere in the output", SECRET not in txt)

    # the local checks pass when things are in place
    os.makedirs(os.environ["BACKUP_DIR"], exist_ok=True)
    name = dt.datetime.now().strftime("tradevoice-%Y%m%d-%H%M%S.tar.gz")
    open(os.path.join(os.environ["BACKUP_DIR"], name), "w").close()
    st, detail = preflight.backups()
    check("a fresh backup, only on this server: FAIL (a dead server loses every book)", st == "FAIL" and "only on this server" in detail, detail)
    os.environ["BACKUP_SUPABASE_URL"] = "https://example.supabase.co"
    st, detail = preflight.backups()
    check("…with an off-server copy set: PASS", st == "PASS" and "supabase" in detail, detail)
    st, detail = preflight.settings_needed()
    check("settings: missing dashboard key and privacy contact is a FAIL that names them",
          st == "FAIL" and "ADMIN_TOKEN" in detail and "PRIVACY_CONTACT" in detail, detail)
    os.environ.update(ADMIN_TOKEN=SECRET, PRIVACY_CONTACT="privacy@example.com", TEAM_PHONES="08000000001")
    st, detail = preflight.settings_needed()
    check("…all set: PASS, without showing the dashboard key", st == "PASS" and SECRET not in detail, detail)
    os.environ["NATLAS_WATCH"] = "0"
    check("N-ATLaS not kept awake: a WARN that says why it matters", preflight.keep_awake()[0] == "WARN")
    os.environ["NATLAS_WATCH"] = "1"
    check("disk and folders: checked on this machine", preflight.disk()[0] in ("PASS", "WARN", "FAIL")
          and preflight.tools()[0] in ("PASS", "FAIL"))
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} pilot-check checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
