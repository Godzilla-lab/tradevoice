"""The trust + money features, mounted in web.py:

🏦 Lender link: the trader agrees, picks how long (1 / 7 / 30 days), and gets a private link to their score and
   statement. Anyone with the link can view it until it expires or the trader revokes it; every view is counted.
💸 Pay link in reminders: /pay/<token> shows what the customer owes. With PAYSTACK_SECRET_KEY set they pay by card or
   transfer on Paystack and the debt settles by itself (Paystack's signed webhook records the payment). Without
   Paystack: the trader's bank details + "I have paid" -> the trader confirms in the customer's conversation.
⏰ Automatic reminders: on the promised day, TradeVoice drafts the reminder (with the pay link) in each customer's
   conversation and sends the trader one WhatsApp summary. The trader still presses send to the customer.
🧾 Receipts: after a record for a customer, a receipt ready to send on WhatsApp (shows the new balance).
🔒 PIN lock: a 4-digit PIN, checked by the server (the API refuses a locked session). 5 wrong -> wait 5 minutes.
📤 CSV export of the whole book.
"""
import csv
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import threading
import time
import urllib.parse

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

import accounts
import insights
import ledger

router = APIRouter()
_lock = threading.Lock()
UNLOCKS = {}          # unlock token -> (phone, expires) : a session that typed the right PIN
PIN_FAILS = {}        # phone -> (fails, locked_until)
UNLOCK_HOURS = 12


def _db():
    c = accounts.db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS shares (id INTEGER PRIMARY KEY AUTOINCREMENT, token_hash TEXT UNIQUE, phone TEXT,
        created_at TEXT, expires TEXT, revoked INTEGER DEFAULT 0, views INTEGER DEFAULT 0, last_view TEXT);
    CREATE TABLE IF NOT EXISTS paylinks (token_hash TEXT PRIMARY KEY, phone TEXT, customer_id INTEGER, amount REAL,
        created_at TEXT, expires TEXT, status TEXT DEFAULT 'open', ref TEXT);
    CREATE TABLE IF NOT EXISTS auto_runs (phone TEXT, day TEXT, PRIMARY KEY (phone, day));
    """)
    cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}
    for col in ("pin_hash", "bank_name", "account_number", "account_name"):
        if col not in cols:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
    return c


def _h(x):
    return hashlib.sha256(str(x).encode()).hexdigest()


def _now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _phone(request):
    phone = request.scope.get("state", {}).get("phone")
    if not phone:
        raise HTTPException(401, "Please log in with your phone number.")
    return phone


def _base(request):
    return (os.getenv("PUBLIC_URL") or str(request.base_url)).rstrip("/")


def _in_book(phone):
    """Context manager-ish: switch to this trader's book (for public pages that aren't logged in)."""
    class _B:
        def __enter__(self):
            self.t = ledger.use_book(phone)

        def __exit__(self, *a):
            ledger.done_with_book(self.t)
    return _B()


def _user(phone):
    with _db() as c:
        r = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    return dict(r) if r else {"phone": phone}


def _page(title, body):
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><title>{title}</title><style>
body{{font:17px/1.5 system-ui,sans-serif;margin:0;background:#FAF7F0;color:#13233F}}
main{{max-width:480px;margin:0 auto;padding:28px 20px}} h1{{font-size:26px;margin:0 0 6px}}
.big{{font-size:40px;font-weight:800}} .card{{background:#fff;border:1px solid #E6E0D4;border-radius:16px;padding:16px;margin:14px 0}}
.btn{{display:block;width:100%;text-align:center;border:0;border-radius:16px;padding:16px;font-weight:800;font-size:17px;
background:#F2A900;color:#13233F;text-decoration:none;margin-top:10px;cursor:pointer}} .muted{{color:#5E6878;font-size:14px}}
.ok{{background:#E3F4EA;color:#0B7A3E;border-radius:12px;padding:12px;font-weight:700}}
</style></head><body><main>{body}</main></body></html>""")


# ---------------------------------------------------------------- 🏦 lender link (consented, time-limited)

class Share(BaseModel):
    days: int = 7
    consent: bool = False


