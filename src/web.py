"""TradeVoice web app: a phone-style front end (web/) over the same Python brains as the Gradio app.

    python src/web.py                  -> http://localhost:8000   (old Gradio screens stay at /admin)
    public link on Brev:  cloudflared tunnel --url http://localhost:8000   (see README)

The API only moves data; every number still comes from ledger.py / insights.py, every reply from converse.py.
"""
import asyncio
import datetime as dt
import json
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.parse
import uuid

import settings  # noqa: F401  (loads .env before the other modules read it)
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import accounts
import converse
import events
import insights
import ledger
import photo
import training
import tts
import ui_text
from extract import TYPES, fold

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root (web/ lives there)
SHOP_NAME = os.getenv("SHOP_NAME", "Chioma Stores")
VOICE_LANGS = {"English": "English / Pidgin", "Pidgin": "English / Pidgin", "Yoruba": "Yoruba", "Hausa": "Hausa",
               "Igbo": "Igbo"}

app = FastAPI(title="TradeVoice")
import whatsapp  # noqa: E402  (the WhatsApp bot: same server, same link, same book)

app.include_router(whatsapp.router)
import team  # noqa: E402  (/team: the team's dashboard + anonymised CSV, ADMIN_TOKEN only)
app.include_router(team.router)
import v2  # noqa: E402  (the TradeVoice 2.0 design's accounts + book: design/tradevoice-2.0/)
app.include_router(v2.router)
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
        if scope["type"] == "websocket":   # live hearing: only who it is (it reads no book); refused when logged out
            cookies = {}
            for k, v in scope.get("headers", []):
                if k == b"cookie":
                    for part in v.decode("latin-1").split(";"):
                        name, _, val = part.strip().partition("=")
                        cookies[name] = val
            phone = accounts.phone_for(cookies.get(COOKIE))
            if AUTH_REQUIRED and not phone:
                await receive()
                return await send({"type": "websocket.close", "code": 4401})
            scope.setdefault("state", {})["phone"] = phone
            return await self.inner(scope, receive, send)
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
MAKING = {}     # speak id -> threading.Event while its voice is being made (after a voice note: started at once)
VOICES = {}     # speak id -> intron_live.Voice: a live reply's voice, piece by piece


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
    SPEAK[sid] = (text, lang if lang in tts.REPLY_LANGS else "English")
    return sid


def _make_voice(sid):
    try:
        text, lang = SPEAK[sid]
        out = tts.speak(text, lang)
        AUDIO[sid] = out["path"] if out else None   # None = no voice for this reply (off, or Intron failed)
    except Exception as e:  # noqa: BLE001  (no voice: the reply is still on screen)
        AUDIO[sid] = None
        print(f"voice reply failed: {type(e).__name__}: {e}")
    finally:
        ev = MAKING.pop(sid, None)
        if ev:
            ev.set()


def _start_voice(sid):
    """After a voice note the spoken reply is made straight away, while the trader reads the card: by the time the
    page asks for it (/api/speak) it is ready or nearly. One Intron call per reply, never two."""
    if sid and sid in SPEAK and sid not in AUDIO and sid not in MAKING:
        MAKING[sid] = threading.Event()
        threading.Thread(target=_make_voice, args=(sid,), daemon=True).start()


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
    if rec.get("amount") in (None, "") or rec.get("_price") or rec.get("_big") or rec.get("_reask") == "amount":
        unsure.append("amount")   # no amount, far from their usual price, or not heard clearly
    if (rec.get("confidence") or 0) < 0.5 and rec.get("amount") not in (None, ""):
        unsure.append("type")
    if rec.get("type") in ("credit_sale", "payment_received", "credit_purchase", "payment_made") and not rec.get("customer"):
        unsure.append("customer")  # a debt needs a person
    elif rec.get("_reask") == "customer":
        unsure.append("customer")  # a new name not heard clearly
    if rec.get("type") in ("credit_sale", "credit_purchase") and not rec.get("due_date"):
        unsure.append("due_date")
    known = bool(rec.get("customer_id")) or bool(rec.get("customer") and ledger.find_customers(rec["customer"]))
    return {"type": rec.get("type"), "amount": rec.get("amount"), "customer": rec.get("customer"),
            "new_customer": bool(rec.get("customer")) and not known, "item": rec.get("item"),
            "quantity": rec.get("quantity"), "unit": rec.get("unit"), "due_date": rec.get("due_date"),
            "note": converse.friendly_note(rec.get("note"), state.get("lang") or "English"), "unsure": unsure,
            "limit": converse.draft_limit(rec)}


