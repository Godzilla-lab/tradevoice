<div align="center">

<img src="web/logo.svg" width="72" alt="TradeVoice logo">

# TradeVoice

**Records that speak your language.**

</div>

TradeVoice keeps the book for Nigerian market traders. A trader talks, types or photographs a notebook page in
English, Pidgin, Yorùbá, Hausa or Igbo, and TradeVoice writes down the sales, expenses, who owes what and when they
will pay. It answers questions about the book and drafts payment reminders that the trader sends. The AI reads the
words; plain code does every sum.

- **Live:** https://tradevoice.duckdns.org (web app at [/app](https://tradevoice.duckdns.org/app), privacy notice at
  [/privacy](https://tradevoice.duckdns.org/privacy))
- **NAIC 2026:** Innovation & Enterprise track, Problem Statement 2: Voice-First Access
- **Built on N-ATLaS:** the N-ATLaS language model writes the records and the four N-ATLaS speech models hear the
  voice notes

## Try it now
About two minutes, on a phone or a computer with a microphone.

1. Open **https://tradevoice.duckdns.org/app** and pick your language: English, Yorùbá, Hausa or Igbo. Pidgin works
   under English.
2. Tap **Create account**. Enter a Nigerian number you own and agree to the terms.
   - No code is needed: your number and a password. If you use Telegram, you can confirm your number there.
   - Choose a password (8 characters or more), then your name and business name. Tap **Create my account**.
3. Tap the mic (the round button in the middle of the bottom bar) and say:

   > Iya Bisi took 2 bags of rice for 60,000, she will pay Friday.

   Say it in English or in your own language.
4. TradeVoice reads it back. Check the card: ₦60,000, sold on credit, Iya Bisi, rice, pay by Friday. Anything it is
   not sure of is marked **Check this**. Tap **Save**. In live talk, where TradeVoice answers out loud, it asks
   "Should I save it?": say "yes", or tap to check it on screen first. Nothing is saved before that.
5. Ask **"Who owes me?"** out loud, or type it in the **Ask** tab. The answer comes from the book and is spoken back.

More to try:
- **Reminder:** open Iya Bisi under **Customers** and tap **Prepare reminder**. **Send on WhatsApp** opens your own
  WhatsApp with the message ready. TradeVoice never messages your customers.
- **Notebook photo:** tap **Scan book** on Home and photograph a page. TradeVoice lists each line; you tick the ones
  to keep and tap **Save ticked**.
- **Lender report:** tap **Lender report** on Home to see the last 30 days, and share a private link that expires by
  itself.

## On Telegram
TradeVoice also runs as a Telegram bot. It is free and works the same way as our WhatsApp bot: voice notes, typed
messages, notebook photos, **Yes, save** and **No** buttons, and spoken replies.

1. The bot link is on the website (https://tradevoice.duckdns.org).
2. Tap **Start**. The bot asks you to tap **Share my phone number**, Telegram's own button. Only your own number is
   accepted.
3. That number's book is the same book as in the web app. Send a voice note, and tap **Yes, save** to keep it.

On the website, **Confirm on Telegram** can also confirm your number when you sign up or log in.

**WhatsApp:** the WhatsApp bot is built and tested (`src/whatsapp.py`, tested against a faked Meta API in
`eval/test_whatsapp.py` and `eval/test_whatsapp_send.py`), but it is **not live**. We could not get WhatsApp Business
API access in time. Reminders still go out through the trader's own WhatsApp, as above.

## How N-ATLaS is used
```
voice note, typed words or notebook photo   (web app, Telegram)
        |
        v
N-ATLaS speech models hear the voice note          (photos: an NVIDIA vision model reads the lines)
        |
        v
N-ATLaS language model writes the record as JSON   (backups: NVIDIA API models, then offline rules)
        |
        v
code checks: the amount must have been said, code multiplies and adds, unsure fields are marked
        |
        v
check card: Save, Change or Cancel   (nothing is saved before the trader says yes)
        |
        v
the trader's own book: answers, reminder drafts, lender report   (plain Python maths)
```
- **The brain for records.** Every sentence, spoken, typed or read from a photo, goes to N-ATLaS first
  (NCAIR1/N-ATLaS, Llama-3 8B), served with vLLM on a Modal GPU (`deploy/modal_natlas.py`). If it is down or slow,
  NVIDIA API models answer, then offline rules (`chat()` in `src/llm.py`).
- **Hearing.** Voice notes are heard by the four N-ATLaS speech models: Yoruba-ASR, Hausa-ASR, Igbo-ASR and
  NigerianAccentedEnglish for English and Pidgin (`deploy/modal_asr.py`, `src/asr.py`). Traders mix languages, so
  a Yorùbá, Hausa or Igbo note is heard twice, by its language model and the English model, and N-ATLaS merges the
  two (`src/hearing.py`). An amount is kept only if a speech model really heard it. While the speech server is
  down, Intron hears the notes instead.
- **Live talk** uses Intron's streaming speech in and out, so words appear while the trader talks. N-ATLaS still
  writes the answer (`src/intron_live.py`).
- **Ask chat** (`src/agent.py`): an NVIDIA model first with N-ATLaS as the backup; in Yorùbá, Hausa and Igbo,
  N-ATLaS goes first. Tools read the book, and code checks every number in the reply.
- **Code does the maths.** Totals, balances, quantity times price and dates come from code (`src/tools.py`,
  `src/ledger.py`), never from a model.

Full details: [`docs/naic/NATLAS_INTEGRATION.md`](docs/naic/NATLAS_INTEGRATION.md). Facts from the model cards:
[`docs/naic/NATLAS_FACTS.md`](docs/naic/NATLAS_FACTS.md).

## Results
N-ATLaS against the model it was built from (Meta-Llama-3-8B-Instruct), on 1,000 test sentences, 200 per language
(`eval/cases_1000.jsonl`; run on 2 Oct 2026, N-ATLaS on a Modal L4 GPU). "Alone" is the model's own answer before
our code checks it. A sentence counts as right when the type, amount and customer are all right.

| | N-ATLaS alone | Llama-3-8B alone | Full app (N-ATLaS + code checks) |
|---|---|---|---|
| **All** | **69%** (95% range 66 to 71) | 51% (47 to 54) | **100%** |
| English | 85% | 59% | 100% |
| Pidgin | 62% | 57% | 100% |
| Yorùbá | 69% | 60% | 100% |
| Hausa | 67% | 27% | 100% |
| Igbo | 62% | 52% | 100% |
| Amounts said in local number words | 62% | 12% | 100% |
| Wrong amount written | 68 | 170 | 0 |
| Asked when the sentence was unclear | 3 of 28 | 17 of 28 | 28 of 28 |
| Median time (warm GPU) | 5.0 s | 5.3 s | 5.1 s |

How to read it:
- N-ATLaS is 18 points ahead of its base model, most of all in Hausa and in amounts said in Yorùbá, Hausa and Igbo
  number words.
- Alone, neither model is safe for money. The app is safe on this set because code checks every record.
- These sentences were written by our team and Claude from templates, not by native speakers, and our rules were
  built on the same templates (rules alone also score 100% here). On 100 sentences written from research on how
  traders talk, before any fixes, the scores were: rules alone 54%, N-ATLaS alone 63%, full app 69%. The real test is
  traders' own voice notes from the pilot.

Every run, with dates and commands: [`docs/RESULTS.md`](docs/RESULTS.md). Pilot numbers (counts only, from the live
log) come from `scripts/validation_report.py`.

## Privacy
- **The book belongs to the trader.** Each phone number has its own book. We never sell data and never message
  customers: reminders and receipts are drafts the trader sends.
- **Voice notes and photos are deleted once read**, unless the trader says yes to "Help make TradeVoice better",
  asked once and separately. Saying no never limits the app.
- **The team's log has no names, amounts, words or audio**, and phone numbers in it are replaced by a code.
- **Delete at any time.** The account closes at once, is kept 90 days in case the trader changes their mind, then is
  erased. The book can be exported from Me. Full notice: [/privacy](https://tradevoice.duckdns.org/privacy).

## Run it yourself
```bash
git clone https://github.com/Godzilla-lab/tradevoice.git && cd tradevoice
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-server.txt
python src/web.py            # open http://localhost:8000/app
```
With no keys, typed records and questions work with the offline rules, and sign-up needs no code. To add N-ATLaS,
copy `.env.example` to `.env` and deploy the two Modal apps:
```bash
modal deploy deploy/modal_natlas.py   # N-ATLaS language model: put its URL + /v1 in NATLAS_URL
modal deploy deploy/modal_asr.py      # N-ATLaS speech models: NATLAS_ASR_URL
```
The live server is set up by `deploy/server/setup.sh` and checked by `deploy/server/preflight.sh`. Full setup,
every setting and the API: [`docs/TECHNICAL.md`](docs/TECHNICAL.md).

## Repo map
```
src/            the Python app (python src/web.py)
  web.py, v2.py         web server and API; accounts, sign-up and the book for the web app
  converse.py           one conversation over one book: record, confirm, correct, ask, remind
  extract.py, llm.py    words to a record; every model call, N-ATLaS first, then the backups
  asr.py, hearing.py    hearing with the N-ATLaS speech models; merging two hearings
  agent.py, askbook.py  the Ask chat: a model with the book's tools; exact answers from the book
  tools.py, ledger.py, insights.py   the book and the maths (code, never the AI)
  intron_live.py, tts.py             live talk and spoken replies (Intron)
  vision.py, photo.py   notebook photo to lines the trader checks and saves
  telegram.py           the Telegram bot (live)
  whatsapp.py           the WhatsApp bot (built and tested, not live)
  sms.py                sign-up codes through Termii, by phone call (or text with a sender ID); off until its keys are set
  extras.py             lender link, pay links, reminders, receipts
  events.py, team.py    the anonymised log and the team dashboard (/team)
  ui_text.py            the words on screen in English, Yorùbá, Hausa and Igbo
web/            the website, the app (app.html, live.js), the privacy notice, the team dashboard
deploy/         modal_natlas.py, modal_asr.py (N-ATLaS on Modal); server/*.sh (the live server)
scripts/        model and server checks, backups, the validation report
eval/           tests (run_all.py, browser_test.cjs) and test sentences (cases_*.jsonl)
docs/           technical notes, results, research; naic/ holds the NAIC documents
design/         the app design the web app is built from
```

## Tests
```bash
python eval/run_all.py                                 # 31 suites, no keys, no network
NODE_PATH=$(npm root -g) node eval/browser_test.cjs    # the whole app in Chromium (needs Playwright)
python eval/run_tools_eval.py                          # tool choice on 203 sentences, offline
python eval/run_eval.py --cases eval/cases_1000.jsonl --llm natlas --raw --workers 8   # the benchmark (needs NATLAS_URL)
```
- `eval/run_all.py`: 998 checks in 31 suites, all passing on 9 Oct 2026. They cover records, corrections, the
  Ask chat, hearing, sign-up, sign-up codes by Termii, Telegram, WhatsApp (against a faked Meta API), backups and the dashboard.
- `eval/browser_test.cjs`: 75 checks in a real browser, from sign-up to a reminder draft, the Ask tab and log out.

More in [`docs/TESTING.md`](docs/TESTING.md).

## Status and limits
- The WhatsApp bot is not live (see above).
- The Yorùbá, Hausa and Igbo wording and voices still need review by native speakers.
- Heavy market noise lowers speech accuracy.
- After an idle hour the N-ATLaS GPU sleeps, and waking it takes a few minutes; the backup models answer meanwhile.
  The server can keep it awake in market hours (`NATLAS_WATCH`, 7am to 8pm Nigeria time, or only on chosen days).
- The app keeps working when Modal is asleep, broken or out of credits: the trader waits at most 12 s once, then
  NVIDIA answers and Intron hears until N-ATLaS is back. `NATLAS_MODE=off` runs it with no Modal at all
  (`docs/TECHNICAL.md`, section 5).

## Team
See [`docs/naic/TEAM_PROFILE.md`](docs/naic/TEAM_PROFILE.md).

## Licence and attribution
TradeVoice's code is under the MIT licence ([`LICENSE`](LICENSE)).

The N-ATLaS models (NCAIR1/N-ATLaS, Yoruba-ASR, Hausa-ASR, Igbo-ASR, NigerianAccentedEnglish) are used under their
own Terms of Use, not the MIT licence. Those terms allow at most 1,000 active end-users in a rolling 30 days without
a commercial licence; the team dashboard counts them.

N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, and powered by Awarri Technologies.

Other services: Intron (live talk and spoken replies), NVIDIA API (backup models and photo reading), Modal (GPUs),
Telegram (the bot). All names in this repo's examples, tests and demo data are made up.