@router.post("/api/share")
def share_create(b: Share, request: Request):
    phone = _phone(request)
    if not b.consent:
        raise HTTPException(400, "Please agree first: the lender will see your score and records.")
    days = b.days if b.days in (1, 7, 30) else 7
    token = secrets.token_urlsafe(24)
    exp = _now() + dt.timedelta(days=days)
    with _lock, _db() as c:
        c.execute("INSERT INTO shares (token_hash, phone, created_at, expires) VALUES (?,?,?,?)",
                  (_h(token), phone, _now().isoformat(), exp.isoformat()))
    url = f"{_base(request)}/lender/{token}"
    return {"url": url, "expires": exp.date().isoformat(), "days": days,
            "whatsapp": "https://wa.me/?text=" + urllib.parse.quote(f"My TradeVoice business record: {url}")}


@router.get("/api/shares")
def shares_list(request: Request):
    phone = _phone(request)
    with _db() as c:
        rows = [dict(r) for r in c.execute("SELECT id, created_at, expires, revoked, views, last_view FROM shares "
                                           "WHERE phone=? ORDER BY id DESC LIMIT 20", (phone,))]
    now = _now().isoformat()
    return {"shares": [dict(r, active=not r["revoked"] and r["expires"] > now) for r in rows]}


@router.delete("/api/shares/{sid}")
def shares_revoke(sid: int, request: Request):
    phone = _phone(request)
    with _lock, _db() as c:
        n = c.execute("UPDATE shares SET revoked=1 WHERE id=? AND phone=?", (sid, phone)).rowcount
    if not n:
        raise HTTPException(404)
    return {"ok": True}


@router.get("/lender/{token}")
def lender_view(token: str):
    with _lock, _db() as c:
        r = c.execute("SELECT * FROM shares WHERE token_hash=?", (_h(token),)).fetchone()
        if not r or r["revoked"] or r["expires"] < _now().isoformat():
            return _page("Link expired", "<h1>This link has expired</h1><p class='muted'>The business owner shared "
                                         "it for a limited time, or stopped sharing it. Ask them for a new link.</p>")
        c.execute("UPDATE shares SET views=views+1, last_view=? WHERE id=?", (_now().isoformat(), r["id"]))
    u = _user(r["phone"])
    with _in_book(r["phone"]):
        page = insights.statement_html(u.get("shop") or "Business", "", None)
    if not page:
        return _page("No records", "<h1>No records yet</h1>")
    banner = (f"<p style='background:#FFF3D1;padding:10px 12px;border-radius:10px;font:14px system-ui'>🔒 Shared by the "
              f"business owner with their consent, until <b>{r['expires'][:10]}</b>. Phone ending "
              f"{r['phone'][-4:]}. From the owner's own confirmed records, not audited. Under the Nigeria Data "
              f"Protection Act the owner can stop sharing at any time; any lending decision needs the lender's own "
              f"checks and a human review.</p>")
    return HTMLResponse(page.replace("<h1>Business Record Statement</h1>", banner + "<h1>Business Record Statement</h1>"))


# ---------------------------------------------------------------- 💸 pay link inside reminders

def pay_link(base, phone, customer_id, amount):
    """A private link for this customer to pay this debt (valid 14 days)."""
    token = secrets.token_urlsafe(12)
    with _lock, _db() as c:
        c.execute("INSERT INTO paylinks (token_hash, phone, customer_id, amount, created_at, expires) "
                  "VALUES (?,?,?,?,?,?)", (_h(token), phone, customer_id, amount, _now().isoformat(),
                                           (_now() + dt.timedelta(days=14)).isoformat()))
    return f"{base}/pay/{token}"


def _paylink(token):
    with _db() as c:
        r = c.execute("SELECT * FROM paylinks WHERE token_hash=?", (_h(token),)).fetchone()
    if not r or r["expires"] < _now().isoformat():
        return None
    return dict(r)


def _owed_now(link):
    with _in_book(link["phone"]):
        s = ledger.customer_summary(link["customer_id"]) or {}
    return (s.get("owes_me") or 0), s


