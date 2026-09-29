# TradeVoice

**Records that speak your language.** Voice-first bookkeeping for Nigerian market traders, on WhatsApp and the web,
in English, Pidgin, Yorùbá, Hausa and Igbo.

Built at **Come Build with AI** (GOMYCODE × NVIDIA, 27 September 2026) · Primary prize: **Kredete Financial Inclusion Award**

| | |
|---|---|
| 🌐 Live app | [link] |
| 💬 WhatsApp bot | [number] (send "hi") |
| 🎬 90-second video | [link] |
| 📑 Pitch deck | [link] · slide text and demo script: [`docs/PITCH_DECK.md`](docs/PITCH_DECK.md) |
| 📦 Submission details (AI disclosure, Brev usage, tests) | [`docs/SUBMISSION.md`](docs/SUBMISSION.md) |

---

## The problem
A trader sells on credit all day: *"Mama Tunde, take it, pay me Friday."* Those debts live in her head, a torn
notebook or a WhatsApp chat. She forgets who owes her, doesn't know her real profit, and when she asks a lender for a
loan she has no records to show. **No records, no credit.**

## What TradeVoice does
The trader **just says what happened**, as a voice note, a photo of her notebook, or a typed message:

> 🎙 *"I sell Mama Tunde two bags of rice for forty-five thousand. She go pay Friday."*

TradeVoice shows what it understood (**customer, amount, item, quantity, credit or paid, due date**), marks anything
it is unsure of, and saves **only when the trader taps Save**. It replies in her language, as text and as a voice note.

- **Who owes me / who I owe**: balances, promised dates, late payers
- **Ask my book** in any of the 5 languages: *"Who owes me the most?"*, *"Ṣé mo ní gbèsè lọ́wọ́ Alhaji?"*; answers are
  calculated from the book, never guessed by the AI
- **Reminders with pay links**: drafted for the trader to send; TradeVoice never messages customers on its own
- **Wholesale tools**: credit limit per customer, customer statements, margin per item, cheapest supplier, usual-order drafts
- **Lender link**: the trader chooses to share a read-only report of her trading history for 1, 7 or 30 days
- **Privacy**: no sign-up (each phone gets its own private book), hide amounts, PIN lock, CSV download,
  delete everything, voice notes and photos deleted after reading, works offline and syncs later

## How it works
```
 Voice note / photo / text   (WhatsApp bot or web app)
        │
        ▼
 Intron Sahara ── hears English, Pidgin, Yorùbá, Hausa, Igbo (and mixed sentences)
        │
        ▼
 Qwen2.5 LLM on our NVIDIA Brev GPU (vLLM) ── words → transaction
 Qwen2.5-VL on the same GPU               ── notebook photo → lines
        │
        ▼
 Code guards ── the amount must have been said · corrections update the same record · unsure fields flagged
        │
        ▼
 Confirmation card ── trader taps Save / Change / Cancel
        │
        ▼
 The trader's own SQLite book ──► answers, reminders, insights, lender report (plain Python maths)
        │
        ▼
 Intron voices speak the reply (Spitch, then Meta MMS, as backups)
```
**Design rule: the AI reads and phrases; plain code does the maths.** Totals, balances and every answer about money
come from the book, so the AI can never invent a number. If the GPU or network is down, NVIDIA's cloud models answer,
and if everything fails, offline rules still record the entry.

## Tested
```bash
python eval/run_all.py                                            # 252/252 checks in 11 suites, no keys needed
python eval/run_eval.py --rules-only --cases eval/cases_hard.jsonl  # trap phrases in 5 languages
```
| Test | Result |
|---|---|
| Automated feature checks (demo flow, corrections, WhatsApp bot, wholesale, login, lender and pay links, Intron voice…) | **252 / 252** |
| Sentence → entry, all fields correct, offline rules alone (5 languages, including 208 trap phrases) | **464 / 464** |
| Real WhatsApp test by a teammate | Found that corrections were saved as new records; fixed, and covered by `eval/test_corrections.py` |

The test sentences were written by our team, not yet checked by native speakers of every language, so the numbers
above are optimistic. Details and AI-model runs: [`docs/RESULTS.md`](docs/RESULTS.md), [`docs/TESTING.md`](docs/TESTING.md).

## Run it
Works on a laptop with no GPU and no keys (offline rules; no photo reading or speech).
```bash
git clone https://github.com/Godzilla-lab/tradevoice.git && cd tradevoice
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/web.py                       # http://localhost:8000  (Me → "Try with sample records" for demo data)
```
With AI, speech and WhatsApp: copy `.env.example` to `.env` and add your own keys (never commit it). On NVIDIA Brev,
`bash scripts/start_brev.sh` starts both models, the app and a public link; `python scripts/check_models.py` and
`python scripts/check_whatsapp.py` test every part and say what to fix. Full setup and every setting:
[`docs/TECHNICAL.md`](docs/TECHNICAL.md) · WhatsApp: [`docs/WHATSAPP.md`](docs/WHATSAPP.md).

## Project layout
```
tradevoice/
├── src/            the Python app (run: python src/web.py)
│   ├── web.py          web server + API; serves web/ and the WhatsApp webhook
│   ├── whatsapp.py     WhatsApp bot (Meta Cloud API): voice notes, photos, Yes/No buttons, voice replies
│   ├── converse.py     one conversation over one book: record, confirm, correct, ask, remind
│   ├── extract.py      words → transaction (LLM first, rules as fallback and amount check); llm.py
│   ├── asr.py, tts.py  hearing (Intron) and speaking (Intron, Spitch, MMS)
│   ├── vision.py, photo.py              notebook photo → lines to check and save
│   ├── ledger.py, insights.py, assistant.py   the book, the maths, exact answers to questions
│   ├── extras.py       lender link, pay links (Paystack), reminders, receipts, PIN, CSV
│   ├── accounts.py     one private book per phone
│   ├── ui_text.py, tax.py   every screen word in 5 languages; sourced tax information
│   └── app.py, asr_server/  old Gradio screens (/admin) and an optional speech server
├── web/            the front end: HTML, CSS, JavaScript, service worker, icons
├── eval/           tests (python eval/run_all.py) and 464 test sentences
├── scripts/        start_brev.sh, check_models.py, check_whatsapp.py
├── docs/           pitch deck, submission, technical notes, research, team guide
└── requirements*.txt, .env.example, vercel.json
```

## Honesty notes
- Starter code was prepared before the event with an AI coding assistant (Claude) and open-source parts; this is
  disclosed in [`docs/SUBMISSION.md`](docs/SUBMISSION.md), and the commit history shows what was built on the day.
- Demo data (`seed_demo.py`) is synthetic, uses made-up names, and is marked as sample data in the app.
- Yorùbá, Hausa and Igbo wording still needs a native-speaker check.

Team docs: [`docs/TEAM_GUIDE.md`](docs/TEAM_GUIDE.md) · [`docs/PREP_PLAN.md`](docs/PREP_PLAN.md) · [`docs/RULES_CHECKLIST.md`](docs/RULES_CHECKLIST.md)

License: MIT
