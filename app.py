"""TradeVoice — voice & photo bookkeeping, debt tracking and money insights for Nigerian market traders.

python app.py            (GRADIO_SHARE=1 for a public link, e.g. when running on Brev)
"""
import datetime as dt
import os
import tempfile

import gradio as gr
import pandas as pd

import insights
import ledger
import tts
from extract import TYPES, extract, extract_many

TYPE_LABELS = {"sale": "Sale (paid now)", "credit_sale": "Sale on credit (owes me)",
               "payment_received": "Debt paid back", "expense": "Expense"}
LABEL_TO_TYPE = {v: k for k, v in TYPE_LABELS.items()}
CONSENT = ("I agree that my voice note / photo is processed by AI to create my records. "
           "The audio or photo is deleted right after it is read.")
PHOTO_COLS = ["save", "type", "amount", "customer", "due_date", "item", "quantity", "unit", "check", "from line"]
SHOP_NAME = os.getenv("SHOP_NAME", "Chioma Stores")


def naira(x):
    return f"₦{x:,.0f}"


def _forget(path):
    try:
        os.remove(path)  # data minimisation: never keep raw audio or photos
    except (OSError, TypeError):
        pass


def risk_line(rec):
    """Warn before giving more credit to a customer with a bad record."""
    if rec["type"] != "credit_sale" or not rec.get("customer"):
        return ""
    r = ledger.customer_risk(rec["customer"])
    return f"🏷️ **Credit check:** {r['message']}  \n"


# ---------------------------------------------------------------- voice / text record tab

VOICE_TO_REPLY = {"English / Pidgin": "Pidgin", "Yoruba": "Yoruba", "Hausa": "Hausa", "Igbo": "Igbo"}


def spoken(rec, reply_lang, saved, balance=None):
    """Audio file reading the entry back (for traders who can't read), or None if voice is off or fails."""
    if not reply_lang or reply_lang == "Off" or rec.get("amount") in (None, ""):
        return None
    try:
        out = tts.speak(tts.confirmation_text(rec, reply_lang, balance=balance, saved=saved), reply_lang)
        return out["path"] if out else None
    except Exception as e:  # noqa: BLE001  - voice is a bonus; never break the flow
        print(f"voice reply failed: {type(e).__name__}: {e}")
        return None


def voice_status():
    engine = tts.backend()
    return (f"🔊 Voice replies on ({engine})." if engine else
            "🔇 Voice replies are off: add SPITCH_API_KEY to .env (or install requirements-tts.txt).")


def process(consent, audio_path, typed_text, voice_lang="English / Pidgin", reply_lang="Off"):
    blank = [gr.update()] * 8 + [None]
    if not consent:
        return ["⚠️ Please tick the consent box first."] + blank
    text, asr_info = (typed_text or "").strip(), ""
    if audio_path:
        try:
            from asr import transcribe

            res = transcribe(audio_path, voice_lang)
            text = res["text"]
            asr_info = f"🎙️ Speech → text: {res['engine']}, {res['latency_ms']} ms, language `{res['language']}`  \n"
            if res.get("note"):
                asr_info += f"⚠️ {res['note']}  \n"
        except Exception as e:
            return [f"⚠️ Could not transcribe ({type(e).__name__}: {e}). Type the entry instead."] + blank
        finally:
            _forget(audio_path)
    if not text:
        return ["⚠️ Record a voice note or type what happened."] + blank

    rec, meta = extract(text)
    warn = []
    if rec["amount"] is None:
        warn.append("No amount heard — please fill it in.")
    if rec["confidence"] < 0.6:
        warn.append("Low confidence — check every field before saving.")
    if rec["type"] == "credit_sale" and not rec["customer"]:
        warn.append("Credit sale without a customer name.")
    if rec.get("note"):
        warn.append(rec["note"])
    if meta["error"]:
        warn.append(f"AI service unavailable, used offline rules ({meta['error'][:80]}).")
    status = (asr_info + f"🧠 Understanding: {meta['engine']}, {meta['latency_ms']} ms, "
              f"confidence {rec['confidence']:.0%}  \n" + risk_line(rec) + "".join(f"⚠️ {w}  \n" for w in warn)
              + "**Check the details below, then press Confirm & save.**")
    return [status, text, TYPE_LABELS[rec["type"]], rec["item"] or "", rec["quantity"], rec["unit"] or "",
            rec["amount"], rec["customer"] or "", rec["due_date"] or "", spoken(rec, reply_lang, saved=False)]


def _valid_due(due):
    if not due:
        return True
    try:
        dt.date.fromisoformat(str(due))
        return True
    except ValueError:
        return False