@router.get("/pay/{token}")
def pay_page(token: str):
    link = _paylink(token)
    if not link:
        return _page("Link expired", "<h1>This payment link has expired</h1><p class='muted'>Ask the trader for a new one.</p>")
    owed, s = _owed_now(link)
    u = _user(link["phone"])
    shop = u.get("shop") or "the trader"
    if owed <= 0:
        return _page("Paid", f"<h1>{shop}</h1><div class='ok'>✅ Nothing to pay. Thank you!</div>")
    bank = ""
    if u.get("account_number"):
        bank = (f"<div class='card'><b>Bank transfer</b><br>{u.get('bank_name') or ''}<br>"
                f"<span class='big' style='font-size:26px'>{u['account_number']}</span><br>{u.get('account_name') or ''}"
                f"<form method='post' action='/pay/{token}/claimed'><button class='btn' style='background:#13233F;color:#fff'>"
                f"I have paid</button></form><p class='muted'>The trader confirms when the money arrives.</p></div>")
    card = (f"<form method='post' action='/pay/{token}/paystack'><button class='btn'>Pay now (card / transfer / USSD)"
            f"</button></form><p class='muted'>Secure payment by Paystack. Your debt updates by itself.</p>"
            if os.getenv("PAYSTACK_SECRET_KEY") else "")
    if not card and not bank:
        bank = "<p class='muted'>The trader has not added a way to pay online yet. Please pay them directly.</p>"
    return _page(f"Pay {shop}", f"<p class='muted'>{shop}</p><h1>{s.get('name', '')}, you owe</h1>"
                                f"<div class='big'>₦{owed:,.0f}</div>{card}{bank}")


@router.post("/pay/{token}/claimed")
def pay_claimed(token: str):
    link = _paylink(token)
    if not link:
        raise HTTPException(404)
    owed, s = _owed_now(link)
    with _in_book(link["phone"]):
        ledger.add_message(link["customer_id"], f"💸 {s.get('name', 'The customer')} says they paid ₦{owed:,.0f} by bank "
                           f"transfer. Check your bank app, then confirm.", sender="customer", kind="payclaim",
                           status=f"claim:{owed:.0f}")
    with _lock, _db() as c:
        c.execute("UPDATE paylinks SET status='claimed' WHERE token_hash=?", (_h(token),))
    return _page("Thank you", "<div class='ok'>✅ Thank you! The trader will confirm when the money arrives.</div>")


@router.post("/pay/{token}/paystack")
def pay_paystack(token: str, request: Request):
    link = _paylink(token)
    key = os.getenv("PAYSTACK_SECRET_KEY")
    if not link or not key:
        raise HTTPException(404)
    owed, _ = _owed_now(link)
    if owed <= 0:
        return RedirectResponse(f"/pay/{token}", 303)
    ref = f"tv-{secrets.token_hex(8)}"
    r = requests.post("https://api.paystack.co/transaction/initialize", timeout=20,
                      headers={"Authorization": f"Bearer {key}"},
                      json={"email": os.getenv("PAYSTACK_EMAIL", "customer@tradevoice.app"), "amount": int(owed * 100),
                            "currency": "NGN", "reference": ref, "callback_url": f"{_base(request)}/pay/{token}",
                            "metadata": {"paylink": _h(token)}})
    j = r.json()
    if not r.ok or not j.get("status"):
        raise HTTPException(502, "Payment page could not open. Try again.")
    with _lock, _db() as c:
        c.execute("UPDATE paylinks SET ref=? WHERE token_hash=?", (ref, _h(token)))
    return RedirectResponse(j["data"]["authorization_url"], 303)


@router.post("/paystack/webhook")
async def paystack_webhook(request: Request):
    """Paystack tells us a payment succeeded (signed with our secret key) -> the debt settles by itself."""
    raw = await request.body()
    key = os.getenv("PAYSTACK_SECRET_KEY", "")
    sig = hmac.new(key.encode(), raw, hashlib.sha512).hexdigest()
    if not key or not hmac.compare_digest(sig, request.headers.get("x-paystack-signature", "")):
        raise HTTPException(401)
    ev = json.loads(raw)
    if ev.get("event") != "charge.success":
        return {"ok": True}
    data = ev["data"]
    with _db() as c:
        r = c.execute("SELECT * FROM paylinks WHERE ref=?", (data.get("reference"),)).fetchone()
    if not r or r["status"] == "paid":
        return {"ok": True}
    record_payment(dict(r), data["amount"] / 100, f"Paystack {data.get('reference')}")
    return {"ok": True}


