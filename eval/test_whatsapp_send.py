"""WhatsApp for the pilot, against a faked Meta: sign-up when the code can't be sent (the trader sends LOGIN <word>
and the page carries on), Meta's 24-hour window and templates, delivery failures shown on /team, signatures,
limits on codes and floods, and message types (reaction, photo sent as a file, caption, too big).
Made-up numbers only. python eval/test_whatsapp_send.py
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "WHATSAPP_", "NATLAS", "INTRON")) or k in ("AUTH_DEMO", "TV_PUBLIC"):
        os.environ.pop(k)
os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "shared.db"), BOOKS_DIR=tempfile.mkdtemp(),
                  ACCOUNTS_DB=os.path.join(tempfile.mkdtemp(), "a.db"), TRAIN_DIR=tempfile.mkdtemp(),
                  TRADEVOICE_ADMIN="0", AUTH_REQUIRED="1", AUTO_REMINDERS="0", WHATSAPP_TOKEN="test",
                  WHATSAPP_PHONE_ID="123", WHATSAPP_APP_SECRET="s3cret", WHATSAPP_VERIFY_TOKEN="v",
                  WHATSAPP_DISPLAY_NUMBER="2348000000999")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import events  # noqa: E402
import ledger  # noqa: E402
import photo  # noqa: E402
import team  # noqa: E402
import web  # noqa: E402
import whatsapp  # noqa: E402

SENT = []
whatsapp.graph_post = lambda p: SENT.append(p) or {"messages": [{"id": "x"}]}
whatsapp.mark_read = lambda *a: None
whatsapp.send_voice = lambda *a: None
CHECKS = []
c = TestClient(web.app)
n = 0


def check(name, ok, got=""):
    CHECKS.append(bool(ok))
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def post(payload, sign=True):
    body = json.dumps({"entry": [{"changes": [{"value": payload}]}]})
    h = {"Content-Type": "application/json"}
    if sign:
        h["X-Hub-Signature-256"] = "sha256=" + hmac.new(b"s3cret", body.encode(), hashlib.sha256).hexdigest()
    return c.post("/whatsapp/webhook", content=body, headers=h)


def msg(frm, **m):
    global n
    n += 1
    return post({"messages": [{"from": frm, "id": f"m{n}", **m}]})


def said(to=None):
    return " ".join(json.dumps(p) for p in SENT if not to or p.get("to") == to)


def ready(phone):
    """A trader who already chose English and agreed (the bot's sign-up done)."""
    tok = ledger.use_book(phone)
    whatsapp.user(phone)
    whatsapp.set_user(phone, lang="English", consent_at="2026-10-01T09:00:00")
    ledger._BOOK.reset(tok)


def main():
    # 1. sign-up when no code can be sent: the trader writes first ("LOGIN MANGO-123"), the page carries on
    r = c.post("/api/auth/v2/code/start", json={"phone": "08030000701", "purpose": "signup"}).json()
    check("never wrote to the bot, no template: no code is sent (Meta would drop it), LOGIN offered instead",
          r["sent"] is False and r["word"] and r["bot"] == "2348000000999" and not SENT, r)
    check("…the page waits: not confirmed yet", c.post("/api/auth/v2/code/poll", json={"login_id": r["login_id"]}).json()
          == {"ok": False})
    msg("2348030000799", type="text", text={"body": f"LOGIN {r['word']}"})
    check("LOGIN from another phone is refused", "not for this number" in said("2348030000799"))
    msg("2348030000701", type="text", text={"body": f"LOGIN {r['word']}"})
    check("LOGIN from that phone: confirmed, and told to go back", "confirmed" in said("2348030000701"))
    check("…the page carries on by itself", c.post("/api/auth/v2/code/poll", json={"login_id": r["login_id"]}).json()
          == {"ok": True})
    s = c.post("/api/auth/v2/signup", json={"login_id": r["login_id"], "pw": "x" * 64, "name": "Ada Testtrader",
                                           "biz": "Ada Test Stores"})
    check("…and sign-up finishes with that confirmation", s.status_code == 200 and s.json()["me"]["biz"] == "Ada Test Stores",
          s.text)
    SENT.clear()
    r = c.post("/api/auth/v2/code/start", json={"phone": "08030000701", "purpose": "login"}).json()
    check("after writing to the bot (window open): the code itself goes by WhatsApp",
          r["sent"] and "Your TradeVoice code is" in said("2348030000701"), r)

    # 2. the live server without the app secret: LOGIN by message is off (anyone could fake it)
    os.environ["TV_PUBLIC"], secret = "1", os.environ.pop("WHATSAPP_APP_SECRET")
    r = c.post("/api/auth/v2/code/start", json={"phone": "08030000702", "purpose": "signup"})
    check("live server, no app secret, no window: nothing to offer -> 503", r.status_code == 503, r.text)
    SENT.clear()
    whatsapp.handle({"from": "2348030000702", "type": "text", "id": "x1", "text": {"body": "LOGIN MANGO-123"}})
    check("…and a LOGIN message is refused politely", "switched off" in said("2348030000702"), SENT)
    os.environ["WHATSAPP_APP_SECRET"] = secret
    os.environ.pop("TV_PUBLIC")

    # 3. too many codes for one number
    codes = [c.post("/api/auth/v2/code/start", json={"phone": "08030000703", "purpose": "signup"}).status_code
             for _ in range(6)]
    check("at most 5 codes an hour for one number", codes[:5] == [200] * 5 and codes[5] == 429, codes)

    # 4. messages we send first: free text in the window, else the template, else not sent (and shown on /team)
    events.ENABLED = True
    SENT.clear()
    whatsapp.saw("2348030000704")
    check("window open: plain text", whatsapp.send_first("2348030000704", "summary", "Iya Bisi promised to pay today.")
          and SENT[-1]["type"] == "text")
    SENT.clear()
    before = whatsapp.STATS["not_sent"]
    check("window closed, no template: not sent, counted", whatsapp.send_first("2348030000705", "summary", "x") is False
          and not SENT and whatsapp.STATS["not_sent"] == before + 1)
    os.environ["WHATSAPP_TPL_SUMMARY"], os.environ["WHATSAPP_TPL_CODE"] = "tradevoice_daily", "tradevoice_code"
    whatsapp.send_first("2348030000705", "summary", "Line one.\nLine two.", params=["2 customers\tpay today."])
    t = SENT[-1]["template"]
    check("window closed, template set: the template, with values on one line (Meta refuses new lines)",
          t["name"] == "tradevoice_daily" and t["components"][0]["parameters"][0]["text"] == "2 customers pay today.", t)
    whatsapp.send_code("2348030000706", "123456")
    t = SENT[-1]["template"]
    check("a code outside the window: the authentication template, code in the body and the copy button",
          t["name"] == "tradevoice_code" and t["components"][0]["parameters"][0]["text"] == "123456"
          and t["components"][1]["parameters"][0]["text"] == "123456", t)
    os.environ.pop("WHATSAPP_TPL_SUMMARY"), os.environ.pop("WHATSAPP_TPL_CODE")

    # 5. Meta's delivery reports: a failure is shown on /team in words
    post({"statuses": [{"id": "wamid.1", "status": "delivered", "recipient_id": "2348030000704"}]})
    post({"statuses": [{"id": "wamid.2", "status": "failed", "recipient_id": "2348030000705",
                        "errors": [{"code": 131047, "title": "Re-engagement message"}]}]})
    check("delivery reports counted; a failure keeps its reason",
          whatsapp.STATS["delivered"] >= 1 and whatsapp.STATS["failed"] >= 1 and "24-hour" in whatsapp.STATS["last_error"])
    with events._db() as db:
        row = dict(db.execute("SELECT * FROM events WHERE kind='wa_failed' ORDER BY id DESC").fetchone())
    check("…on the dashboard: 'WhatsApp message not delivered: outside the 24-hour window…', no phone number",
          "24-hour" in team.describe(row)[1] and team.describe(row)[0] == "errors" and "2348030000705" not in json.dumps(row),
          team.describe(row))
    events.ENABLED = False

    # 6. signatures, floods, message types
    check("an unsigned post is refused", post({"messages": []}, sign=False).status_code == 401)
    ready("2348030000710")
    before = whatsapp.STATS["flood_dropped"]
    for _ in range(whatsapp.FLOOD_MAX + 3):
        msg("2348030000711", type="reaction", reaction={"emoji": "x", "message_id": "m"})
    check("more than 30 messages a minute from one number: the rest are dropped", whatsapp.STATS["flood_dropped"] - before == 3)
    SENT.clear()
    msg("2348030000710", type="reaction", reaction={"emoji": "x", "message_id": "m1"})
    msg("2348030000710", type="sticker", sticker={"id": "s1"})
    check("a reaction or a sticker gets no reply", not said("2348030000710"), SENT)
    path = os.path.join(tempfile.mkdtemp(), "p.jpg")
    open(path, "wb").write(b"\xff\xd8x")
    whatsapp.download = lambda media_id, suffix: (open(path + "2", "wb").write(b"x"), path + "2")[1]
    photo.read = lambda p: {"rows": [{"type": "sale", "item": "rice", "amount": 5000}]}
    msg("2348030000710", type="document", document={"id": "d1", "mime_type": "image/jpeg", "filename": "page.jpg"})
    check("a photo sent as a file is read like a photo", "rice" in said("2348030000710") or "5,000" in said("2348030000710"), SENT)
    SENT.clear()
    photo.read = lambda p: {"rows": []}
    msg("2348030000710", type="image", image={"id": "i1", "caption": "how much does Iya Bisi owe me?"})
    check("a photo with no lines but a caption: the caption is answered", said("2348030000710")
          and "couldn't find money records" not in said("2348030000710"), SENT)
    SENT.clear()

    def too_big(media_id, suffix):
        raise whatsapp.TooBig()
    whatsapp.download = too_big
    msg("2348030000710", type="audio", audio={"id": "a1"})
    check("a file over 16 MB: a plain message, not 'something went wrong'", "too big" in said("2348030000710")
          and "went wrong" not in said("2348030000710"), SENT)

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} WhatsApp sending checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
