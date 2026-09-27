# TradeVoice 🗣️📸💰
**Speak it or snap your book: bookkeeping, debt tracking and money insights for Nigerian market traders.**

Built for **Come Build with AI** (GOMYCODE × NVIDIA, 27 Sep 2026). Primary prize: **Kredete Financial Inclusion Award**.

> ✅ **Prep checklist for the 4 of us: [`docs/PREP_PLAN.md`](docs/PREP_PLAN.md)** · 📊 **Test results: [`docs/RESULTS.md`](docs/RESULTS.md)**
>
> 👋 **New to the team? Read [`TEAM_GUIDE.md`](TEAM_GUIDE.md) first.** It covers who does what, the plan for the day and the rules we must follow.
> **WhatsApp plan:** [`docs/WHATSAPP.md`](docs/WHATSAPP.md). Traders will use TradeVoice inside WhatsApp; the web app is the dashboard.
> Other docs: [`docs/RULES_CHECKLIST.md`](docs/RULES_CHECKLIST.md) · [`docs/PITCH.md`](docs/PITCH.md) (video script + project card) ·
> [`docs/SUBMISSION.md`](docs/SUBMISSION.md) (disclosure + test results to fill in) · [`docs/RESEARCH.md`](docs/RESEARCH.md)

---

## The problem
Nigerian market traders sell on credit and keep records in their heads or in a notebook. They forget who owes them, they
don't know their real profit, and without records they can't get a loan from a microfinance bank or cooperative.