def record_payment(link, amount, how):
    with _in_book(link["phone"]):
        ledger.add_entry({"type": "payment_received", "amount": amount, "customer_id": link["customer_id"]},
                         raw_text=f"(paid online: {how})", engine="paylink")
        s = ledger.customer_summary(link["customer_id"]) or {}
        ledger.add_message(link["customer_id"], f"✅ Paid ₦{amount:,.0f} online ({how}). New balance: "
                           f"₦{(s.get('owes_me') or 0):,.0f}.", sender="tradevoice", kind="note")
    with _lock, _db() as c:
        c.execute("UPDATE paylinks SET status='paid' WHERE token_hash=?", (link["token_hash"],))


class Bank(BaseModel):
    bank_name: str = ""
    account_number: str = ""
    account_name: str = ""


@router.get("/api/bank")
def bank_get(request: Request):
    u = _user(_phone(request))
    return {k: u.get(k) or "" for k in ("bank_name", "account_number", "account_name")} | {
        "paystack": bool(os.getenv("PAYSTACK_SECRET_KEY"))}


@router.post("/api/bank")
def bank_set(b: Bank, request: Request):
    phone = _phone(request)
    num = re.sub(r"\D", "", b.account_number)
    if num and len(num) != 10:
        raise HTTPException(400, "A Nigerian account number has 10 digits.")
    with _lock, _db() as c:
        c.execute("INSERT INTO users (phone) VALUES (?) ON CONFLICT(phone) DO NOTHING", (phone,))
        c.execute("UPDATE users SET bank_name=?, account_number=?, account_name=? WHERE phone=?",
                  (b.bank_name.strip(), num, b.account_name.strip(), phone))
    return {"ok": True}


class Confirm(BaseModel):
    message_id: int


@router.post("/api/customers/{cid}/confirm_paid")
def confirm_paid(cid: int, b: Confirm, request: Request):
    """The trader checked the bank app: record the payment the customer said they made."""
    with ledger.conn() as c:
        m = c.execute("SELECT * FROM messages WHERE id=? AND customer_id=? AND kind='payclaim'", (b.message_id, cid)).fetchone()
    if not m or not (m["status"] or "").startswith("claim:"):
        raise HTTPException(404)
    amount = float(m["status"].split(":")[1])
    ledger.add_entry({"type": "payment_received", "amount": amount, "customer_id": cid},
                     raw_text="(bank transfer, confirmed)", engine="paylink")
    ledger.set_message(b.message_id, status="confirmed")
    return {"customer": ledger.customer_summary(cid), "thread": ledger.thread(cid)}


def reminder_with_paylink(request_base, phone, cid, msg):
    if not phone or not msg:
        return msg
    s = ledger.customer_summary(cid) or {}
    if (s.get("owes_me") or 0) <= 0:
        return msg
    return msg + f"\n\n💳 Pay here: {pay_link(request_base, phone, cid, s['owes_me'])}"


# ---------------------------------------------------------------- 🧾 receipt after a record

