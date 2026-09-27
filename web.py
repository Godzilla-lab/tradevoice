"""TradeVoice web app: a phone-style front end (web/) over the same Python brains as the Gradio app.

    python web.py                  -> http://localhost:8000   (old Gradio screens stay at /admin)
    public link on Brev:  cloudflared tunnel --url http://localhost:8000   (see README)

The API only moves data; every number still comes from ledger.py / insights.py, every reply from converse.py.
"""
import datetime as dt
import os
import re
import shutil
import tempfile
import urllib.parse
import uuid

import settings  # noqa: F401  (loads .env before the other modules read it)
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import accounts
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
import extras  # noqa: E402  (lender link, pay links, automatic reminders, receipts, PIN, CSV)

app.include_router(extras.router)
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "1") == "1"  # AUTH_REQUIRED=0: no login, one shared book (old demo)
OPEN_API = ("/api/auth/", "/api/ui", "/api/status", "/api/voice_check")
PIN_FREE = ("/api/auth/", "/api/ui", "/api/status")
COOKIE = "tv_auth"


class BookPerTrader:
    """Every request works on the logged-in trader's own book (books/<number>.db). Not logged in -> 401 for the API."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
        cookies = {}
        for k, v in scope.get("headers", []):
            if k == b"cookie":
                for part in v.decode("latin-1").split(";"):
                    name, _, val = part.strip().partition("=")
                    cookies[name] = val
        phone = accounts.phone_for(cookies.get(COOKIE))
        path = scope.get("path", "")
        if (AUTH_REQUIRED and not phone and path.startswith("/api/") and not path.startswith(OPEN_API)):
            return await JSONResponse({"error": "Please log in with your phone number.", "login": True}, 401)(
                scope, receive, send)
        if phone and path.startswith("/api/") and not path.startswith(PIN_FREE) and extras.has_pin(phone):
            unlock = dict(scope.get("headers", [])).get(b"x-tv-unlock", b"").decode()
            if not extras.unlocked(phone, unlock):
                return await JSONResponse({"error": "Enter your PIN.", "locked": True}, 423)(scope, receive, send)
        scope.setdefault("state", {})["phone"] = phone
        token = ledger.use_book(phone) if phone else None
        try:
            await self.inner(scope, receive, send)
        finally:
            if token:
                ledger.done_with_book(token)


app.add_middleware(BookPerTrader)
SESSIONS = {}   # (book, browser session id) -> conversation state (who "her" is, the draft waiting for "yes")
SPEAK = {}      # speak id -> (text, language) ; audio is made only when the page asks for it
AUDIO = {}      # speak id -> audio file path


def _state(session, lang=None):
    """The chat's memory. `lang` = the language the trader picked; replies use it unless they clearly speak another."""
    st = SESSIONS.setdefault((ledger.book_path(), session or "anon"), converse.new_state())
    if lang in VOICE_LANGS:
        st["prefer"] = lang
    return st


def _lang_of(request):
    """The logged-in trader's language (English if unknown)."""
    phone = request.scope.get("state", {}).get("phone")
    lang = accounts.profile(phone).get("lang") if phone else None
    return lang if lang in VOICE_LANGS else "English"


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


def _draft(state):
    """What is waiting for "yes", as fields for the confirmation card. `unsure` names the fields TradeVoice is not
    sure about (so the card shows a "?" and asks), `new_customer` says the name isn't in the book yet."""
    rec = state.get("pending")
    if not rec or state.get("choose"):
        return None
    unsure = []
    if rec.get("amount") in (None, ""):
        unsure.append("amount")
    if (rec.get("confidence") or 0) < 0.5 and rec.get("amount") not in (None, ""):
        unsure.append("type")
    if rec.get("type") in ("credit_sale", "payment_received", "credit_purchase", "payment_made") and not rec.get("customer"):
        unsure.append("customer")  # a debt needs a person
    if rec.get("type") in ("credit_sale", "credit_purchase") and not rec.get("due_date"):
        unsure.append("due_date")
    known = bool(rec.get("customer_id")) or bool(rec.get("customer") and ledger.find_customers(rec["customer"]))
    return {"type": rec.get("type"), "amount": rec.get("amount"), "customer": rec.get("customer"),
            "new_customer": bool(rec.get("customer")) and not known, "item": rec.get("item"),
            "quantity": rec.get("quantity"), "unit": rec.get("unit"), "due_date": rec.get("due_date"),
            "note": converse.friendly_note(rec.get("note"), state.get("lang") or "English"), "unsure": unsure,
            "limit": converse.draft_limit(rec)}


