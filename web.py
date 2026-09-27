"""TradeVoice web app: a phone-style front end (web/) over the same Python brains as the Gradio app.

    python web.py                  -> http://localhost:8000   (old Gradio screens stay at /admin)
    public link on Brev:  cloudflared tunnel --url http://localhost:8000   (see README)

The API only moves data; every number still comes from ledger.py / insights.py, every reply from converse.py.
"""
import datetime as dt
import os
import shutil
import tempfile
import uuid

import settings  # noqa: F401  (loads .env before the other modules read it)
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import converse
import insights
import ledger
import photo
import tts
import ui_text
from extract import TYPES

HERE = os.path.dirname(os.path.abspath(__file__))
SHOP_NAME = os.getenv("SHOP_NAME", "Chioma Stores")
VOICE_LANGS = {"English": "English / Pidgin", "Pidgin": "English / Pidgin", "Yoruba": "Yoruba", "Hausa": "Hausa",
               "Igbo": "Igbo"}

app = FastAPI(title="TradeVoice")
import whatsapp  # noqa: E402  (📲 the WhatsApp bot: same server, same link, same book)

app.include_router(whatsapp.router)
SESSIONS = {}   # browser session id -> conversation state (who "her" is, the draft waiting for "yes")
SPEAK = {}      # speak id -> (text, language) ; audio is made only when the page asks for it
AUDIO = {}      # speak id -> audio file path


def _state(session, lang=None):
    """The chat's memory. `lang` = the language the trader picked; replies use it unless they clearly speak another."""
    st = SESSIONS.setdefault(session or "anon", converse.new_state())
    if lang in VOICE_LANGS:
        st["prefer"] = lang
    return st


def _speak_id(text, lang):
    if not text:
        return None
    sid = uuid.uuid4().hex
    SPEAK[sid] = (text, lang if lang in tts.REPLY_LANGS else "Pidgin")
    return sid