RECEIPT = {
    "English": {"sale": "Thank you for buying {item}for {amt} from {shop} today. 🙏",
                "credit_sale": "{shop}: you took {item}for {amt} on credit today.{due} You now owe {bal} in total.",
                "payment_received": "{shop}: we received {amt} from you today. Thank you! 🙏 Balance left: {bal}.",
                "due": " You promised to pay by {d}."},
    "Pidgin": {"sale": "Thank you as you buy {item}for {amt} from {shop} today. 🙏",
               "credit_sale": "{shop}: you carry {item}for {amt} on credit today.{due} Your total balance na {bal}.",
               "payment_received": "{shop}: we don collect {amt} from you today. Thank you! 🙏 Wetin remain: {bal}.",
               "due": " You talk say you go pay by {d}."},
    "Yoruba": {"sale": "Ẹ ṣé tí ẹ ra {item}ní {amt} lọ́wọ́ {shop} lónìí. 🙏",
               "credit_sale": "{shop}: ẹ mú {item}ní {amt} ní àwìn lónìí.{due} Gbogbo gbèsè yín jẹ́ {bal}.",
               "payment_received": "{shop}: a ti gba {amt} lọ́wọ́ yín lónìí. Ẹ ṣé o! 🙏 Èyí tó kù: {bal}.",
               "due": " Ẹ ṣèlérí láti san ní {d}."},
    "Hausa": {"sale": "Mun gode da kuka sayi {item}na {amt} daga {shop} yau. 🙏",
              "credit_sale": "{shop}: kun ɗauki {item}na {amt} bashi yau.{due} Jimillar bashinku {bal}.",
              "payment_received": "{shop}: mun karɓi {amt} daga gare ku yau. Mun gode! 🙏 Saura: {bal}.",
              "due": " Kun yi alkawarin biya kafin {d}."},
    "Igbo": {"sale": "Daalụ maka ịzụta {item}na {amt} n'aka {shop} taa. 🙏",
             "credit_sale": "{shop}: ị were {item}na {amt} n'ụgwọ taa.{due} Ngụkọta ụgwọ gị bụ {bal}.",
             "payment_received": "{shop}: anyị natara {amt} n'aka gị taa. Daalụ! 🙏 Ihe fọdụrụ: {bal}.",
             "due": " Ị kwere nkwa ịkwụ ụgwọ tupu {d}."},
}


def receipt(cid, rec_type, amount, item, due, shop, lang="English"):
    """A receipt for the customer after a record, in the trader's language (they can edit it before sending)."""
    words = RECEIPT.get(lang) or RECEIPT["English"]
    if rec_type not in words:
        return None
    s = ledger.customer_summary(cid) or {}
    goods = {"English": "goods", "Pidgin": "goods", "Yoruba": "ọjà", "Hausa": "kaya", "Igbo": "ngwa ahịa"}
    try:
        due_txt = dt.date.fromisoformat(due).strftime("%-d %b") if due else ""
    except ValueError:
        due_txt = due
    txt = words[rec_type].format(item=(item or goods.get(lang, "goods")) + " ", amt=f"₦{amount:,.0f}", shop=shop,
                                 bal=f"₦{(s.get('owes_me') or 0):,.0f}",
                                 due=words["due"].format(d=due_txt) if due else "")
    return "🧾 " + re.sub(r"\s{2,}", " ", txt)


# ---------------------------------------------------------------- ⏰ automatic reminders on the promised day

def run_due_reminders(base=None, today=None, send=True):
    """For every trader's book: draft today's reminders (once a day) and WhatsApp the trader a summary."""
    today = today or dt.date.today()
    base = (base or os.getenv("PUBLIC_URL") or "").rstrip("/")
    done = 0
    if not os.path.isdir(ledger.BOOKS_DIR):
        return 0
    for f in os.listdir(ledger.BOOKS_DIR):
        if not f.endswith(".db"):
            continue
        phone = f[:-3]
        with _lock, _db() as c:
            if c.execute("SELECT 1 FROM auto_runs WHERE phone=? AND day=?", (phone, today.isoformat())).fetchone():
                continue
            c.execute("INSERT INTO auto_runs VALUES (?,?)", (phone, today.isoformat()))
        u = _user(phone)
        lang = u.get("lang") if u.get("lang") in insights.TEMPLATES else "Pidgin"
        due = []
        with _in_book(phone):
            for d in ledger.debtors(today):
                if not d.get("due_date") or d["due_date"] > today.isoformat() or not d.get("customer_id"):
                    continue
                msg, _ = insights.reminder(d["customer"], lang, u.get("shop") or "your trader", today,
                                           customer_id=d["customer_id"])
                if base:
                    msg = reminder_with_paylink(base, phone, d["customer_id"], msg)
                ledger.add_message(d["customer_id"], msg, sender="tradevoice", kind="reminder", status="draft")
                due.append(d)
        if due and send and os.getenv("WHATSAPP_TOKEN"):
            try:
                import whatsapp

                lines = "\n".join(f"• {d['customer']}: ₦{d['balance']:,.0f}" for d in due[:8])
                whatsapp.send_text(phone, f"📌 {len(due)} customer(s) promised to pay today:\n{lines}\n\n"
                                          f"Your reminders are ready (with a pay link). Open: {base}/app")
            except Exception as e:  # noqa: BLE001 - WhatsApp may not reach them (24 h rule); drafts are still there
                print(f"daily summary not sent: {e}")
        done += len(due)
    return done