def _reply_json(r, state, heard=None, live=False):
    from plain import no_emoji   # words only, whatever wrote them (the AI included)
    spoken = no_emoji(tts.live_ask(r.get("spoken"), r["lang"]) if live else r.get("spoken"))
    return {"text": no_emoji(r["text"]), "english": no_emoji(r.get("english")), "lang": r["lang"], "heard": heard,
            "message": no_emoji(r.get("message")), "link": r.get("link"), "choices": r.get("choices"),
            "pending": bool(state.get("pending")), "draft": _draft(state), "saved": bool(r.get("saved")),
            "speak": _speak_id(spoken, r["lang"]), "rows": r.get("rows") or [], "act": r.get("act")}


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

        lang = lang if lang in ui_text.LANGS else "English"   # honest: never a "Hello" that ignores the question
        said = converse.SAY["not_sure"].get(lang, converse.SAY["not_sure"]["English"])
        return {"text": said, "spoken": said, "lang": lang}


@app.post("/api/voice")
def voice(file: UploadFile = File(...), session: str = Form("anon"), lang: str = Form("English"),
          consent: str = Form(""), shop: str = Form(""), live: str = Form("")):
    """A voice note in, the reply out (its spoken voice is made at once in the background). live=1: the live
    conversation (no buttons), so the read-back asks "Should I save it?" instead of "Press save"."""
    heard = _hear(file, lang, consent)
    if isinstance(heard, JSONResponse):
        return heard
    out = _say(heard["text"], session, lang, shop, live == "1")
    out["engine"], out["detected"] = heard.get("engine"), heard.get("detected")
    return out


def _hear(file, lang, consent):
    """Voice note -> words (nothing else changes: safe to run early and to throw away)."""
    if consent != "yes":
        raise HTTPException(400, "consent needed")
    path, heard = _upload(file, os.path.splitext(file.filename or "")[1] or ".webm"), None
    try:
        from asr import transcribe_auto

        heard = transcribe_auto(path, VOICE_LANGS.get(lang, "English / Pidgin"), vocab=ledger.known_words())
    except Exception as e:  # noqa: BLE001
        print(f"hearing failed: {type(e).__name__}: {e}")
        return JSONResponse({"error": "Sorry, I couldn't hear that. Please try again, or type it."}, 502)
    finally:
        training.keep(path, "voice", lang, heard)   # only if this trader said yes to helping train TradeVoice
        os.remove(path)  # the voice note is deleted as soon as it is read
    heard["text"] = (heard.get("text") or "").strip()
    if not heard["text"]:
        return JSONResponse({"error": "I didn't hear anything. Try again, closer to the phone."}, 422)
    if heard.get("check"):   # an unclear amount or name: kept for the reply (live talk replies in the next call)
        now = time.time()
        for k in [k for k, (t, _) in HEARD_CHECKS.items() if now - t > 300]:
            HEARD_CHECKS.pop(k, None)
        HEARD_CHECKS[(ledger.book_path(), heard["text"])] = (now, heard["check"])
    return heard


HEARD_CHECKS = {}   # (book, words heard) -> (time, what the hearing models weren't sure of), for 5 minutes


def _say(text, session, lang, shop, live):
    """Words -> the reply (the conversation moves on: a draft, a question, or a save), its voice started at once."""
    state = _state(session, lang)
    if live:
        state["queue_ok"] = True    # the live conversation: several things said one after the other wait together
        state["fast"] = os.getenv("LIVE_FAST_RECORDS", "1") == "1"   # a record the rules read fully: no model wait
    check = HEARD_CHECKS.pop((ledger.book_path(), text), (0, None))[1]
    if check:
        state["heard_check"] = check   # the chat asks again for just the unclear part
    t0 = time.perf_counter()
    import llm

    with llm.budget(float(os.getenv("ASK_AI_SECONDS", "20"))):   # a reply in time, even while N-ATLaS wakes up
        r = _safe_reply(text, state, shop, lang)
    out = _reply_json(r, state, heard=text, live=live)
    ms = (time.perf_counter() - t0) * 1000
    events.log("understand", channel="web", lang=lang, ms=ms, engine="live talk" if live else "voice")   # speed (E6)
    training.keep_turn("live_turn" if live else "voice_turn", text, out.get("text"), lang,
                       {"engine": r.get("engine"), "ms": int(ms)})   # only if this trader said yes
    out["parts"] = 0
    if live and out.get("speak"):   # live talk: the voice in short pieces, the first plays while the rest is made
        import intron_live

        words, said_in = SPEAK[out["speak"]]
        VOICES[out["speak"]] = v = intron_live.Voice(words, said_in).start()
        out["parts"] = len(v.parts)
        for k in list(VOICES)[:-200]:   # keep the last 200 replies' pieces
            VOICES.pop(k, None)
    else:
        _start_voice(out.get("speak"))
    return out


