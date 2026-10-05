"""Help make TradeVoice better (src/training.py): voice notes, photos, live talk and chats are kept ONLY for traders
who said yes, asked once and separately (web + WhatsApp); no keeps nothing and deletes what was kept; erasing the
account erases them; the dashboard's file links can't reach outside a trader's folder. Made-up numbers only.

python eval/test_training.py
"""
import io
import json
import os
import sys
import tempfile
import wave

os.environ["TV_NO_DOTENV"] = "1"
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith(("LOCAL_", "WHATSAPP_", "NATLAS", "INTRON")) or k in ("AUTH_DEMO", "TV_PUBLIC"):
        os.environ.pop(k)
os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "shared.db"), BOOKS_DIR=tempfile.mkdtemp(),
                  ACCOUNTS_DB=os.path.join(tempfile.mkdtemp(), "a.db"), TRAIN_DIR=tempfile.mkdtemp(),
                  TRADEVOICE_ADMIN="0", AUTH_REQUIRED="1", AUTO_REMINDERS="0")
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from fastapi.testclient import TestClient  # noqa: E402

import accounts  # noqa: E402
import add_account  # noqa: E402
import asr  # noqa: E402
import photo  # noqa: E402
import training  # noqa: E402
import web  # noqa: E402
import whatsapp  # noqa: E402

CHECKS = []
SENT = []
whatsapp.graph_post = lambda p: SENT.append(p) or {"messages": [{"id": "x"}]}
whatsapp.mark_read = lambda *a: None
asr.transcribe_auto = lambda path, lang, vocab=None: {"text": "Mama Ngozi took rice 5000 on credit", "engine": "test"}
photo.read = lambda path: {"rows": [{"type": "sale", "item": "rice", "amount": 5000}]}


def check(name, ok, got=""):
    ok = bool(ok)
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:300]}"))


def wav():
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000), w.writeframes(b"\1\0" * 1600)
    return b.getvalue()


def kept(phone):
    m = os.path.join(training.folder(phone), "manifest.jsonl")
    return [json.loads(x) for x in open(m, encoding="utf-8")] if os.path.exists(m) else []


def hear(c):
    return c.post("/api/hear", files={"file": ("v.wav", wav(), "audio/wav")}, data={"lang": "English", "consent": "yes"})