def _reply_json(r, state, heard=None):
    return {"text": r["text"], "english": r.get("english"), "lang": r["lang"], "heard": heard,
            "message": r.get("message"), "link": r.get("link"), "choices": r.get("choices"),
            "pending": bool(state.get("pending")), "draft": _draft(state),
            "speak": _speak_id(r.get("spoken"), r["lang"])}


class DraftEdit(BaseModel):
    session: str = "anon"
    lang: str | None = None
    type: str | None = None
    amount: float | None = None
    customer: str | None = None
    item: str | None = None
    quantity: float | None = None
    unit: str | None = None
    due_date: str | None = None


@app.post("/api/draft")
def draft_edit(b: DraftEdit):
    """"Change" on the confirmation card: the trader fixes what TradeVoice understood, then saves with Yes."""
    state = _state(b.session, b.lang)
    rec = state.get("pending")
    if not rec:
        raise HTTPException(400, "There is nothing waiting to be saved.")
    if b.type is not None and b.type not in TYPES:
        raise HTTPException(400, "Unknown record type.")
    if b.amount is not None and b.amount <= 0:
        raise HTTPException(400, "The amount must be more than ₦0.")
    if b.due_date:
        try:
            dt.date.fromisoformat(b.due_date)
        except ValueError:
            raise HTTPException(400, "Use a date like 2026-10-02.")
    for k in ("type", "amount", "item", "quantity", "unit", "due_date"):
        v = getattr(b, k)
        if v is not None:
            rec[k] = (v.strip() or None) if isinstance(v, str) else v
    if b.customer is not None and (b.customer.strip() or None) != rec.get("customer"):
        rec["customer"], rec["customer_id"] = b.customer.strip() or None, None
    rec["confidence"], rec["note"] = 1.0, None  # the trader checked it
    lang = state.get("lang") or "English"
    heard = converse._heard(rec, lang)
    return _reply_json(heard, state)


# ---------------------------------------------------------------- talk

class Msg(BaseModel):
    session: str = "anon"
    text: str
    shop: str | None = None
    lang: str | None = None


@app.post("/api/message")
def message(m: Msg):
    state = _state(m.session, m.lang)
    return _reply_json(_safe_reply(m.text, state, m.shop, m.lang), state)


def _safe_reply(text, state, shop, lang):
    """The chat never answers with a bare error: log it and say something useful instead."""
    try:
        return converse.reply(text, state, shop=shop or SHOP_NAME)
    except Exception as e:  # noqa: BLE001
        print(f"chat reply failed for {text!r}: {type(e).__name__}: {e}")
        import ui_text

        lang = lang if lang in ui_text.LANGS else "English"
        return {"text": ui_text.t("hello", lang), "spoken": ui_text.t("hello", lang), "lang": lang}


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
    out = _reply_json(_safe_reply(text, state, shop, lang), state, heard=text)
    out["engine"] = heard.get("engine")
    out["detected"] = heard.get("detected")
    return out