def save(text, type_label, item, qty, unit, amount, customer, due, engine_note, reply_lang="Off"):
    if amount in (None, "") or float(amount) <= 0:
        return "⚠️ Amount is required before saving.", None
    if not _valid_due(due):
        return "⚠️ Due date must look like 2026-10-02.", None
    rec = {"type": LABEL_TO_TYPE[type_label], "item": item or None, "quantity": qty, "unit": unit or None,
           "amount": float(amount), "customer": (customer or "").strip() or None, "due_date": due or None}
    eid = ledger.add_entry(rec, raw_text=text, engine="voice/text")
    balance = None
    if rec["customer"]:
        balance = next((d["balance"] for d in ledger.debtors()
                        if ledger.customer_key(d["customer"]) == ledger.customer_key(rec["customer"])), None)
    msg = f"✅ Saved entry #{eid}: {type_label}, {naira(rec['amount'])}" + (
        f" — {rec['customer']}" if rec["customer"] else "")
    if balance:
        msg += f"  \n📒 {rec['customer']} now owes you {naira(balance)} in total."
    return msg, spoken(rec, reply_lang, saved=True, balance=balance)


# ---------------------------------------------------------------- photo tab

def read_photo(consent, image_path):
    if not consent:
        return "⚠️ Please tick the consent box first.", gr.update()
    if not image_path:
        return "⚠️ Take or upload a photo of your book page or receipt.", gr.update()
    try:
        from vision import read_notebook

        res = read_notebook(image_path)
    except Exception as e:
        return (f"⚠️ Could not read the photo ({type(e).__name__}: {str(e)[:120]}). "
                "You can type the lines in the box below instead."), gr.update()
    finally:
        _forget(image_path)
    if not res["text"]:
        return "No money records found in this photo. Try a clearer, flatter photo in good light.", ""
    return (f"📸 Read by {res['engine']} in {res['latency_ms']} ms. **Fix anything wrong below, then press "
            f"'Turn lines into entries'.** Unreadable bits are marked [?]."), res["text"]


def lines_to_table(lines_text):
    recs, meta = extract_many(lines_text)
    if not recs:
        return "No lines with money found.", pd.DataFrame(columns=PHOTO_COLS)
    rows = []
    for r in recs:
        checks = []
        if r["amount"] is None:
            checks.append("add amount")
        if r["confidence"] < 0.6:
            checks.append("low confidence")
        if r.get("note"):
            checks.append(r["note"])
        if r["type"] == "credit_sale" and r.get("customer"):
            risk = ledger.customer_risk(r["customer"])
            if risk["level"] in ("medium", "high"):
                checks.append(risk["message"])
        rows.append({"save": r["amount"] is not None, "type": r["type"], "amount": r["amount"],
                     "customer": r["customer"] or "", "due_date": r["due_date"] or "", "item": r["item"] or "",
                     "quantity": r["quantity"], "unit": r["unit"] or "", "check": "; ".join(checks) or "ok",
                     "from line": r["line"]})
    msg = (f"🧠 {len(rows)} entries found ({meta['engine']}, {meta['latency_ms']} ms). Edit the table — "
           f"`type` must be one of {', '.join(TYPES)}. Untick `save` to skip a row. Then press **Save all ticked**.")
    if meta["error"]:
        msg += f"  \n⚠️ AI unavailable, used offline rules ({meta['error'][:80]})."
    return msg, pd.DataFrame(rows, columns=PHOTO_COLS)


def _truthy(v):
    return v is True or str(v).strip().lower() in ("true", "1", "yes", "y", "✓")


def save_table(df):
    if df is None or len(df) == 0:
        return "Nothing to save."
    saved, problems = 0, []
    for i, row in pd.DataFrame(df).iterrows():
        if not _truthy(row.get("save")):
            continue
        n = i + 1
        typ = str(row.get("type") or "").strip()
        try:
            amount = float(str(row.get("amount")).replace(",", "").replace("₦", ""))
        except ValueError:
            amount = 0
        due = str(row.get("due_date") or "").strip()
        if typ not in TYPES:
            problems.append(f"row {n}: type must be one of {', '.join(TYPES)}")
            continue
        if not amount or amount != amount or amount <= 0:  # also catches NaN
            problems.append(f"row {n}: amount missing")
            continue
        if not _valid_due(due):
            problems.append(f"row {n}: due date must look like 2026-10-02")
            continue
        qty = row.get("quantity")
        ledger.add_entry({"type": typ, "amount": amount, "customer": str(row.get("customer") or "").strip() or None,
                          "due_date": due or None, "item": str(row.get("item") or "").strip() or None,
                          "quantity": None if qty in (None, "") or pd.isna(qty) else float(qty),
                          "unit": str(row.get("unit") or "").strip() or None},
                         raw_text=str(row.get("from line") or ""), engine="photo")
        saved += 1
    return f"✅ Saved {saved} entries." + ("  \n⚠️ Not saved: " + "; ".join(problems) if problems else "")