## What TradeVoice does
**You talk. TradeVoice keeps the book.** (`python web.py`) A trader logs in with their phone number, taps the big
mic and says what happened. TradeVoice shows what it understood (customer, amount, item, credit or paid, pay-by date,
with a "?" on anything it isn't sure of), the trader taps **Save**, and the book updates. Home shows money in and out
today and the money to collect; Customers is a ledger per person ("You gave / You got"); Ask answers questions from
the book by voice. The same brain (`converse.py`) runs the WhatsApp bot, on the same book for the same number.

| Feature | What the trader does | What happens |
|---|---|---|
| 💬 **Talk to TradeVoice** | One conversation, switching language whenever they like: *"Mama Tunde dey owe me forty-five thousand"* → *"yes"* → *"Ṣé mo ní gbèsè lọ́wọ́ Alhaji?"* → *"Remind her tomorrow"* | Each message is routed (record / yes-no / question / reminder) and answered **in the language it was said in**, from the same book. It remembers who "her/him/am" is, fills a missing amount from the next message ("How much?" → "50k"), matches "Alhaji" to the right Alhaji (the one you owe vs the one who owes you), and sets reminders that show up on the day with the WhatsApp message ready. Works offline. `converse.py`, `eval/test_converse.py` (18/18). Typed messages switch language freely; for voice notes the trader taps the language once (the speech engine needs it) |
| 🎙️ **Speak** | Sends a voice note: *"I sell 3 bags of rice give Mama Tunde, 45k, she go pay Friday"* (or in Yoruba, Hausa, Igbo) | **Intron Sahara** speech-to-text (built for Nigerian languages and mixed sentences) → text → **AI brain on our NVIDIA Brev GPU** → entry: *credit sale, ₦45,000, Mama Tunde, due Fri* → trader confirms |
| 📸 **Snap your book** | Takes a photo of a notebook page or receipt | Vision AI reads every line → editable table → trader ticks and saves all |
| 🔊 **Voice replies** | Can't read? Just listen | The app reads the entry back aloud in Pidgin, English, Yoruba, Hausa or Igbo before and after saving (Intron Sahara voices; Spitch, then free MMS voices as backup) |
| 🏷️ **Credit check** | Records a credit sale | Warning if that customer is already late: *"⛔ Oga Emeka already owes ₦30,600 and is 18 days late"* |
| 📒 **Who owes me** | Opens the tab | Everyone who owes, how much, how late. Payments clear the oldest debt first |
| 📲 **WhatsApp reminder** | Picks a debtor + Pidgin / English / Yoruba | Polite reminder opens in WhatsApp; the trader presses send themselves |
| 🔮 **Insights** | Opens the tab | Next 7 days' sales forecast, expected cash, debts coming in, busiest day, best sellers, restock tip |
| 💬 **Ask my book** | *"How much Mama Tunde owe me?"*, *"Wetin sell pass this week?"* | Answer in their own style, from their own numbers only |
| 🏦 **Credit profile + statement** | Downloads a statement | A transparent 0–100 record score + weekly summary to show a lender, cooperative or ajo group |
| 🎤 **Ask my book, in your language** | "Ìrẹsì mélòó ni mo tà lóṣù yìí?" · "Shinkafa nawa na sayar a wannan makon?" | Voice or text question in English, Pidgin, Yoruba, Hausa or Igbo → the AI only turns it into a search (item, period, sold/bought/owed) → numbers added up from the book → answer as text + voice note in the same language. Works offline with word lists. `eval/test_askbook.py` |
| 🔊 **Read it to me** + 🌍 **App language** | One big button on Today, Debts, Insights, Credit profile; language picker at the top | The screen is spoken as a short voice note in English, Pidgin, Yoruba, Hausa or Igbo (numbers from the book, fixed sentences, `readaloud.py`); tab names, main buttons and consent switch language (`ui_text.py`, native-speaker check) |
| 📝 **Long voice notes** | Talks about many things in one note | Every money item in a tickable table, a simple-English summary on screen, the same summary as a voice note in their language, tips computed by code (rent per month/day, debt totals), unclear parts asked; every AI number checked (`note.py`, `eval/test_note.py`) |
| 🧾 **Who I owe** | "Alhaji give me 10 bags on credit, I go pay Friday" / "I don pay Alhaji 50k" | The trader's OWN debts to suppliers/lenders, with promised dates and voice replies; goods on credit count as spending, borrowed cash doesn't |
| 📒 **My year so far** | One button | Sales, money spent **by type** (restock, rent, levies, transport, power, staff), monthly totals, rent & levy payments to keep receipts for. Also in the statement. Facts from the book only, no tax advice (tax research in progress: `docs/FINANCE_RESEARCH.md`) |
| 🔒 **My data** | - | Consent first, audio and photos deleted after reading, nothing saved without confirmation, delete-everything button |

**Data model (ledger.py, SQLite):** `customers(id, name, phone, notes, language, last_read_at)` · `entries(…, customer_id)` ·
`messages(id, customer_id, sender, kind, content, status)` (notes and reminder drafts) · `reminders(…, customer_id)`.
Customers are never identified by name alone: two "Feranmi"s stay two customers, and the chat asks "Which Feranmi?".

## How it works
```
 Voice note ─► Intron Sahara speech-to-text (Spitch backup) ─────────────────────┐
                                                                                 ├─► text lines
 Book photo ─► vision model on our NVIDIA Brev GPU (NVIDIA cloud backup) ─────────┘
                                         │
                                         ▼
          NVIDIA Nemotron LLM (build.nvidia.com) ─► entries ◄─ rule-based parser (offline fallback
                                         │                      + checks every amount against the text)
                                         ▼
                    Trader CONFIRMS / edits ─► SQLite ledger
                                         │
     ┌──────────────┬───────────────┬────┴─────────┬──────────────────┬──────────────────┐
   Today      Who owes me +     Insights +     Ask my book        Credit profile +
              reminders         forecast       (LLM phrases       lender statement
                                               computed facts)
```
**Design rule: AI reads and phrases; plain Python does the maths.** Totals, balances, the forecast and the score are
deterministic and explainable, so the AI can never invent a number in your books.

## Code map
| File | What it does |
|---|---|
| `web.py` + `web/` | 📱 **The app**: no login (each phone gets its own book; phone-number login kept for later), Home · Customers · big mic (Talk) · Insights · Me, confirmation card before anything is saved, 5 languages, dark mode, offline voice-note queue (`web/sw.js`), WhatsApp view. `web.py` is a small API over the same modules. Design: `docs/UI_RESEARCH.md` |
| `accounts.py` | 🔐 Log in with your phone number (code on WhatsApp, or "Confirm with WhatsApp" = send `LOGIN <word>` from that phone, or demo code); one book per number (`books/<number>.db`); hashed codes and sessions; `eval/test_auth.py` |
| `extras.py` | 🏦 Lender link (consent, 1/7/30 days, revoke, view count) · 💳 pay link in reminders (Paystack checkout + signed webhook settles the debt; or bank details + "I have paid") · ⏰ reminder drafts on the promised day · 🧾 receipts · 🔒 server-checked PIN · 📤 CSV export; `eval/test_extras.py` |
| `assistant.py` | 🎙️ Ask TradeVoice: explains each screen, answers spoken questions; the example questions are answered exactly from the book (`book_answer`), AI answers are checked against the book's numbers |
| Wholesale (in `ledger.py`, `insights.py`, `extras.py`, `converse.py`) | **Credit limit** per customer (contact sheet, or say "Iya Bisi limit 30k"): a credit sale over it is flagged on the card, said out loud, and needs "Sell anyway" · **Margin per item** (sell price vs buy price per unit, only where quantities were said) · **Cheapest supplier** per item · **Per-customer statement** (open items, running balance, due date, pay link; "send Mama Tunde her statement") · **Repeat orders** ("Mama Tunde buys 4 crates of eggs every Friday": suggested as a draft on that day, never saved without Save); `eval/test_wholesale.py` |
| `tax.py` | Tax records + general tax information (9 sourced facts, 5 languages); never says what anyone owes |
| `eval/test_demo_flow.py` | The 90-second demo end to end: speak → card → change → save → who owes most → reminder with pay link → Yoruba question on the same book |
| `app.py` | Gradio screens (all features, used as the admin/backup view at `/admin`) |
| `llm.py` | Every NVIDIA API call, with automatic fallback to the next model if one is deprecated |
| `check_models.py` | Lists the models your key can see and tests ours. **Run this first** |
| `eval/lang_check.py` | Scoreboard: which model reads/understands Yoruba, Hausa, Igbo, Pidgin best |
| `asr.py` | Speech-to-text: **Intron Sahara** (default, Nigerian languages), Spitch as backup, local Whisper/omniASR offline; `transcribe_auto` hears the language the trader actually spoke |
| `requirements-omni.txt` | Extra install for Yoruba/Hausa/Igbo voice (Brev GPU only) |
| `asr_server/server.py` | Optional standalone speech API (FastAPI) for a Brev GPU, same engines as `asr.py` |
| `vision.py` | Book photo → text lines (shrinks the image to fit NVIDIA's inline-image limit) |
| `extract.py` | Text → entries. LLM first; rules as fallback and amount cross-check. `extract()` for one, `extract_many()` for many lines |
| `web/customers.js` | 👥 **Customers**: balance-first list; each customer is a money timeline (running balance, notes, receipts, reminder drafts with Send / Edit / Cancel, "customer says they paid" to confirm); "You gave / You got"; two columns on desktop |
| `ui_text.py` | **All screen words in one place** (English, Pidgin, Yorùbá, Hausa, Igbo; English fallback, never a raw key); used by the web app, the website and WhatsApp. Native-speaker check pending |
| `whatsapp.py` | 📲 WhatsApp bot (Meta Cloud API webhook at `/whatsapp/webhook`, inside `web.py`): sign-up in chat, voice notes, photos, buttons, voice-note replies; `eval/test_whatsapp.py` |
| `photo.py` | Notebook photo → draft rows → tick/fix → save (shared by web and WhatsApp) |
| `converse.py` | 💬 One conversation over one book: routes each message (record, yes/no, question, reminder), follows the language per message, remembers who "her/him" is. Channel-free: the WhatsApp bot can call `reply()` as it is |
| `ledger.py` | SQLite storage, daily summary, debtors (oldest debt paid first), customer credit check, record score |
| `insights.py` | Forecast, best sellers, WhatsApp reminders, Ask-my-book, lender statement |
| `seed_demo.py` | 3 weeks of **synthetic, flagged** demo history for the presentation |
| `eval/run_eval.py` + `eval/cases*.jsonl` | Accuracy and speed test with 95% ranges, per language and per trap (`docs/TESTING.md`) |
| `eval/make_hard_cases.py` | Generates 211 trap phrases in 5 languages (`eval/cases_hard.jsonl`) |

## Quick start (laptop, no GPU, no key: everything except photos works offline)
```bash
git clone https://github.com/Godzilla-lab/tradevoice.git && cd tradevoice
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed_demo.py --wipe      # demo history (optional)
python app.py                   # open http://localhost:7860
python eval/run_eval.py         # accuracy report (hard traps: --cases eval/cases_hard.jsonl, see docs/TESTING.md)
```
Tick the consent box, then try typing `I sell 2 crates of eggs give Oga Emeka, 10,800, he go pay Monday`.

With AI switched on:
```bash
cp .env.example .env            # put your nvapi-... key in it
set -a; source .env; set +a
python check_models.py          # which NVIDIA models work with your key
python app.py
```

## Run on NVIDIA Brev (event day)
**Who does what (decided 25 Sep):**
| Job | Where | Why |
|---|---|---|
| **Hear** the voice note (speech → text) | **Intron Sahara API** (Spitch as backup) | Best we found for English, Pidgin, Yoruba, Hausa, Igbo, incl. mixed-language sentences |
| **Understand** the note (AI brain, LLM) | **Our Brev GPU** (vLLM), NVIDIA cloud models as backup, offline rules last | No cloud queue/timeouts; our own model |
| **Read** notebook photos (vision model) | **Our Brev GPU** (vLLM), NVIDIA cloud as backup | Same |
| **Speak** replies (voice notes) | **Intron Sahara TTS** (Spitch, then MMS as backup) | Native Yoruba, Hausa, Igbo voices + Nigerian English (for English/Pidgin) |
| App + WhatsApp webhook | Our Brev GPU instance | Public link |

1. Activate the voucher → create a GPU instance. **Two models share the GPU**: with 4-bit (AWQ) models a 24 GB L4 should
   fit both (~6 GB + ~8 GB); a 48 GB L40S gives room for full-size models. ⚠️ Memory figures not tested yet: check `nvidia-smi`.
2. On the instance:
   ```bash
   git clone https://github.com/Godzilla-lab/tradevoice.git && cd tradevoice
   pip install -r requirements.txt vllm
   # terminal 1: the AI brain (swap in NCAIR1/N-ATLaS, Nigeria's own 8B model, if it fits / scores better)
   vllm serve Qwen/Qwen2.5-7B-Instruct-AWQ --port 8001 --gpu-memory-utilization 0.35 --max-model-len 4096
   # terminal 2: the photo reader
   vllm serve Qwen/Qwen2.5-VL-7B-Instruct-AWQ --port 8002 --gpu-memory-utilization 0.45 --max-model-len 8192
   ```
3. `.env` on the instance (keys never in git):
   ```
   LOCAL_LLM_URL=http://localhost:8001/v1
   LOCAL_VISION_URL=http://localhost:8002/v1
   LLM_MODELS=local,nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3-super-120b-a12b
   VISION_MODELS=local,meta/llama-3.2-11b-vision-instruct
   INTRON_API_KEY=...        # hearing AND voice replies (defaults to Intron for both when this is set)
   SPITCH_API_KEY=...        # optional backup voice + backup hearing
   NVIDIA_API_KEY=...        # cloud backup
   ```
   (`LOCAL_LLM_MODEL` / `LOCAL_VISION_MODEL` if you serve different models.)
4. Check and start:
   ```bash
   set -a; source .env; set +a
   python check_models.py        # "AI brain on our Brev GPU ✅" and "Photo reader on our Brev GPU ✅"
   python web.py                 # the WhatsApp-style web app on port 8000 (old Gradio screens at /admin)
   # second terminal: a public https link (phones only allow the microphone on https)
   curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
   chmod +x cloudflared && ./cloudflared tunnel --url http://localhost:8000   # prints https://….trycloudflare.com
   ```
   That trycloudflare link is the demo link for judges' phones (no login). Backup: `GRADIO_SHARE=1 python app.py`
   prints a public `….gradio.live` link for the old Gradio screens. Brev's own tunnels sit behind a Cloudflare
   login, so judges' phones can't open them directly.
**Optional nicer link on Vercel** (e.g. `tradevoice.vercel.app`): Vercel serves only the pages in `web/`; every
`/api` call is passed to our server by `vercel.json`. When the server's public link changes, update the two
`destination` lines in `vercel.json` and push (Vercel redeploys by itself).

**After a stop/start, one command brings everything back:** `bash start_brev.sh` (both models, web app, public
link, model check); `bash start_brev.sh stop` before stopping the machine. For a link that stays the same across
restarts, put `NGROK_AUTHTOKEN` and `NGROK_DOMAIN` (the free static domain from dashboard.ngrok.com) in `.env`.
5. **Stop the instance whenever you're not using it.** Screenshot the Brev console (GPU type, runtime, cost) and
   `nvidia-smi` showing both models for the submission.

Fallbacks: if a Brev model is down, the cloud models answer; if everything fails, the offline rules still save the entry.
A model that times out is skipped for 2 minutes. Our own speech models (Whisper / omniASR, `ASR_ENGINE=local`,
`requirements-omni.txt`) still work as an option but are no longer the plan.
Stretch: package the setup as a **Brev Launchable** (one-click template) so anyone can rerun our demo.

## Environment variables
| Variable | Default | Purpose |
|---|---|---|
| `NVIDIA_API_KEY` | – | build.nvidia.com key. Without it: offline rules, no photo reading |
| `LLM_MODELS` | `nvidia/nemotron-3-super-120b-a12b,google/gemma-4-31b-it,qwen/qwen3.5-397b-a17b,meta/llama-3.3-70b-instruct` | Text models, tried in order |
| `VISION_MODELS` | `google/gemma-4-31b-it,qwen/qwen3.5-397b-a17b,nvidia/nemotron-nano-12b-v2-vl,meta/llama-3.2-90b-vision-instruct` | Photo models, tried in order (multilingual first) |
| `VISION_BASE_URL` / `VISION_API_KEY` | NVIDIA API / `NVIDIA_API_KEY` | Point at a self-hosted vLLM server instead |
| `ASR_MODEL` | `large-v3-turbo` | Whisper model on GPU (`small` on CPU); try `large-v3` for max accuracy |
| `OMNI_MODEL` | `omniASR_LLM_3B_v2` | Meta omniASR model for Yoruba/Hausa/Igbo voice (`omniASR_LLM_7B_v2` on a 48 GB GPU) |
| `ASR_URL` / `ASR_TOKEN` | – | Use a remote `asr_server` instead of local speech models |
| `DB_PATH` | `tradevoice.db` | SQLite file |
| `SHOP_NAME` | `Chioma Stores` | Default shop name on reminders and statement |
| `GRADIO_SHARE` | – | `1` = public link |
| `AUTH_REQUIRED` | `1` | Phone-number login. `0` = no login, one shared book (old demo) |
| `AUTH_DEMO` | – | `1` = show the login code on screen (use until WhatsApp works; also on when WhatsApp isn't set up) |
| `BOOKS_DIR` / `ACCOUNTS_DB` | `books` / `accounts.db` | One book file per phone number / logins, sessions, PIN, bank details, lender links, pay links |
| `WHATSAPP_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_VERIFY_TOKEN` | – | WhatsApp bot + login codes (`check_whatsapp.py` tests the whole chain) |
| `WHATSAPP_APP_SECRET` | – | Optional: checks messages really come from Meta (leave empty if unsure) |
| `PUBLIC_URL` | request address | Link used in pay links and in the daily reminder summary |
| `PAYSTACK_SECRET_KEY` / `PAYSTACK_EMAIL` | – | Pay links open a Paystack checkout; point Paystack's webhook at `/paystack/webhook` |
| `AUTO_REMINDERS` | `1` | Draft reminders on the promised day (every 30 min check) and WhatsApp the trader a summary |

## Honesty notes
- The starter code was prepared before the event with an AI coding assistant (Claude) and open-source parts. It is disclosed
  in `docs/SUBMISSION.md`, and the commit history shows what was built on the day.
- Demo history from `seed_demo.py` is synthetic and marked as such in the app and on the statement.
- The 20 test phrases in `eval/cases.jsonl` were written together with the rules, so their score is optimistic. We
  report results on new phrases written by teammates (see `TEAM_GUIDE.md`).

License: MIT