@app.post("/api/hear")
def hear(file: UploadFile = File(...), lang: str = Form("English"), consent: str = Form("")):
    """Live talk, step 1: only the words. The page sends this at a short pause while it keeps listening; if the trader
    goes on talking, it throws this away and sends the whole thing again. Nothing in the book or the chat changes.
    No N-ATLaS merge of the two hearings here (hearing.live): the reply is this turn's one N-ATLaS call."""
    import hearing

    with hearing.live():
        heard = _hear(file, lang, consent)
    if isinstance(heard, JSONResponse):
        return heard
    return {"heard": heard["text"], "engine": heard.get("engine"), "detected": heard.get("detected")}


class Said(BaseModel):
    session: str = "anon"
    text: str
    lang: str = "English"
    shop: str = ""


@app.post("/api/say")
def say(b: Said):
    """Live talk, step 2: the trader has really finished; the words heard in step 1 get their (spoken) reply."""
    if not b.text.strip():
        raise HTTPException(400, "nothing was said")
    return _say(b.text.strip(), b.session, b.lang, b.shop, live=True)


# ---------------------------------------------------------------- Ask: the chat with your book (design 3, Ask tab)
# The questions and answers are kept on the trader's phone (the design's history); the server keeps only what a
# conversation needs to follow on ("how much does SHE owe?"), per open page, and forgets it on "Clear history".

ASK_PHOTO = {
    "not_record": {"English": "This looks like {what}, not a page from your record book. Send a photo of your book or a "
                             "receipt, and I'll read every line.",
                   "Pidgin": "Dis one be like {what}, e no be page from your record book. Send photo of your book or "
                             "receipt, I go read every line.",
                   "Yoruba": "Èyí dà bí {what}, kì í ṣe ojú ìwé àkọsílẹ̀ rẹ. Fi fọ́tò ìwé rẹ tàbí rìsíìtì ránṣẹ́, màá "
                             "ka gbogbo ìlà.",
                   "Hausa": "Wannan kamar {what} ne, ba shafin littafin ajiyarka ba. Aiko hoton littafinka ko rasit, zan "
                            "karanta kowane layi.",
                   "Igbo": "Nke a dị ka {what}, ọ bụghị peeji akwụkwọ ndekọ gị. Zitere m foto akwụkwọ gị ma ọ bụ "
                           "risiti, m ga-agụ ahịrị ọ bụla."},
    "found": {"English": "I found {n} lines. Check them before I save.", "Pidgin": "I see {n} lines. Check dem before I save.",
              "Yoruba": "Mo rí ìlà {n}. Ṣàyẹ̀wò wọn kí n tó kọ wọ́n sílẹ̀.", "Hausa": "Na ga layuka {n}. Duba su kafin in adana.",
              "Igbo": "Ahụrụ m ahịrị {n}. Lelee ha tupu m chekwaa."},
    "found1": {"English": "I found 1 line. Check it before I save.", "Pidgin": "I see 1 line. Check am before I save.",
               "Yoruba": "Mo rí ìlà kan. Ṣàyẹ̀wò rẹ̀ kí n tó kọ ọ́ sílẹ̀.", "Hausa": "Na ga layi 1. Duba shi kafin in adana.",
               "Igbo": "Ahụrụ m otu ahịrị. Lelee ya tupu m chekwaa."},
    "none": {"English": "I couldn't read that page. Try again in good light, with the whole page in the photo.",
             "Pidgin": "I no fit read that page. Try again for better light, make the whole page show.",
             "Yoruba": "Mi ò lè ka ojú ìwé yẹn. Tún gbìyànjú níbi tí ìmọ́lẹ̀ wà, kí gbogbo ojú ìwé hàn nínú fọ́tò.",
             "Hausa": "Ban iya karanta wannan shafin ba. Sake gwadawa a wuri mai haske, duk shafin ya fito a hoton.",
             "Igbo": "Enweghị m ike ịgụ peeji ahụ. Nwaa ọzọ n'ebe ìhè dị, ka peeji niile pụta na foto."},
    "cant": {"English": "I can't read photos right now. Try again later.",
             "Pidgin": "I no fit read photo now. Try again later.",
             "Yoruba": "Mi ò lè ka fọ́tò báyìí. Tún gbìyànjú nígbà míì.",
             "Hausa": "Ba zan iya karanta hoto yanzu ba. Sake gwadawa anjima.",
             "Igbo": "Enweghị m ike ịgụ foto ugbu a. Nwaa ọzọ ma emechaa."},
}