# ---------------------------------------------------------------- dashboards

def today_view():
    s = ledger.day_summary()
    md = (f"### Today ({s['date']}) — {s['count']} entries\n"
          f"| | |\n|---|---|\n"
          f"| Sales | **{naira(s['sales'])}** (cash {naira(s['cash_sales'])}, credit {naira(s['credit_sales'])}) |\n"
          f"| Debts collected | {naira(s['payments_received'])} |\n"
          f"| Expenses | {naira(s['expenses'])} |\n"
          f"| **Sales − expenses** | **{naira(s['profit'])}** |\n"
          f"| Cash in hand change | {naira(s['cash_in_hand_change'])} |")
    rows = ledger.entries(limit=50)
    df = pd.DataFrame([{"id": r["id"], "time": r["created_at"][5:16].replace("T", " "),
                        "type": TYPE_LABELS[r["type"]], "item": r["item"], "qty": r["quantity"],
                        "amount": naira(r["amount"]), "customer": r["customer"], "due": r["due_date"],
                        "via": r["engine"]}
                       for r in rows]).fillna("") if rows else pd.DataFrame(columns=["id", "time", "type", "amount"])
    return md, df


def debtors_view():
    ds = ledger.debtors()
    names = [d["customer"] for d in ds]
    if not ds:
        return "Nobody owes you money right now. 🎉", pd.DataFrame(), gr.update(choices=[], value=None)
    total = sum(d["balance"] for d in ds)
    overdue = sum(d["balance"] for d in ds if d["overdue"])
    md = f"### {len(ds)} customers owe you **{naira(total)}**" + (
        f" — **{naira(overdue)} overdue** 🔴" if overdue else "")
    df = pd.DataFrame([{"customer": d["customer"], "balance": naira(d["balance"]), "took": naira(d["owed"]),
                        "paid back": naira(d["paid"]), "promised by": d["due_date"] or "—",
                        "status": f"🔴 {d['days_late']} days late" if d["overdue"] else "🟢 on time",
                        "credit check": ledger.customer_risk(d["customer"])["level"]} for d in ds])
    return md, df, gr.update(choices=names, value=names[0])


def make_reminder(customer, language, shop):
    if not customer:
        return "Pick a customer.", ""
    msg, link = insights.reminder(customer, language, shop or SHOP_NAME)
    if not msg:
        return f"{customer} doesn't owe you anything. 🎉", ""
    return msg, (f"### [📲 Open in WhatsApp]({link})\nWhatsApp opens with the message ready — you choose the "
                 f"contact and press send yourself.")


def insights_view():
    f = insights.forecast()
    if not f:
        return "Record a few days of sales to see your forecast.", pd.DataFrame()
    top = insights.top_items()
    md = [f"### Next 7 days: expect about **{naira(f['week_sales'])}** in sales",
          f"- 💵 Cash you should have left after normal expenses: **{naira(f['expected_cash'])}** "
          f"(about {f['cash_share']:.0%} of your sales are paid on the spot).",
          f"- 📅 **{f['busiest_day']}** is your busiest day — stock up the day before."]
    if f["due_soon"]:
        md.append("- 📥 Debts promised this week: " + ", ".join(
            f"{d['customer']} {naira(d['balance'])} ({d['due_date']})" for d in f["due_soon"]))
    if f["overdue"]:
        md.append(f"- 🔴 Overdue: {naira(sum(d['balance'] for d in f['overdue']))} — send reminders from "
                  f"the **Who owes me** tab.")
    if top:
        md.append("\n### Best sellers (last 14 days)")
        md += [f"{i}. **{t['item']}** — {naira(t['revenue'])}" + (
            f" ({t['qty']:.0f} {t['unit']}{'s' if t['qty'] != 1 else ''})" if t["qty"] and t["unit"] else "")
            for i, t in enumerate(top, 1)]
        md.append(f"\n💡 Restock tip: make sure **{top[0]['item']}** and **{top[1]['item'] if len(top) > 1 else ''}** "
                  f"don't run out before {f['busiest_day']}.")
    md.append("\n_Forecast = your average sales for each weekday over the last 4 weeks. Simple and explainable, "
              "not a guarantee._")
    df = pd.DataFrame([{"day": f"{p['weekday'][:3]} {p['date'][5:]}", "expected sales": naira(p["sales"]),
                        "debts due in": naira(p["collections"]) if p["collections"] else ""} for p in f["plan"]])
    return "\n".join(md), df