def start_scheduler():
    def loop():
        while True:
            try:
                run_due_reminders()
            except Exception as e:  # noqa: BLE001
                print(f"auto reminders failed: {type(e).__name__}: {e}")
            time.sleep(1800)
    if os.getenv("AUTO_REMINDERS", "1") == "1":
        threading.Thread(target=loop, daemon=True).start()


# ---------------------------------------------------------------- 🔒 PIN lock

class Pin(BaseModel):
    pin: str = ""
    old: str = ""


def _pin_hash(phone, pin):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), phone.encode(), 100_000).hex()


def has_pin(phone):
    return bool(_user(phone).get("pin_hash"))


def unlocked(phone, token):
    u = UNLOCKS.get(token or "")
    return bool(u and u[0] == phone and u[1] > time.time())


@router.post("/api/auth/pin")
def pin_set(b: Pin, request: Request):
    phone = _phone(request)
    if has_pin(phone) and not unlocked(phone, request.headers.get("x-tv-unlock")):
        raise HTTPException(403, "Enter your PIN first.")
    if not re.fullmatch(r"\d{4}", b.pin or ""):
        raise HTTPException(400, "The PIN is 4 numbers.")
    with _lock, _db() as c:
        c.execute("UPDATE users SET pin_hash=? WHERE phone=?", (_pin_hash(phone, b.pin), phone))
    token = secrets.token_urlsafe(24)
    UNLOCKS[token] = (phone, time.time() + UNLOCK_HOURS * 3600)
    return {"ok": True, "unlock": token}


@router.delete("/api/auth/pin")
def pin_remove(request: Request):
    phone = _phone(request)
    if not unlocked(phone, request.headers.get("x-tv-unlock")):
        raise HTTPException(403, "Enter your PIN first.")
    with _lock, _db() as c:
        c.execute("UPDATE users SET pin_hash=NULL WHERE phone=?", (phone,))
    return {"ok": True}


@router.post("/api/auth/unlock")
def pin_check(b: Pin, request: Request):
    phone = _phone(request)
    fails, until = PIN_FAILS.get(phone, (0, 0))
    if until > time.time():
        raise HTTPException(429, f"Too many tries. Wait {int((until - time.time()) // 60) + 1} minutes.")
    if not hmac.compare_digest(_user(phone).get("pin_hash") or "", _pin_hash(phone, b.pin or "")):
        fails += 1
        PIN_FAILS[phone] = (0, time.time() + 300) if fails >= 5 else (fails, 0)
        raise HTTPException(400, "Wrong PIN." + (" Wait 5 minutes." if fails >= 5 else f" {5 - fails} tries left."))
    PIN_FAILS.pop(phone, None)
    token = secrets.token_urlsafe(24)
    UNLOCKS[token] = (phone, time.time() + UNLOCK_HOURS * 3600)
    return {"ok": True, "unlock": token}


# ---------------------------------------------------------------- 📤 CSV export

@router.get("/api/export.csv")
def export_csv(request: Request):
    with ledger.conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT e.created_at, e.type, e.amount, COALESCE(cu.name, e.customer) AS customer, e.item, e.quantity, "
            "e.unit, e.due_date, e.raw_text, e.demo FROM entries e LEFT JOIN customers cu ON cu.id=e.customer_id "
            "ORDER BY e.created_at")]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=["created_at", "type", "amount", "customer", "item", "quantity", "unit",
                                        "due_date", "raw_text", "demo"])
    w.writeheader()
    w.writerows(rows)
    return Response("﻿" + out.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="tradevoice-book-{dt.date.today()}.csv"'})