def _headline(text):
    """The big number on top of an answer: the one amount in its first sentence ("Mama Tunde owes you ₦63,600.").
    None when the first sentence has none, or several (then the words carry it)."""
    money = lambda x: re.findall(r"₦\s?\d[\d,]*(?:\.\d+)?", x)  # noqa: E731
    first = re.split(r"(?<=[.!?])\s|\n", text or "", maxsplit=1)[0]
    head, _, tail = first.partition(":")    # "owes you the most: ₦45,000" / "₦70,000 in total, 2 people: A ₦…, B ₦…"
    if not money(head) and tail.strip().startswith("₦"):   # "money that came in: ₦10,000 (₦8,000 + ₦2,000)"
        return money(tail)[0].replace(" ", "")
    for part in (head, tail if not money(head) else "", first):
        found = money(part)
        if len(found) == 1:
            return found[0].replace(" ", "")
        if found:
            return None
    return None


def _ask_text(r, out):
    """The chat bubble's words: no WhatsApp *bold*, choices as numbered lines, a reminder's message to forward."""
    t = (out["text"] or "").replace("*", "")
    if r.get("choices"):
        n = 0
        for key, label in r["choices"]:
            if key == "cust:new":
                t += "\n" + label + " (say: new)"
            else:
                n += 1
                t += f"\n{n}. {label}"
    if out.get("message"):
        t += "\n\n" + out["message"]
    return t


class AskIn(BaseModel):
    session: str = "anon"
    text: str
    lang: str = "English"
    voice: bool = False     # asked by voice (the answer is still words: its voice is made only on a tap)
    shop: str = ""


JOBS = {}   # a long answer: job id -> (done event, result box, started)


def _in_time(fn):
    """Answer within ANSWER_WAIT_SECONDS (25 s): iPhone Safari gives up on a request after 60 s and the page called
    that "No network". A longer piece of work (a sleeping N-ATLaS, a photo, a long list) goes on in the background
    and the page collects it from /api/job/<id>."""
    import contextvars

    jid, ev, box = uuid.uuid4().hex, threading.Event(), {}
    ctx = contextvars.copy_context()   # the trader's own book goes with the work

    def work():
        try:
            box["result"] = ctx.run(fn)
        except HTTPException as e:
            box["error"] = (e.status_code, e.detail)
        except Exception as e:  # noqa: BLE001
            print(f"answer failed: {type(e).__name__}: {e}")
            box["error"] = (500, "Sorry, something went wrong. Try again.")
        ev.set()
    threading.Thread(target=work, daemon=True).start()
    if ev.wait(float(os.getenv("ANSWER_WAIT_SECONDS", "25"))):
        return _job_out(box)
    now = time.time()
    for k in [k for k, (_, _, t0) in JOBS.items() if now - t0 > 900]:
        JOBS.pop(k, None)
    JOBS[jid] = (ev, box, now)
    return {"job": jid}


def _job_out(box):
    if "error" in box:
        raise HTTPException(*box["error"])
    return box["result"]


@app.get("/api/job/{jid}")
def job(jid: str):
    """A long answer, collected by the page: waits up to 20 s, then {"job": id} again if it is still being worked on."""
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, "that answer is gone; ask again")
    ev, box, _ = j
    if not ev.wait(20):
        return {"job": jid}
    JOBS.pop(jid, None)
    return _job_out(box)


def _rules_first(text, state):
    """Messages the record flow must answer itself (it holds what is waiting): yes / no / undo / save one only /
    "no, that's wrong" after a save / a pasted list / an answer to "Which Alhaji?" or "Say the amount again" / the
    time / hello, thanks, help (fixed words, no model needed)."""
    import clock

    t = fold(text)
    return bool(converse._drafts(state) or state.get("choose") or state.get("heard_check")
                or converse.YES.match(t) or converse.NO.match(t) or converse.UNDO.match(t) or converse.ONLY.search(t)
                or (converse._last_saved(state) and converse.WRONG_AFTER.match(t)) or converse.is_list(text)
                or clock.asked(t) or converse.THANKS.match(t) or converse.GREET.match(t) or converse.HELP.search(t))


def _ask_brain(text, state, shop, lang):
    """The Ask chat: the model (agent.py) answers, with the book's tools; a new record, the commands above, or a
    model that fails go to the record flow and the rules (converse.reply)."""
    import agent
    import llm

    if agent.available(lang) and not _rules_first(text, state):
        with llm.budget(float(os.getenv("ASK_LLM_SECONDS", "45"))):
            a = agent.answer(text, state, lang)
        if a and not a.get("record"):
            return a   # (the model marks a message that isn't about the shop: agent.py shows the fixed line)
    with llm.budget(float(os.getenv("ASK_AI_SECONDS", "20"))):   # an answer in time, even while N-ATLaS wakes up
        r = _safe_reply(text, state, shop, lang)
    agent.remember(state, text, r.get("text") or "")
    return r