def profile_view():
    p = ledger.credit_profile()
    if not p:
        return "No records yet. Record a few days of sales to build your profile."
    lines = [f"## Business record score: {p['score']}/100 — {p['band']}",
             f"Based on **{p['span_days']} days** of records. Average daily sales **{naira(p['avg_daily_sales'])}**, "
             f"sales minus expenses **{naira(p['profit'])}**, money owed to you **{naira(p['outstanding'])}**"
             + (f" ({naira(p['overdue'])} overdue)." if p["overdue"] else "."),
             "", "| Factor | Points | Why |", "|---|---|---|"]
    for name, (pts, mx, why) in p["parts"].items():
        lines.append(f"| {name} | {pts:.0f} / {mx} | {why} |")
    lines += ["", "> ℹ️ **How this works:** a simple, published formula over your own records — no hidden AI "
                  "judgement. It is an *indicator* to help you talk to a lender, cooperative or ajo group. "
                  "It is **not** a credit decision; a person must review any loan."]
    if p["has_demo_data"]:
        lines.append("\n> 🧪 Includes demo data seeded for the hackathon presentation.")
    return "\n".join(lines)


def download_statement(shop):
    page = insights.statement_html(shop or SHOP_NAME)
    if not page:
        return None
    path = os.path.join(tempfile.gettempdir(), f"business-statement-{dt.date.today().isoformat()}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path


def chat(question, history):
    answer, engine = insights.ask(question)
    return answer + (f"\n\n_— {engine}_" if engine != "rules" else "")


def do_delete(entry_id):
    if not entry_id:
        return "Enter an entry id."
    return "🗑️ Deleted." if ledger.delete_entry(entry_id) else "No entry with that id."


def do_wipe(confirm):
    if confirm != "DELETE":
        return "Type DELETE (capital letters) to confirm."
    return f"🗑️ Deleted all {ledger.wipe()} entries. Nothing is kept."


# ---------------------------------------------------------------- UI

THEME = gr.themes.Soft(primary_hue="green")
GRADIO6 = int(gr.__version__.split(".")[0]) >= 6  # Gradio 6 moved `theme` from Blocks() to launch()

with gr.Blocks(title="TradeVoice", **({} if GRADIO6 else {"theme": THEME})) as demo:
    gr.Markdown("# 🗣️💰 TradeVoice\nSpeak it or snap your book — we keep your records, chase who owes you, "
                "and show where your money is going.")
    consent = gr.Checkbox(label=CONSENT, value=False)
    shop = gr.Textbox(label="Shop name (used on reminders & statement)", value=SHOP_NAME)

    with gr.Tab("🎙️ Speak"):
        with gr.Row():
            with gr.Column():
                voice_lang = gr.Radio(["English / Pidgin", "Yoruba", "Hausa", "Igbo"], value="English / Pidgin",
                                      label="Voice note language")
                audio = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Voice note")
            typed = gr.Textbox(label="…or type it", lines=3,
                               placeholder="I sell 3 bags of rice give Mama Tunde, 45k, she go pay Friday")
        with gr.Row():
            reply_lang = gr.Radio(["Off"] + tts.REPLY_LANGS, value="Pidgin",
                                  label="🔊 Read it back to me in (for traders who prefer listening)")
            gr.Markdown(voice_status())
        voice_lang.change(lambda v: VOICE_TO_REPLY.get(v, "Pidgin"), voice_lang, reply_lang)
        go = gr.Button("Process", variant="primary")
        status = gr.Markdown()
        heard_audio = gr.Audio(label="🔊 What I heard", autoplay=True, interactive=False)
        with gr.Group():
            transcript = gr.Textbox(label="What we heard (edit if wrong)")
            with gr.Row():
                f_type = gr.Dropdown(list(TYPE_LABELS.values()), label="Type", value=TYPE_LABELS["sale"])
                f_amount = gr.Number(label="Amount (₦)")
                f_customer = gr.Textbox(label="Customer")
                f_due = gr.Textbox(label="Promised pay date (YYYY-MM-DD)")
            with gr.Row():
                f_item = gr.Textbox(label="Item")
                f_qty = gr.Number(label="Quantity")
                f_unit = gr.Textbox(label="Unit")
        confirm = gr.Button("✅ Confirm & save")
        saved = gr.Markdown()
        saved_audio = gr.Audio(label="🔊 Saved", autoplay=True, interactive=False)
        go.click(process, [consent, audio, typed, voice_lang, reply_lang],
                 [status, transcript, f_type, f_item, f_qty, f_unit, f_amount, f_customer, f_due, heard_audio])
        confirm.click(save, [transcript, f_type, f_item, f_qty, f_unit, f_amount, f_customer, f_due, status,
                             reply_lang], [saved, saved_audio])

    with gr.Tab("📸 Snap your book"):
        gr.Markdown("Take a photo of a page of your record book or a receipt. Flat page, good light, whole page in view.")
        photo = gr.Image(sources=["upload", "webcam"], type="filepath", label="Book page / receipt")
        read_btn = gr.Button("Read photo", variant="primary")
        photo_status = gr.Markdown()
        photo_lines = gr.Textbox(label="Lines read from the photo (edit, or type/paste lines yourself)", lines=6)
        to_table = gr.Button("Turn lines into entries")
        table_status = gr.Markdown()
        table = gr.Dataframe(headers=PHOTO_COLS, interactive=True, wrap=True)
        save_all = gr.Button("✅ Save all ticked")
        save_all_out = gr.Markdown()
        read_btn.click(read_photo, [consent, photo], [photo_status, photo_lines])
        to_table.click(lines_to_table, photo_lines, [table_status, table])
        save_all.click(save_table, table, save_all_out)

    with gr.Tab("📊 Today"):
        t_md, t_df = gr.Markdown(), gr.Dataframe(interactive=False)
        with gr.Row():
            del_id = gr.Number(label="Entry id to delete", precision=0)
            del_btn = gr.Button("Delete entry")
        del_out = gr.Markdown()
        del_btn.click(do_delete, del_id, del_out).then(today_view, None, [t_md, t_df])

    with gr.Tab("📒 Who owes me"):
        d_md, d_df = gr.Markdown(), gr.Dataframe(interactive=False)
        gr.Markdown("### 📲 Send a polite reminder")
        with gr.Row():
            r_who = gr.Dropdown(label="Customer", choices=[])
            r_lang = gr.Radio(["Pidgin", "English", "Yoruba"], value="Pidgin", label="Language")
        r_btn = gr.Button("Write reminder")
        r_msg = gr.Textbox(label="Message (edit before sending)", lines=3)
        r_link = gr.Markdown()
        r_btn.click(make_reminder, [r_who, r_lang, shop], [r_msg, r_link])

    with gr.Tab("🔮 Insights"):
        i_md, i_df = gr.Markdown(), gr.Dataframe(interactive=False)

    with gr.Tab("💬 Ask my book"):
        gr.ChatInterface(chat, examples=["How much Oga Emeka owe me?", "Wetin sell pass this week?",
                                         "How much I go make next week?", "How my market today?"])

    with gr.Tab("🏦 Credit profile"):
        p_md = gr.Markdown()
        y_btn = gr.Button("📒 My year so far (sales, spending by type, rent & levies)")
        y_md = gr.Markdown()
        y_btn.click(lambda: "```\n" + insights.year_record_text() + "\n```", None, y_md)
        st_btn = gr.Button("⬇️ Download statement for lender / cooperative")
        st_file = gr.File(label="Business record statement (HTML — open and print to PDF)")
        st_btn.click(download_statement, shop, st_file)

    with gr.Tab("🔒 My data"):
        gr.Markdown("- Voice notes and photos are read and **deleted immediately**; only the text entries are stored.\n"
                    "- Speech recognition runs on **our own GPU server (NVIDIA Brev)** — your voice is not sent "
                    "to a third-party speech service.\n"
                    "- Nothing is saved until **you** confirm it. Reminders are only sent if **you** press send.\n"
                    "- Numbers (totals, forecast, score) are calculated by simple published rules; the AI only reads "
                    "your notes and phrases answers.\n- You can delete everything at any time.")
        wipe_box = gr.Textbox(label="Type DELETE to erase all your records")
        wipe_btn = gr.Button("Erase all my data", variant="stop")
        wipe_out = gr.Markdown()
        wipe_btn.click(do_wipe, wipe_box, wipe_out)

    refresh = gr.Button("🔄 Refresh dashboards")
    for trigger in (refresh.click, demo.load, confirm.click, save_all.click, wipe_btn.click):
        trigger(today_view, None, [t_md, t_df])
        trigger(debtors_view, None, [d_md, d_df, r_who])
        trigger(insights_view, None, [i_md, i_df])
        trigger(profile_view, None, p_md)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", 7860)),
                share=os.getenv("GRADIO_SHARE") == "1", **({"theme": THEME} if GRADIO6 else {}))