def _upload(file: UploadFile, suffix):
    """Save an upload to our own temp file (deleted right after it is read)."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return path


def _reply_json(r, state, heard=None):
    return {"text": r["text"], "english": r.get("english"), "lang": r["lang"], "heard": heard,
            "message": r.get("message"), "link": r.get("link"), "choices": r.get("choices"),
            "pending": bool(state.get("pending")), "speak": _speak_id(r.get("spoken"), r["lang"])}


# ---------------------------------------------------------------- talk

class Msg(BaseModel):
    session: str = "anon"
    text: str
    shop: str | None = None
    lang: str | None = None


@app.post("/api/message")
def message(m: Msg):
    state = _state(m.session, m.lang)
    r = converse.reply(m.text, state, shop=m.shop or SHOP_NAME)
    return _reply_json(r, state)


@app.post("/api/voice")
def voice(file: UploadFile = File(...), session: str = Form("anon"), lang: str = Form("English"),
          consent: str = Form(""), shop: str = Form("")):
    if consent != "yes":
        raise HTTPException(400, "consent needed")
    path = _upload(file, os.path.splitext(file.filename or "")[1] or ".webm")
    try:
        from asr import transcribe_auto

        heard = transcribe_auto(path, VOICE_LANGS.get(lang, "English / Pidgin"), vocab=ledger.known_words())
    except Exception as e:  # noqa: BLE001
        print(f"hearing failed: {type(e).__name__}: {e}")
        return JSONResponse({"error": "Sorry, I couldn't hear that. Please try again, or type it."}, 502)
    finally:
        os.remove(path)  # the voice note is deleted as soon as it is read
    text = heard["text"].strip()
    if not text:
        return JSONResponse({"error": "I didn't hear anything. Try again, closer to the phone."}, 422)
    state = _state(session, lang)
    out = _reply_json(converse.reply(text, state, shop=shop or SHOP_NAME), state, heard=text)
    out["engine"] = heard.get("engine")
    out["detected"] = heard.get("detected")
    return out


@app.get("/api/speak/{sid}")
def speak(sid: str):
    """The voice note for a reply, made on first request (so the text shows without waiting for the voice)."""
    if sid not in AUDIO:
        if sid not in SPEAK:
            raise HTTPException(404)
        text, lang = SPEAK[sid]
        out = tts.speak(text, lang)
        if not out:
            raise HTTPException(404, "voice is off")
        AUDIO[sid] = out["path"]
    return FileResponse(AUDIO[sid], media_type="audio/wav")


# ---------------------------------------------------------------- photo of the book

@app.post("/api/photo")
def photo_api(file: UploadFile = File(...), consent: str = Form("")):
    if consent != "yes":
        raise HTTPException(400, "consent needed")
    path = _upload(file, os.path.splitext(file.filename or "")[1] or ".jpg")
    try:
        return photo.read(path)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Could not read the photo ({type(e).__name__}: {str(e)[:100]})."}, 502)
    finally:
        os.remove(path)  # the photo is deleted as soon as it is read


class Rows(BaseModel):
    rows: list[dict]


@app.post("/api/save_rows")
def save_rows(body: Rows):
    return photo.save(body.rows)


# ---------------------------------------------------------------- customers + their conversations

def _customer_or_404(cid):
    c = ledger.customer_summary(cid)
    if not c:
        raise HTTPException(404, "customer not found (it may have been deleted)")
    return c


@app.get("/api/customers")
def customers():
    rows = ledger.conversations()
    names = {}
    for r in rows:
        names[ledger.customer_key(r["name"])] = names.get(ledger.customer_key(r["name"]), 0) + 1
    for r in rows:
        r["same_name"] = names[ledger.customer_key(r["name"])] > 1
    return {"customers": rows}


class NewCustomer(BaseModel):
    name: str
    phone: str | None = None
    notes: str | None = None


@app.post("/api/customers")
def new_customer(c: NewCustomer):
    if not c.name.strip():
        raise HTTPException(400, "name needed")
    return ledger.customer_summary(ledger.create_customer(c.name, c.phone, c.notes))


@app.get("/api/customers/{cid}")
def customer(cid: int):
    return {"customer": _customer_or_404(cid), "thread": ledger.thread(cid)}


class CustomerEdit(BaseModel):
    name: str | None = None
    phone: str | None = None
    notes: str | None = None


@app.patch("/api/customers/{cid}")
def edit_customer(cid: int, e: CustomerEdit):
    _customer_or_404(cid)
    ledger.update_customer(cid, **{k: v for k, v in e.model_dump().items() if v is not None})
    return ledger.customer_summary(cid)


@app.delete("/api/customers/{cid}")
def remove_customer(cid: int):
    return {"deleted": bool(ledger.delete_customer(cid))}


@app.post("/api/customers/{cid}/read")
def mark_read(cid: int):
    _customer_or_404(cid)
    ledger.update_customer(cid, last_read_at=ledger._now())
    return {"ok": True}


class CustRecord(BaseModel):
    type: str
    amount: float
    item: str | None = None
    due_date: str | None = None
    raw_text: str | None = None


@app.post("/api/customers/{cid}/record")
def customer_record(cid: int, r: CustRecord):
    """Record a sale / payment for THIS customer (by id). Balances update everywhere at once."""
    _customer_or_404(cid)
    if r.type not in TYPES or r.amount <= 0:
        raise HTTPException(400, "needs a type and an amount")
    ledger.add_entry({"type": r.type, "amount": r.amount, "item": (r.item or "").strip() or None,
                      "due_date": r.due_date or None, "customer_id": cid}, raw_text=r.raw_text or "", engine="customer")
    return {"customer": ledger.customer_summary(cid), "thread": ledger.thread(cid)}


class CustSay(BaseModel):
    text: str


@app.post("/api/customers/{cid}/say")
def customer_say(cid: int, m: CustSay):
    """Typed in a customer's conversation: something with money ("paid 10k") -> a draft to confirm;
    anything else -> saved as a note."""
    cust = _customer_or_404(cid)
    from extract import extract, parse_amount

    if parse_amount(m.text) is not None:
        import re

        from extract import fold

        rec, meta = extract(f"{cust['name']} {m.text}")
        t = fold(m.text)
        # inside THIS customer's conversation, "paid 5k" means they paid me; "I paid 5k" means I paid them back
        if re.search(r"\b(i|we)\s+(don\s+|have\s+)?(paid|pay|settle|settled|cleared)\b", t):
            rec["type"] = "payment_made"
        elif re.search(r"\b(paid|pay|pays|don pay|settle|settled|cleared|brought|bring|collect|collected|received|receive|ti san|biya|kwuru|kwuola)\b", t):
            rec["type"] = "payment_received"
        elif re.search(r"\b(owe|credit|go pay|will pay|later)\b", t) and rec["type"] == "sale":
            rec["type"] = "credit_sale"
        return {"draft": {k: rec.get(k) for k in ("type", "amount", "item", "due_date")}, "engine": meta["engine"]}
    ledger.add_message(cid, m.text.strip(), sender="trader", kind="note")
    return {"thread": ledger.thread(cid)}


class Remind(BaseModel):
    lang: str = "Pidgin"
    shop: str | None = None


@app.post("/api/customers/{cid}/reminder")
def customer_reminder(cid: int, b: Remind):
    """TradeVoice drafts the reminder; the trader edits it and sends it from their own WhatsApp."""
    cust = _customer_or_404(cid)
    msg, link = insights.reminder(cust["name"], b.lang if b.lang in insights.TEMPLATES else "Pidgin",
                                  b.shop or SHOP_NAME, customer_id=cid)
    if not msg:
        return {"message": None}
    mid = ledger.add_message(cid, msg, sender="tradevoice", kind="reminder", status="draft")
    return {"message": msg, "link": link, "id": mid, "phone": cust.get("phone"), "thread": ledger.thread(cid)}


class MsgEdit(BaseModel):
    content: str | None = None
    status: str | None = None


@app.patch("/api/messages/{mid}")
def edit_message(mid: int, e: MsgEdit):
    ledger.set_message(mid, **{k: v for k, v in e.model_dump().items() if v is not None})
    return {"ok": True}


# ---------------------------------------------------------------- screens

@app.get("/api/today")
def today():
    return {"summary": ledger.day_summary(), "due": ledger.reminders(due_only=True),
            "entries": [{k: r[k] for k in ("id", "created_at", "type", "item", "quantity", "unit", "amount",
                                           "customer", "due_date")} for r in ledger.entries(limit=30)]}


@app.get("/api/debts")
def debts():
    keep = ("customer", "balance", "due_date", "overdue", "days_late", "items")
    return {"owed_to_me": [{k: d.get(k) for k in keep} for d in ledger.debtors()],
            "i_owe": [{k: d.get(k) for k in keep} for d in ledger.creditors()],
            "reminders": ledger.reminders()}


@app.get("/api/reminder")
def reminder(customer: str, lang: str = "Pidgin", shop: str = ""):
    msg, link = insights.reminder(customer, lang if lang in insights.TEMPLATES else "Pidgin", shop or SHOP_NAME)
    return {"message": msg, "link": link}


@app.get("/api/insights")
def insights_api():
    return {"forecast": insights.forecast(), "top": insights.top_items()}


@app.get("/api/profile")
def profile():
    p = ledger.credit_profile()
    if p:
        p = dict(p, parts=[{"name": k, "points": v[0], "max": v[1], "why": v[2]} for k, v in p["parts"].items()])
    return {"profile": p, "year": insights.year_record_text()}


@app.get("/api/statement", response_class=HTMLResponse)
def statement(shop: str = ""):
    page = insights.statement_html(shop or SHOP_NAME)
    if not page:
        raise HTTPException(404, "no records yet")
    return HTMLResponse(page, headers={"Content-Disposition":
                                       f'attachment; filename="business-statement-{dt.date.today()}.html"'})


@app.get("/api/read/{screen}")
def read(screen: str, lang: str = "English"):
    import readaloud

    if screen not in readaloud.SCREENS:
        raise HTTPException(404)
    lang = lang if lang in readaloud.LANGS else "English"
    text = readaloud.text(screen, lang)
    return {"text": text, "speak": _speak_id(text, lang)}


@app.get("/api/read/{screen}/audio")
def read_audio(screen: str, lang: str = "English"):
    """The screen as a voice note, as a plain audio URL: the page can start it straight from the tap
    (phones, iPhone Safari especially, block sound that starts after a wait)."""
    import readaloud

    if screen not in readaloud.SCREENS:
        raise HTTPException(404)
    lang = lang if lang in readaloud.LANGS else "English"
    out = tts.speak(readaloud.text(screen, lang), lang if lang in tts.REPLY_LANGS else "Pidgin")
    if not out:
        raise HTTPException(404, "voice is off")
    return FileResponse(out["path"], media_type="audio/wav")


# ---------------------------------------------------------------- 🎙️ Ask TradeVoice (voice assistant on every screen)

@app.get("/api/explain/{screen}")
def explain(screen: str, lang: str = "English"):
    import assistant

    e = assistant.explain(screen, lang)
    return {"text": e["text"], "engine": e["engine"], "speak": _speak_id(e.get("spoken") or e["text"], lang)}


@app.get("/api/explain/{screen}/audio")
def explain_audio(screen: str, lang: str = "English"):
    """The explanation as a plain audio URL, so the sound can start inside the tap that opened the assistant."""
    import assistant

    e = assistant.explain(screen, lang)
    out = tts.speak(e.get("spoken") or e["text"], lang if lang in tts.REPLY_LANGS else "Pidgin")
    if not out:
        raise HTTPException(404, "voice is off")
    return FileResponse(out["path"], media_type="audio/wav")


@app.post("/api/assist")
def assist(screen: str = Form("today"), lang: str = Form("English"), session: str = Form("anon"),
           text: str = Form(""), speak_lang: str = Form("English"), consent: str = Form(""),
           shop: str = Form(""), file: UploadFile | None = File(None)):
    """A question by voice (file) or typed (text) about the screen the trader is on; answered in their language."""
    import assistant

    heard, detected = text.strip(), None
    if file is not None:
        if consent != "yes":
            raise HTTPException(400, "consent needed")
        path = _upload(file, os.path.splitext(file.filename or "")[1] or ".webm")
        try:
            from asr import transcribe_auto

            h = transcribe_auto(path, VOICE_LANGS.get(speak_lang, "English / Pidgin"), vocab=ledger.known_words())
            heard, detected = h["text"].strip(), h.get("detected")
        except Exception as e:  # noqa: BLE001
            print(f"hearing failed: {type(e).__name__}: {e}")
            return JSONResponse({"error": "Sorry, I couldn't hear that. Please try again, or type it."}, 502)
        finally:
            os.remove(path)  # the voice note is deleted as soon as it is read
    if not heard:
        return JSONResponse({"error": "I didn't hear anything. Try again, closer to the phone."}, 422)
    state = _state(session, lang)
    r = assistant.answer(heard, screen, lang, state=state, shop=shop or SHOP_NAME)
    return {"heard": heard, "detected": detected, "text": r["text"], "english": r.get("english"),
            "lang": r.get("lang", lang), "engine": r.get("engine"), "message": r.get("message"), "link": r.get("link"),
            "pending": bool(state.get("pending")), "choices": r.get("choices"),
            "speak": _speak_id(r.get("spoken") or r["text"], r.get("lang", lang))}


@app.delete("/api/entry/{entry_id}")
def delete(entry_id: int):
    return {"deleted": bool(ledger.delete_entry(entry_id))}


class Wipe(BaseModel):
    confirm: str


@app.post("/api/wipe")
def wipe(w: Wipe):
    if w.confirm != "DELETE":
        raise HTTPException(400, "type DELETE")
    SESSIONS.clear()
    return {"deleted": ledger.wipe()}


@app.get("/api/ui")
def ui(lang: str = "English"):
    return {k: ui_text.t(k, lang) for k in ui_text.UI} | {"_langs": ui_text.LANGS,
                                                          "_dir": ui_text.DIRECTION.get(lang, "ltr"),
                                                          "_code": ui_text.CODES.get(lang, "en")}


@app.get("/api/status")
def status():
    import llm

    hearing = os.getenv("ASR_ENGINE") or ("intron" if os.getenv("INTRON_API_KEY") else "local")
    return {"hearing": hearing, "voice": tts.backend(),
            "brain": "brev" if os.getenv("LOCAL_LLM_URL") else ("nvidia" if os.getenv("NVIDIA_API_KEY") else "offline"),
            "photos": "brev" if os.getenv("LOCAL_VISION_URL") else ("nvidia" if llm.available("vision") else "off"),
            "shop": SHOP_NAME, "whatsapp": bool(os.getenv("WHATSAPP_TOKEN") and (os.getenv("WHATSAPP_PHONE_ID")
                                                               or os.getenv("WHATSAPP_PHONE_NUMBER_ID")))}


# ---------------------------------------------------------------- pages

app.mount("/static", StaticFiles(directory=os.path.join(HERE, "web")), name="static")


@app.get("/")
def landing():
    return FileResponse(os.path.join(HERE, "web", "landing.html"))


@app.get("/app")
def index():
    return FileResponse(os.path.join(HERE, "web", "index.html"))


if os.getenv("TRADEVOICE_ADMIN", "1") == "1":  # the old Gradio screens, as a backup, at /admin
    try:
        import gradio as gr

        from app import demo

        app = gr.mount_gradio_app(app, demo, path="/admin")
    except Exception as e:  # noqa: BLE001
        print(f"/admin not mounted: {type(e).__name__}: {e}")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