@app.get("/api/ask_check")
def ask_check(q: str = "How much does Mike and Dino owe me?", lang: str = "English"):
    """Open /api/ask_check?q=... while logged in: one question through the Ask chat's model, on your own book, and
    what happened (which model, what it wrote, which tools, why the rules answered if they did). Never shows a key."""
    import agent
    import llm

    state = converse.new_state()
    if not agent.available(lang):
        return {"model_on": False, "why": "no NVIDIA_API_KEY and no N-ATLaS (or ASK_BRAIN=rules)", "models": agent.models(lang)}
    t0 = time.perf_counter()
    with llm.budget(float(os.getenv("ASK_LLM_SECONDS", "45"))):
        a = agent.answer(q, state, lang)
    return {"model_on": True, "models": agent.models(lang), "question": q, "seconds": round(time.perf_counter() - t0, 1),
            "answer": (a or {}).get("text"), "record": bool((a or {}).get("record")), "tools": (a or {}).get("tools"),
            "steps": state.get("_trace")}


@app.post("/api/ask")
def ask_chat(b: AskIn):
    return _in_time(lambda: _ask(b))


def _ask(b):
    """One question in the Ask chat -> {n, t, lang, say, speak}. The same brain as everywhere (the book, the tools,
    5 languages, N-ATLaS); a record said here waits for "yes" like anywhere else.
    The chat answers in words, even to a voice question. The spoken answer costs an Intron call, so it is made only
    when the trader taps its play button (/api/speak/<speak>), never by itself."""
    text = (b.text or "").strip()[:1000]
    if not text:
        raise HTTPException(400, "nothing was asked")
    state = _state("ask:" + b.session, b.lang)
    state["queue_ok"] = True    # a chat: drafts said one after the other wait together ("save it all")
    check = HEARD_CHECKS.pop((ledger.book_path(), text), (0, None))[1]
    if check:
        state["heard_check"] = check
    t0 = time.perf_counter()
    r = _ask_brain(text, state, b.shop, b.lang)
    out = _reply_json(r, state, heard=text if b.voice else None, live=True)   # no buttons in a chat: "Should I save it?"
    ms = (time.perf_counter() - t0) * 1000
    events.log("understand", channel="web", lang=b.lang, ms=ms, engine=r.get("engine"))
    words = _ask_text(r, out)
    training.keep_turn("ask_turn", text, words, b.lang, {"engine": r.get("engine"), "ms": int(ms),
                                                          "voice": bool(b.voice)})   # only if this trader said yes
    said = SPEAK.get(out["speak"], (None,))[0] if out.get("speak") else None
    return {"t": words, "n": None if r.get("rows") else _headline(words), "lang": out["lang"],
            "english": out.get("english"), "say": said, "speak": out.get("speak"), "pending": out["pending"],
            "link": out.get("link"), "rows": out["rows"], "act": out["act"]}


@app.post("/api/ask/photo")
def ask_photo(file: UploadFile = File(...), consent: str = Form(""), lang: str = Form("English")):
    """A photo of a notebook page sent in the chat -> {t, rows, act}. Nothing is saved: the trader checks the
    lines first ("Check the lines"), then /api/save_rows."""
    if consent != "yes":
        raise HTTPException(400, "consent needed")
    lang = lang if lang in ASK_PHOTO["found"] else "English"
    path = _upload(file, os.path.splitext(file.filename or "")[1] or ".jpg")
    return _in_time(lambda: _ask_photo(path, lang))   # the vision model can take a while: never "No network"


def _ask_photo(path, lang):
    res = None
    try:
        res = photo.read(path)
    except Exception as e:  # noqa: BLE001
        print(f"ask photo failed: {type(e).__name__}: {e}")
        return {"t": ASK_PHOTO["cant"][lang], "rows": [], "act": None, "lang": lang}
    finally:
        training.keep(path, "photo", lang, res)   # only if this trader said yes to helping train TradeVoice
        os.remove(path)   # the photo is deleted as soon as it is read
    if res.get("not_record"):   # an advert, a person, a product: said, nothing read into the book
        return {"t": ASK_PHOTO["not_record"][lang].format(what=res["not_record"]), "rows": [], "act": None, "lang": lang}
    rows = res.get("rows") or []
    key = "none" if not rows else "found1" if len(rows) == 1 else "found"
    return {"t": ASK_PHOTO[key][lang].format(n=len(rows)), "rows": rows, "act": "scan" if rows else None, "lang": lang}