@app.get("/api/voice_check")
def voice_check(lang: str = "Yoruba", fmt: str = "wav"):
    """Open /api/voice_check?lang=Yoruba in a browser: says whether the voice works, and the error if not."""
    samples = {"English": "Hello, I am your book.", "Pidgin": "Hello, na me be your book.",
               "Yoruba": "Ẹ n lẹ́ o. Èmi ni ìwé rẹ.", "Hausa": "Sannu. Ni ne littafinka.", "Igbo": "Ndewo. Abụ m akwụkwọ gị."}
    try:
        text = samples.get(lang, samples["English"])
        if fmt == "ogg_opus":  # exactly what the WhatsApp bot sends (fmt=ogg_opus tests the voice-note path)
            path = whatsapp.voice_file(text, lang)
            if not path:
                return {"lang": lang, "ok": False, "error": "no voice set up: SPITCH_API_KEY missing or spitch not installed"}
            size = os.path.getsize(path)
            os.remove(path)
            return {"lang": lang, "ok": True, "format": "ogg (WhatsApp voice note)", "bytes": size}
        out = tts.speak(text, lang if lang in tts.REPLY_LANGS else "English")
        if not out:
            return {"lang": lang, "ok": False, "error": "no voice set up: SPITCH_API_KEY missing or spitch not installed"}
        return {"lang": lang, "ok": True, "engine": out["engine"], "bytes": os.path.getsize(out["path"])}
    except Exception as e:  # noqa: BLE001
        return {"lang": lang, "ok": False, "error": f"{type(e).__name__}: {e}"[:500]}


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
    credit_limit: float | None = None


@app.post("/api/customers")
def new_customer(c: NewCustomer):
    if not c.name.strip():
        raise HTTPException(400, "name needed")
    cid = ledger.create_customer(c.name, c.phone, c.notes)
    if c.credit_limit and c.credit_limit > 0:
        ledger.update_customer(cid, credit_limit=c.credit_limit)
    return ledger.customer_summary(cid)


@app.get("/api/customers/{cid}")
def customer(cid: int):
    return {"customer": _customer_or_404(cid), "thread": ledger.thread(cid)}


class CustomerEdit(BaseModel):
    name: str | None = None
    phone: str | None = None
    notes: str | None = None
    credit_limit: float | None = None   # 0 = remove the limit


@app.patch("/api/customers/{cid}")
def edit_customer(cid: int, e: CustomerEdit):
    _customer_or_404(cid)
    fields = {k: v for k, v in e.model_dump().items() if v is not None}
    if "credit_limit" in fields:
        if fields["credit_limit"] < 0:
            raise HTTPException(400, "The limit can't be below ₦0.")
        fields["credit_limit"] = fields["credit_limit"] or None
    ledger.update_customer(cid, **fields)
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
    over_limit_ok: bool = False   # the trader saw the limit warning and chose "Sell anyway"


@app.post("/api/customers/{cid}/record")
def customer_record(cid: int, r: CustRecord, request: Request):
    """Record a sale / payment for THIS customer (by id). Balances update everywhere at once.
    Then a receipt, ready to send to the customer on WhatsApp."""
    _customer_or_404(cid)
    if r.type not in TYPES or r.amount <= 0:
        raise HTTPException(400, "needs a type and an amount")
    if r.type == "credit_sale" and not r.over_limit_ok:
        lim = ledger.limit_check(cid, r.amount)
        if lim and lim["over"]:  # ask first: "Sell anyway?"
            return JSONResponse({"over_limit": lim, "warning": converse.over_limit_text(lim, _lang_of(request))}, 409)
    ledger.add_entry({"type": r.type, "amount": r.amount, "item": (r.item or "").strip() or None,
                      "due_date": r.due_date or None, "customer_id": cid}, raw_text=r.raw_text or "", engine="customer")
    phone = request.scope["state"].get("phone")
    prof = accounts.profile(phone) if phone else {}
    rc = extras.receipt(cid, r.type, r.amount, (r.item or "").strip(), r.due_date, prof.get("shop") or SHOP_NAME,
                        prof.get("lang") or "English")
    if rc:
        ledger.add_message(cid, rc, sender="tradevoice", kind="receipt", status="draft")
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
def customer_reminder(cid: int, b: Remind, request: Request):
    """TradeVoice drafts the reminder (with a pay link); the trader edits it and sends it from their own WhatsApp."""
    cust = _customer_or_404(cid)
    msg, link = insights.reminder(cust["name"], b.lang if b.lang in insights.TEMPLATES else "Pidgin",
                                  b.shop or SHOP_NAME, customer_id=cid)
    if not msg:
        return {"message": None}
    msg = extras.reminder_with_paylink(extras._base(request), request.scope["state"].get("phone"), cid, msg)
    link = link.split("?text=")[0] + "?text=" + urllib.parse.quote(msg)
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
def reminder(customer: str, request: Request, lang: str = "Pidgin", shop: str = ""):
    msg, link = insights.reminder(customer, lang if lang in insights.TEMPLATES else "Pidgin", shop or SHOP_NAME)
    d = next((x for x in ledger.debtors() if ledger.customer_key(x["customer"]) == ledger.customer_key(customer)), None)
    if msg and d and d.get("customer_id"):
        msg = extras.reminder_with_paylink(extras._base(request), request.scope["state"].get("phone"), d["customer_id"], msg)
        link = link.split("?text=")[0] + "?text=" + urllib.parse.quote(msg)
    return {"message": msg, "link": link}