def main():
    phone, temp = add_account.create("08030000611", "Ada Testtrader", "Ada Test Stores")
    c = TestClient(web.app)
    r = c.post("/api/auth/v2/login", json={"phone": "08030000611", "pw": add_account.page_hash(temp)})
    me = r.json()["me"]
    check("a new trader: not answered, not asked yet", me["train"] is None and me["trainAsked"] is False, me)

    r = hear(c)
    check("not answered: the voice note is heard, then deleted (nothing kept)",
          r.status_code == 200 and not os.path.exists(training.folder(phone)), r.text)
    c.post("/api/v2/training", json={"yes": None})
    me = c.get("/api/v2/me").json()
    check("closing the question counts as asked (not asked again), still no answer",
          me["trainAsked"] and me["train"] is None, me)

    r = c.post("/api/v2/training", json={"yes": True})
    check("yes is saved", r.json() == {"train": True} and c.get("/api/v2/me").json()["train"] is True, r.text)
    hear(c)
    c.post("/api/photo", files={"file": ("p.jpg", b"\xff\xd8fakejpeg", "image/jpeg")}, data={"consent": "yes"})
    c.post("/api/ask", json={"session": "s1", "text": "who owes me money?", "lang": "English"})
    c.post("/api/say", json={"session": "s2", "text": "Mama Ngozi took rice 5000 on credit", "lang": "English"})
    k = kept(phone)
    kinds = [x["kind"] for x in k]
    check("yes: the voice note, the photo, the Ask chat turn and the live-talk turn are kept",
          {"voice", "photo", "ask_turn", "live_turn"} <= set(kinds), kinds)
    v = next(x for x in k if x["kind"] == "voice")
    check("…the voice note's file with what was heard", v["file"] and os.path.exists(
        os.path.join(training.folder(phone), v["file"])) and v["heard"]["text"].startswith("Mama Ngozi"), v)
    t = next(x for x in k if x["kind"] == "live_turn")
    check("…a turn keeps what was said and TradeVoice's reply", t["heard"]["text"] and t["reply"], t)
    check("…kept in a folder named by a code, never the phone number",
          phone not in training.folder(phone) and os.path.basename(training.folder(phone)).isalnum())
    items = training.items()
    check("the dashboard lists what was kept, newest first", len(items) == len(k) and items[0]["at"] >= items[-1]["at"])
    code = os.path.basename(training.folder(phone))
    check("the dashboard's file links: only a kept file inside that trader's folder",
          training.media_path(code, v["file"]) and not training.media_path(code, "manifest.jsonl")
          and not training.media_path(code, "../a.db") and not training.media_path("../../etc", "passwd"))
    s = training.stats()
    check("counts for the dashboard", s["yes"] == 1 and s["kept"].get("voice") == 1 and s["mb"] >= 0, s)

    r = c.post("/api/v2/training", json={"yes": False})
    check("no: stops, and deletes what was kept", r.json() == {"train": False} and not os.path.exists(training.folder(phone)))
    hear(c)
    check("…after no, nothing new is kept", not kept(phone))

    c.post("/api/v2/training", json={"yes": True})
    hear(c)
    accounts.delete_account(phone)
    check("erasing the account erases what was kept, and the answer",
          not os.path.exists(training.folder(phone)) and training.answer(phone) is None)

    # WhatsApp: asked once, right after "I agree", as its own question with two buttons
    wa = "2348030000622"
    for body in ("hi", "lang:English", "consent:yes"):
        whatsapp._safe({"from": wa, "type": "text", "id": "m", "text": {"body": body}})
    q = [p for p in SENT if p.get("type") == "interactive" and "train:yes" in json.dumps(p)]
    check("WhatsApp: after 'I agree', the separate question with Yes / No buttons", len(q) == 1, SENT[-2:])
    whatsapp._safe({"from": wa, "type": "interactive", "id": "m",
                    "interactive": {"button_reply": {"id": "train:yes", "title": "Yes, keep them"}}})
    check("…Yes is saved and thanked", training.answer(wa) is True and "Thank you" in json.dumps(SENT[-1]), SENT[-1])
    n = len(SENT)
    whatsapp._safe({"from": wa, "type": "text", "id": "m", "text": {"body": "improve"}})
    check("…'improve' asks again (to change the answer)", "train:no" in json.dumps(SENT[n:]), SENT[n:])
    whatsapp._safe({"from": wa, "type": "interactive", "id": "m",
                    "interactive": {"button_reply": {"id": "train:no", "title": "No, thanks"}}})
    check("…No is saved", training.answer(wa) is False)

    # a trader who agreed before this question existed: asked once, after their message is answered
    old = "2348030000633"
    tok = web.ledger.use_book(old)
    whatsapp.user(old)   # the bot's row for this number, then: language chosen and agreed, in September
    whatsapp.set_user(old, lang="English", consent_at="2026-09-01T10:00:00")
    web.ledger._BOOK.reset(tok)
    n = len(SENT)
    whatsapp._safe({"from": old, "type": "text", "id": "m", "text": {"body": "hello"}})
    first = [p for p in SENT[n:] if "train:yes" in json.dumps(p)]
    n = len(SENT)
    whatsapp._safe({"from": old, "type": "text", "id": "m", "text": {"body": "hello"}})
    again = [p for p in SENT[n:] if "train:yes" in json.dumps(p)]
    check("an earlier trader is asked once, after the reply, never again", len(first) == 1 and not again, (first, again))

    page = TestClient(web.app).get("/privacy").text
    check("the privacy notice says what yes keeps and how to turn it off",
          "Helping make TradeVoice better" in page and "We then delete everything we kept" in page)

    print(f"\n{sum(CHECKS)}/{len(CHECKS)} improve-TradeVoice checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