class SayAgain(BaseModel):
    text: str
    lang: str = "English"


@app.post("/api/ask/say")
def ask_say(b: SayAgain):
    """Play an answer again (the voice-note button): a fresh id for the same words. Words already spoken come
    from the voice cache, so a replay costs nothing."""
    from plain import no_emoji
    text = no_emoji((b.text or "").replace("*", "").strip())[:800]
    if not text:
        raise HTTPException(400, "nothing to say")
    import assistant
    return {"speak": _speak_id(assistant.spoken(text), b.lang)}


class AskReset(BaseModel):
    session: str = "anon"


@app.post("/api/ask/reset")
def ask_reset(b: AskReset):
    """'Clear history': the server forgets this chat's follow-on memory (who was talked about, a waiting draft)."""
    SESSIONS.pop((ledger.book_path(), "ask:" + (b.session or "anon")), None)
    return {"ok": True}


@app.post("/api/warm")
def warm():
    """Talk was opened: wake the N-ATLaS servers now, so they are up by the time the voice note arrives."""
    import natlas_watch

    import intron_live

    return {"waking": natlas_watch.wake(), "live": intron_live.hearing_on()}   # live: hear with Intron's stream


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
                return {"lang": lang, "ok": False, "error": "no voice set up: add INTRON_API_KEY (or SPITCH_API_KEY) to .env"}
            size = os.path.getsize(path)
            os.remove(path)
            return {"lang": lang, "ok": True, "format": "ogg (WhatsApp voice note)", "bytes": size}
        out = tts.speak(text, lang if lang in tts.REPLY_LANGS else "English")
        if not out:   # the real reason (no key, Intron refused the key / credit, or Intron's own error)
            return {"lang": lang, "ok": False, "error": tts.why_not_intron() or "Intron gave no audio (see the server log)"}
        return {"lang": lang, "ok": True, "engine": out["engine"], "bytes": os.path.getsize(out["path"]),
                "why_not_intron": None if out["engine"].startswith("intron") else tts.why_not_intron()}
    except Exception as e:  # noqa: BLE001
        return {"lang": lang, "ok": False, "error": f"{type(e).__name__}: {e}"[:500]}


@app.get("/api/speak/{sid}/{i}")
def speak_piece(sid: str, i: int):
    """Live talk: piece i of a reply's voice, as soon as it is made (piece 1 plays while piece 2 is being made)."""
    v = VOICES.get(sid)
    if not v or not 0 <= i < len(v.parts):
        raise HTTPException(404)
    v.ready[i].wait(45)
    if not v.files[i]:
        raise HTTPException(404, "no voice for this piece")
    return FileResponse(v.files[i], media_type="audio/wav")


@app.websocket("/api/live/hear")
async def live_hear(ws: WebSocket, lang: str = "English", consent: str = ""):
    """Live talk, hearing while you talk: the page streams the mic (16 kHz, 16-bit), we pass it to Intron's streaming
    speech-to-text and send the words back as they come; {"type": "commit"} gives the final words."""
    import intron_live

    await ws.accept()
    if consent != "yes" or not intron_live.hearing_on():
        await ws.send_text(json.dumps({"type": "error", "message": "consent needed" if consent != "yes" else "off"}))
        return await ws.close()
    got = await intron_live.relay_hearing(ws, lang, collect=bool(training.answer()))
    if got and got.get("pcm"):   # only kept for a trader who said yes to helping train TradeVoice
        await asyncio.to_thread(training.keep_pcm, got["pcm"], lang, {"text": got.get("text", "")})
    try:
        await ws.close()
    except Exception:  # noqa: BLE001
        pass


@app.get("/api/speak/{sid}")
def speak(sid: str):
    """The voice note for a reply, made on first request (so the text shows without waiting for the voice)."""
    ev = MAKING.get(sid)
    if ev:
        ev.wait(90)   # already being made since the voice note came in
    if sid not in AUDIO:
        if sid not in SPEAK:
            raise HTTPException(404)
        text, lang = SPEAK[sid]
        out = tts.speak(text, lang)
        if not out:
            raise HTTPException(404, "voice is off")
        AUDIO[sid] = out["path"]
    if not AUDIO[sid]:
        raise HTTPException(404, "no voice for this reply")
    return FileResponse(AUDIO[sid], media_type="audio/wav")


# ---------------------------------------------------------------- photo of the book