@app.get("/api/repeats")
def repeats():
    """Today's usual orders not recorded yet (suggestions: the trader confirms)."""
    return {"repeats": insights.repeat_orders()}


class RepeatPick(BaseModel):
    session: str = "anon"
    lang: str | None = None
    customer_id: int
    item: str


@app.post("/api/repeats/draft")
def repeat_draft(b: RepeatPick):
    """Tap "Record it": the usual order becomes a draft on the confirmation card (nothing saved yet)."""
    state = _state(b.session, b.lang)
    p = next((x for x in insights.repeat_orders(only_today=False)
              if x["customer_id"] == b.customer_id and x["item"].lower() == b.item.lower()), None)
    if not p:
        raise HTTPException(404, "That usual order isn't there any more.")
    lang = b.lang if b.lang in VOICE_LANGS else "English"
    state["lang"] = lang
    return _reply_json(converse.draft_repeat(state, p, lang), state)


@app.get("/api/insights")
def insights_api():
    return {"forecast": insights.forecast(), "top": insights.top_items(), "margins": insights.margins(),
            "suppliers": insights.suppliers()}


@app.get("/api/profile")
def profile(lang: str = "English"):
    p = ledger.credit_profile()
    if p:
        p = dict(p, parts=[{"name": k, "points": v[0], "max": v[1], "why": v[2]} for k, v in p["parts"].items()])
    import tax

    return {"profile": p, "year": insights.year_record_text(), "year_data": insights.year_data(),
            "tax": {"facts": tax.facts(lang), "check": tax.check(lang)}}


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
    for k in [k for k in SESSIONS if k[0] == ledger.book_path()]:
        SESSIONS.pop(k)
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
                                                               or os.getenv("WHATSAPP_PHONE_NUMBER_ID"))),
            "whatsapp_seen": whatsapp.STATS}


# ---------------------------------------------------------------- 🔐 log in with your phone number

class Start(BaseModel):
    phone: str
    lang: str | None = None


class Code(BaseModel):
    login_id: str
    code: str = ""


class Me(BaseModel):
    name: str | None = None
    shop: str | None = None
    lang: str | None = None


def _logged_in(request: Request, phone):
    token = accounts.new_session(phone)
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    r = JSONResponse({"ok": True, "me": _me(phone)})
    r.set_cookie(COOKIE, token, max_age=accounts.SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=secure)
    return r


def _me(phone):
    p = accounts.profile(phone)
    token = ledger.use_book(phone)
    try:
        empty = ledger.is_empty()
    finally:
        ledger.done_with_book(token)
    return {"phone": accounts.masked(phone), "name": p.get("name") or "", "shop": p.get("shop") or "",
            "lang": p.get("lang") or "", "new": not p.get("shop"), "empty_book": empty, "has_pin": extras.has_pin(phone)}


