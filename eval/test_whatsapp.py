"""WhatsApp bot without Meta: fake incoming webhooks, capture what the bot would send. No keys needed.

python eval/test_whatsapp.py
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import tempfile

os.environ["TV_NO_DOTENV"] = "1"  # never let the real .env keys into a test
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["BOOKS_DIR"] = tempfile.mkdtemp()
os.environ["ACCOUNTS_DB"] = os.path.join(tempfile.mkdtemp(), "a.db")
for k in list(os.environ):
    if k.endswith("API_KEY") or k.startswith("LOCAL_") or k.startswith("WHATSAPP_"):
        os.environ.pop(k)
os.environ.update(WHATSAPP_TOKEN="test", WHATSAPP_PHONE_ID="123", WHATSAPP_VERIFY_TOKEN="tv-verify",
                  WHATSAPP_APP_SECRET="s3cret", TRADEVOICE_ADMIN="0")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastapi.testclient import TestClient  # noqa: E402

import ledger  # noqa: E402
import web  # noqa: E402
import whatsapp  # noqa: E402

SENT = []
whatsapp.graph_post = lambda p: SENT.append(p) or {"messages": [{"id": "x"}]}
whatsapp.send_voice = lambda to, text, lang: SENT.append({"voice": text, "lang": lang})
whatsapp.download = lambda media_id, suffix: tempfile.mkstemp(suffix=suffix)[1]
import asr  # noqa: E402
import vision  # noqa: E402

HEARD = {"v1": "Mama Tunde dey owe me forty-five thousand"}
asr.transcribe = lambda path, lang, vocab=None: {"text": HEARD[os.environ["_VOICE"]], "engine": "fake"}
vision.read_notebook = lambda path: {"text": "Iya Bisi paid 15k\nOga Emeka owe 4?,000\nTransport 2000",
                                     "latency_ms": 5, "engine": "fake-vision"}
client = TestClient(web.app)
PHONE = "2348000000001"
n = 0
ALL = []


def post(msg):
    global n
    n += 1
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"from": PHONE, "id": f"m{n}", **msg}]}}]}]})
    sig = "sha256=" + hmac.new(b"s3cret", body.encode(), hashlib.sha256).hexdigest()
    SENT.clear()
    r = client.post("/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": sig,
                                                                "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    ALL.extend(SENT)
    return [s for s in SENT if s.get("status") != "read"]


def text_of(out):
    parts = []
    for s in out:
        if "voice" in s:
            parts.append(f"[🔊 {s['lang']}] {s['voice']}")
        elif s.get("type") == "text":
            parts.append(s["text"]["body"])
        elif s.get("type") == "interactive":
            i = s["interactive"]
            btns = [b["reply"]["title"] for b in i["action"].get("buttons", [])] or \
                   [r["title"] for r in i["action"]["sections"][0]["rows"]]
            parts.append(f"{i['body']['text']}  {btns}")
    return "\n".join(parts)


CHECKS = []


def check(name, ok, out=""):
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {out[:400]}"))


def main():
    ledger.use_book(PHONE)  # the WhatsApp sender's own book (same one the web app opens after login)
    ledger.add_entry({"type": "credit_sale", "item": "rice", "amount": 30000, "customer": "Mama Tunde"},
                     created_at=dt.datetime(2026, 9, 20, 10))
    ledger.add_entry({"type": "credit_purchase", "item": "rice", "amount": 60000, "customer": "Alhaji Sani"},
                     created_at=dt.datetime(2026, 9, 21, 10))
    ledger.add_entry({"type": "credit_sale", "item": "garri", "amount": 8000, "customer": "Iya Bisi"},
                     created_at=dt.datetime(2026, 9, 22, 10))

    r = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "tv-verify",
                                                "hub.challenge": "12345"})
    check("Meta verify handshake answers the challenge", r.status_code == 200 and r.text == "12345", r.text)
    bad = client.post("/whatsapp/webhook", content=b"{}", headers={"X-Hub-Signature-256": "sha256=nope"})
    check("fake (unsigned) messages are refused", bad.status_code == 401)

    out = text_of(post({"type": "text", "text": {"body": "hi"}}))
    check("first message → language list (4 N-ATLaS languages, no Pidgin)", "Which language" in out
          and "Yorùbá" in out and "Pidgin" not in out, out)
    out = text_of(post({"type": "interactive", "interactive": {"type": "list_reply",
                                                                "list_reply": {"id": "lang:Pidgin"}}}))
    check("an old 'Pidgin' button → English, consent with 'Agree' button", "Agree and continue" in out, out)
    out = text_of(post({"type": "audio", "audio": {"id": "a1"}}))
    check("no processing before consent", "Agree and continue" in out and "Mama Tunde" not in out, out)
    out = text_of(post({"type": "interactive", "interactive": {"type": "button_reply",
                                                                "button_reply": {"id": "consent:yes"}}}))
    check("agreed → hello", "Hello" in out, out)

    os.environ["_VOICE"] = "v1"
    out = text_of(post({"type": "audio", "audio": {"id": "a2", "voice": True}}))
    check("voice note → transcript + draft + Yes/No buttons + voice reply",
          "Mama Tunde dey owe me" in out and "₦45,000" in out and "Yes, save" in out and "[🔊" in out, out)
    out = text_of(post({"type": "interactive", "interactive": {"type": "button_reply",
                                                                "button_reply": {"id": "yes"}}}))
    check("✅ tapped → saved, new total ₦75,000", "₦75,000" in out, out)
    out = text_of(post({"type": "text", "text": {"body": "Ṣé mo ní gbèsè lọ́wọ́ Alhaji?"}}))
    check("typed Yoruba question → Yoruba answer as TEXT only (voice only after a voice note: saves Intron credit)",
          "O jẹ Alhaji Sani ní ₦60,000" in out and "[🔊" not in out, out)
    os.environ["VOICE_REPLIES"] = "always"
    out = text_of(post({"type": "text", "text": {"body": "Ṣé mo ní gbèsè lọ́wọ́ Alhaji?"}}))
    check("VOICE_REPLIES=always → Yoruba answer + Yoruba voice", "[🔊 Yoruba]" in out, out)
    os.environ.pop("VOICE_REPLIES")
    out = text_of(post({"type": "text", "text": {"body": "Remind her tomorrow"}}))
    # they wrote Yoruba above, so the chat is now in Yoruba: the reminder comes in Yoruba too
    check("'Remind her' → Mama Tunde + message to forward (Yoruba)", "Mama Tunde" in out and "Forward this" in out
          and "Ẹ káàárọ̀ Mama Tunde" in out, out)

    out = text_of(post({"type": "image", "image": {"id": "i1"}}))
    check("photo → numbered lines + Save/Cancel", "1." in out and "2." in out and "Save ticked" in out, out)
    out = text_of(post({"type": "text", "text": {"body": "2 = 40k"}}))
    check("'2 = 40k' fixes line 2", "₦40,000" in out, out)
    before = len(ledger.entries(limit=100))
    out = text_of(post({"type": "interactive", "interactive": {"type": "button_reply",
                                                                "button_reply": {"id": "p_save"}}}))
    check("Save ticked → saved to the same book as the web app",
          "Saved" in out and len(ledger.entries(limit=100)) > before, out)

    out = text_of(post({"type": "text", "text": {"body": "voice off"}}))
    out = text_of(post({"type": "text", "text": {"body": "Who owes me?"}}))
    check("voice off → text only", "[🔊" not in out and "owes you" in out, out)
    dup = {"type": "text", "text": {"body": "Who owes me?"}}
    post(dup)
    global n
    n -= 1  # same message id again (Meta retry)
    check("duplicate delivery is ignored", post(dup) == [])
    check("no 'Something went wrong' after normal messages", not any("went wrong" in json.dumps(x) for x in ALL),
          [x for x in ALL if "went wrong" in json.dumps(x)][:2])
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} WhatsApp checks pass")
    return len(CHECKS) - sum(CHECKS)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