@app.post("/api/photo")
def photo_api(file: UploadFile = File(...), consent: str = Form("")):
    if consent != "yes":
        raise HTTPException(400, "consent needed")
    path, res = _upload(file, os.path.splitext(file.filename or "")[1] or ".jpg"), None
    try:
        res = photo.read(path)
        return res
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Could not read the photo ({type(e).__name__}: {str(e)[:100]})."}, 502)
    finally:
        training.keep(path, "photo", "", res)   # only if this trader said yes to helping train TradeVoice
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
    lang: str = "English"
    shop: str | None = None


@app.post("/api/customers/{cid}/reminder")
def customer_reminder(cid: int, b: Remind, request: Request):
    """TradeVoice drafts the reminder (with a pay link); the trader edits it and sends it from their own WhatsApp."""
    cust = _customer_or_404(cid)
    msg, link = insights.reminder(cust["name"], b.lang if b.lang in insights.TEMPLATES and b.lang != "Pidgin" else "English",
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
def reminder(customer: str, request: Request, lang: str = "English", shop: str = ""):
    msg, link = insights.reminder(customer, lang if lang in insights.TEMPLATES and lang != "Pidgin" else "English", shop or SHOP_NAME)
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
    out = tts.speak(readaloud.text(screen, lang), lang if lang in tts.REPLY_LANGS else "English")
    if not out:
        raise HTTPException(404, "voice is off")
    return FileResponse(out["path"], media_type="audio/wav")


# ---------------------------------------------------------------- Ask TradeVoice (voice assistant on every screen)

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
    out = tts.speak(e.get("spoken") or e["text"], lang if lang in tts.REPLY_LANGS else "English")
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
        path, h = _upload(file, os.path.splitext(file.filename or "")[1] or ".webm"), None
        try:
            from asr import transcribe_auto

            h = transcribe_auto(path, VOICE_LANGS.get(speak_lang, "English / Pidgin"), vocab=ledger.known_words())
            heard, detected = h["text"].strip(), h.get("detected")
        except Exception as e:  # noqa: BLE001
            print(f"hearing failed: {type(e).__name__}: {e}")
            return JSONResponse({"error": "Sorry, I couldn't hear that. Please try again, or type it."}, 502)
        finally:
            training.keep(path, "voice", speak_lang, h)   # only if this trader said yes to helping train TradeVoice
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

    hearing = os.getenv("ASR_ENGINE") or ("natlas" if os.getenv("NATLAS_ASR_URL") else
                                          "intron" if os.getenv("INTRON_API_KEY") else "local")
    brain = ("natlas" if llm.natlas_on() else "brev" if os.getenv("LOCAL_LLM_URL") else
             "nvidia" if os.getenv("NVIDIA_API_KEY") else "offline")
    # counts only: no error text or tokens on this public page (details are on /team)
    return {"hearing": hearing, "voice": tts.backend(), "brain": brain,
            "keep_awake": bool(os.getenv("NATLAS_URL")) and os.getenv("NATLAS_WATCH", "1") == "1",
            "photos": "brev" if os.getenv("LOCAL_VISION_URL") else ("nvidia" if llm.available("vision") else "off"),
            "shop": SHOP_NAME, "whatsapp": v2.whatsapp_on(), "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "signup_code": not v2.channels()["nocode"]}


# ---------------------------------------------------------------- log in with your phone number

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
    import events
    events.log("web_visit", phone, "web", lang=p.get("lang"))
    token = ledger.use_book(phone)
    try:
        empty = ledger.is_empty()
    finally:
        ledger.done_with_book(token)
    guest = accounts.is_guest(phone)
    return {"phone": "" if guest else accounts.masked(phone), "guest": guest, "name": p.get("name") or "", "shop": p.get("shop") or "",
            "lang": p.get("lang") or "", "new": not p.get("shop"), "empty_book": empty, "has_pin": extras.has_pin(phone)}


@app.post("/api/auth/start")
def auth_start(b: Start, request: Request):
    phone = accounts.normalize(b.phone)
    if not phone:
        raise HTTPException(400, "That doesn't look like a phone number. Try like 0803 123 4567.")
    if v2._too_many(phone, request):
        raise HTTPException(429, "Too many codes asked for. Try again in an hour.")
    login = accounts.start(phone)
    sent = False
    if not accounts.demo_mode():
        try:   # inside Meta's 24-hour window or with the code template; else LOGIN <word> below
            sent = whatsapp.send_code(phone, login["code"])
        except Exception as e:  # noqa: BLE001 - expired token
            print(f"login code not sent by WhatsApp: {e}")
    bot = whatsapp.bot_number() if whatsapp.login_by_message_ok() else ""
    # the code is NEVER shown on screen when sending fails (that let anyone open any number's book); they can still
    # verify by sending LOGIN <word> to the bot from that phone. AUTH_STRICT=0 restores the old fallback (demos only)
    fallback = not sent and not accounts.demo_mode() and os.getenv("AUTH_STRICT", "1") == "0"
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


class Guest(BaseModel):
    shop: str | None = None
    lang: str | None = None


@app.post("/api/auth/guest")
def auth_guest(b: Guest, request: Request):
    """No login: this phone/browser gets its own book straight away (kept by a cookie for 90 days)."""
    phone = request.scope["state"].get("phone")
    if phone:
        return {"ok": True, "me": _me(phone)}
    phone = accounts.new_guest()
    accounts.update_profile(phone, shop=(b.shop or "").strip()[:60] or "My shop",
                            lang=b.lang if b.lang in VOICE_LANGS else None)
    return _logged_in(request, phone)


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
    accounts.end_session(request.cookies.get(COOKIE))
    at = v2.schedule_delete(phone)   # closed now, erased after v2.DELETE_DAYS (same as the app's delete screen)
    r = JSONResponse({"ok": True, "delAt": at})
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

import mimetypes  # noqa: E402

mimetypes.add_type("application/manifest+json", ".webmanifest")   # "Add to Home Screen": the app's install file
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "web")), name="static")