@app.post("/api/auth/start")
def auth_start(b: Start):
    phone = accounts.normalize(b.phone)
    if not phone:
        raise HTTPException(400, "That doesn't look like a phone number. Try like 0803 123 4567.")
    login = accounts.start(phone)
    sent = False
    if not accounts.demo_mode():
        try:
            words = {"Pidgin": "Your TradeVoice code na", "Yoruba": "Kóòdù TradeVoice rẹ ni",
                     "Hausa": "Lambar TradeVoice ɗinka ita ce", "Igbo": "Koodu TradeVoice gị bụ"}
            whatsapp.send_text(phone, f"🔐 {words.get(b.lang, 'Your TradeVoice code is')} *{login['code']}*\n"
                                      "Don't share it with anyone.")
            sent = True
        except Exception as e:  # noqa: BLE001 - expired token, or Meta's 24-hour rule
            print(f"login code not sent by WhatsApp: {e}")
    bot = whatsapp.bot_number()
    # never a dead end: if WhatsApp couldn't deliver the code, show it on screen (AUTH_STRICT=1 turns this off)
    fallback = not sent and not accounts.demo_mode() and os.getenv("AUTH_STRICT") != "1"
    return {"login_id": login["id"], "phone": accounts.masked(phone), "sent": sent,
            "word": login["word"], "verify_link": f"https://wa.me/{bot}?text=LOGIN%20{login['word']}" if bot else None,
            "demo_code": login["code"] if accounts.demo_mode() or fallback else None,
            "fallback": fallback}


@app.post("/api/auth/verify")
def auth_verify(b: Code, request: Request):
    phone, why = accounts.check_code(b.login_id, b.code)
    if not phone:
        raise HTTPException(400, why)
    return _logged_in(request, phone)


@app.post("/api/auth/poll")
def auth_poll(b: Code, request: Request):
    phone = accounts.poll(b.login_id)
    return _logged_in(request, phone) if phone else {"ok": False}


@app.get("/api/auth/me")
def auth_me(request: Request):
    phone = request.scope["state"].get("phone")
    if not phone:
        return JSONResponse({"login": True}, 401)
    return _me(phone)


@app.post("/api/auth/me")
def auth_update(b: Me, request: Request):
    phone = request.scope["state"].get("phone")
    if not phone:
        return JSONResponse({"login": True}, 401)
    accounts.update_profile(phone, name=b.name, shop=b.shop, lang=b.lang)
    return _me(phone)


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    accounts.end_session(request.cookies.get(COOKIE))
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE)
    return r


@app.post("/api/auth/delete")
def auth_delete(w: Code, request: Request):
    phone = request.scope["state"].get("phone")
    if not phone or w.code != "DELETE":
        raise HTTPException(400, "type DELETE")
    for k in [k for k in SESSIONS if k[0] == ledger.book_file(phone)]:
        SESSIONS.pop(k)
    accounts.delete_account(phone)
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE)
    return r


@app.post("/api/demo_data")
def demo_data():
    """Fill an EMPTY book with 3 weeks of clearly-marked sample records (for trying the app / the demo video)."""
    if ledger.credit_profile():
        raise HTTPException(400, "Your book already has records.")
    import seed_demo

    seed_demo.seed()
    return {"ok": True}


# ---------------------------------------------------------------- pages

app.mount("/static", StaticFiles(directory=os.path.join(HERE, "web")), name="static")


@app.get("/")
def landing():
    return _page("landing.html")


@app.get("/sw.js")
def service_worker():
    """Offline: the app opens without internet, and voice notes wait on the phone until it's back."""
    return FileResponse(os.path.join(HERE, "web", "sw.js"), media_type="text/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.on_event("startup")
def _auto_reminders():
    extras.start_scheduler()


NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


def _version():
    """Changes whenever any file in web/ changes: stamped on /static links so a browser never mixes an old page
    with a new stylesheet (that showed old tabs with the new colours and an empty Insights screen)."""
    web = os.path.join(HERE, "web")
    return str(int(max(os.path.getmtime(os.path.join(web, f)) for f in os.listdir(web))))


def _page(name):
    html = open(os.path.join(HERE, "web", name), encoding="utf-8").read()
    v = _version()
    html = re.sub(r'(/static/[\w.-]+\.(?:css|js|svg|png))(?=["\'])', rf"\1?v={v}", html)
    return HTMLResponse(html, headers=NO_CACHE)


@app.get("/app")
def index():
    return _page("index.html")


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