@app.get("/")
def landing():
    return _page("landing.html")


@app.get("/privacy")
def privacy():
    """The privacy notice (sign-up links to it; it states the 90-day hold after an account is deleted)."""
    import html as _html

    page = open(os.path.join(HERE, "web", "privacy.html"), encoding="utf-8").read()
    contact = _html.escape(os.getenv("PRIVACY_CONTACT", "").strip()) or "the TradeVoice team"
    supa = bool(os.getenv("BACKUP_SUPABASE_URL"))
    page = page.replace("{{contact}}", contact).replace(
        "{{backup}}", " A backup copy is also kept in a private store with Supabase." if supa else "").replace(
        "{{backup_company}}", "\n<li><b>Supabase:</b> keeps a private backup copy.</li>" if supa else "")
    return HTMLResponse(page, headers=NO_CACHE)


@app.get("/sw.js")
def service_worker():
    """Offline: the app opens without internet, and voice notes wait on the phone until it's back."""
    return FileResponse(os.path.join(HERE, "web", "sw.js"), media_type="text/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.on_event("startup")
def _auto_reminders():
    extras.start_scheduler()
    import events
    import llm
    import natlas_watch
    events.ENABLED = True  # the real server records the interaction log (tests and benchmarks don't)
    llm.wake_natlas()     # start the N-ATLaS GPU loading now, not on the first trader's message
    natlas_watch.start()  # market hours: keep it warm + WhatsApp the team if it stops answering


NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


def _version():
    """Changes whenever any file in web/ changes: stamped on /static links so a browser never mixes an old page
    with a new stylesheet (that showed old tabs with the new colours and an empty Insights screen)."""
    web = os.path.join(HERE, "web")
    return str(int(max(os.path.getmtime(os.path.join(web, f)) for f in os.listdir(web))))


def _page(name):
    """The TradeVoice 2.0 pages (built from design/tradevoice-2.0/ by scripts/build_app.py)."""
    html = open(os.path.join(HERE, "web", name), encoding="utf-8").read()
    v = _version()
    html = re.sub(r'(/static/[\w.-]+\.(?:css|js|svg|png))(?=["\'])', rf"\1?v={v}", html)
    # which ways in work today (WhatsApp, Telegram, codes): the app and the website hide or reword what can't work
    ch = v2.channels()
    html = html.replace("</head>", "<script>window.TV_CH=" + json.dumps(ch).replace("</", "<\\/") + "</script>\n"
                        + ('<script src="/static/channels.js" defer></script>\n' if name == "landing.html" else "")
                        + "</head>", 1)
    bot = (os.getenv("WHATSAPP_BOT_NUMBER") or whatsapp.bot_number()) if ch["wa"] else ""
    if bot:  # the website's "Use on WhatsApp" buttons open a chat with the bot
        html = html.replace('href="https://wa.me/"', f'href="https://wa.me/{bot}?text=Hi"')
        html = html.replace('window.open("https://wa.me/","_blank"', f'window.open("https://wa.me/{bot}?text=Hi","_blank"')
        html = html.replace('"https://wa.me/?text="', f'"https://wa.me/{bot}?text="')   # "tell me when it's in the store"
    return HTMLResponse(html, headers=NO_CACHE)


@app.get("/app")
def index():
    return _page("app.html")


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
