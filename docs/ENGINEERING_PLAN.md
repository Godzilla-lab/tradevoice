# TradeVoice: engineering plan (October 2026)

For the developers. It turns the [`ROADMAP.md`](ROADMAP.md) into **tasks with owners, order, acceptance tests and
dates**, and sets the working rules. The design side is in [`DESIGN_PLAN.md`](DESIGN_PLAN.md); NAIC deliverables
are in [`naic/CHECKLIST.md`](naic/CHECKLIST.md).

**The one goal before Sun 11 Oct:** a live TradeVoice where **N-ATLaS really does the hearing and understanding**,
WhatsApp and the web share one book, 50+ real trader interactions are logged, and everything NAIC asks for can be
shown.

**Anything not on the P1 list waits until after NAIC.**

---

## 1. Rules (read first)
1. **The AI never does maths or invents money.**
   - Amounts must appear in what the trader said.
   - Totals, balances and any calculation come from code over the book.
   - Every number in a reply must trace to the book, the trader or a tool result.
2. **Nothing is saved without the trader's tap** (confirmation card or WhatsApp "Yes").
3. **TradeVoice never messages a customer by itself.** Reminders, receipts and statements are drafts the trader
   sends. Messages to the *trader* are fine.
4. **N-ATLaS is the primary engine.** Qwen, NVIDIA cloud and the offline rules are fallbacks **only when N-ATLaS is
   down**. Every reply records `engine`. Never route "hard" questions to a bigger model (NAIC disqualifies
   wrappers).
5. **Secrets only in `.env` / Modal Secrets.** Never in code, commits, issues, chat or screenshots. `.env`,
   `*.db` and `books/` are never committed.
6. **Made-up names only** in tests, seeds and demos (Mama Tunde, Oga Emeka, Iya Bisi, Alhaji Sani, Madam Funke).
   No real phone or account numbers in the repo.
7. **Privacy:**
   - one SQLite book per trader;
   - voice notes and photos are deleted after reading;
   - the usage log holds counts only, with no names, amounts or message text;
   - phones in analytics are salted hashes.
8. **N-ATLaS licence:**
   - the attribution text appears in the app (Me → About), the README and the landing page;
   - track active users over 30 days and warn at 800;
   - N-ATLaS is never used to score or profile traders.

## 2. Set-up
```bash
git clone https://github.com/Godzilla-lab/tradevoice.git && cd tradevoice
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in only what you need; tests need no keys
python src/web.py               # http://localhost:8000
python eval/run_all.py          # must say "N/N checks pass"
```
- **Layout:** `src/` (Python app), `web/` (front end), `eval/` (tests and test sentences), `scripts/` (start and
  checks), `docs/`.
- **Main modules:**

| Module | Job |
|---|---|
| `web.py` | API and the per-trader book middleware |
| `whatsapp.py` | The bot |
| `converse.py` | One conversation |
| `extract.py` + `llm.py` | Words → record |
| `asr.py` / `tts.py` | Hearing and speaking |
| `vision.py` | Photos |
| `ledger.py` | The book |
| `insights.py` / `assistant.py` | Maths and answers |
| `extras.py` | Lender, pay links, Paystack, reminders, PIN, CSV |
| `accounts.py` | Phones, guests, sessions |
| `ui_text.py` | All words in 5 languages |

## 3. How we work
- **Branches:**
  - `main` must always run and pass tests;
  - work on `feat/<task-id>-short-name` (for example `feat/E3-magic-link`);
  - open a pull request (PR) into `main`.
- **PR rules:**
  - small (one task);
  - tests added or updated;
  - `python eval/run_all.py` all green;
  - screenshots for any UI change (light + dark, 390 px);
  - one reviewer approves.
- **Tests:**
  - every new behaviour gets checks in `eval/test_*.py`, using the existing pattern: temp DBs, fake `graph_post`,
    signed webhooks, `check(name, ok, got)`;
  - end with a `N/M … checks pass` line so `run_all.py` picks it up;
  - **no test may need a real key or network.**
- **Commits:** clear message saying what changed and why. No secrets, no real data.
- **Daily:** 10-minute stand-up in the team chat (done / doing / blocked). The task board is the table in §5. Update
  the owner and status there.
- **Definition of done:**
  - code merged, tests green;
  - works on a real phone (WhatsApp and web);
  - docs updated (`TECHNICAL.md` / `.env.example`) if settings changed;
  - the checklist item ticked.

## 4. Environments
| Where | What runs | Notes |
|---|---|---|
| Laptop | Everything with offline rules; Mac can run N-ATLaS 4-bit via `mlx_lm.server` | For development |
| **Modal** | N-ATLaS LLM (vLLM, 1× L4, `--max-model-len 8192`); speech models only if the server CPU is too slow | Scales to zero; warm (`min_containers=1`) 6–10 Oct and 15–17 Oct. Spending limit set. `HF_TOKEN` as a Modal Secret |
| **Small always-on VPS** | `src/web.py` (web app + WhatsApp webhook + Paystack webhook), the 4 Whisper-Small speech models on CPU (to be confirmed by a speed test), cron jobs, Litestream → R2 | Behind **Cloudflare Tunnel** with a fixed hostname |
| NVIDIA API | Photo reading (`VISION_MODELS`) | Already built in |
| Cloudflare R2 | Backups, later training data | Encrypted |

**New settings** (add to `.env.example` with comments):

| Setting | What it's for |
|---|---|
| `NATLAS_URL`, `NATLAS_MODEL` | N-ATLaS LLM endpoint |
| `NATLAS_ASR` | `local` (on the server) or a URL |
| `ADMIN_TOKEN` | For `/team` and `/api/voice_check` |
| `TEAM_WHATSAPP` | The team's WhatsApp number |
| `CHAT_DAYS` | How long chat history is kept |
| `PUBLIC_URL` | Must be the fixed hostname |

## 5. Task list
Est. = rough engineer-days. **P1 = before NAIC.** Fill in owners today.

### Week 1 (Thu 1 – Sun 5 Oct): foundations + N-ATLaS
| ID | Task | Est. | Owner | Depends | Accept when |
|---|---|---|---|---|---|
| **E0** | **Ops (not code):** Meta payment method (bot stops without it!), start Meta business verification (the test number can only message 5 phones), Modal account + spending limit, VPS + Cloudflare Tunnel fixed hostname, Paystack test keys, HF licence accepted + token | 1 | | – | Bot replies from the VPS through the fixed link; Modal and Paystack keys in the server `.env` |
| **E1** | **Repo clean-up + security** (ROADMAP Part 1): delete `src/app.py`, `note.py`, `asr_server/`, `vercel.json`; fix `requirements.txt`; harden login (no code shown on screen); protect `/api/voice_check`; trim `/api/status`; skip guest books in reminders | 1 | | – | Fresh clone + `pip install -r requirements.txt` + `python src/web.py` works; tests green; no `/admin` |
| **E2** | **N-ATLaS LLM backend** in `llm.py`: OpenAI-compatible client to `NATLAS_URL`, official chat template with `date_string`, temperature 0.1, repetition penalty 1.12; **structured output** (guided JSON); few-shot examples per language; `engine="natlas"` | 2 | | E0 (Modal) | `scripts/check_models.py` shows N-ATLaS answering; 3 sample sentences per language produce valid records |
| **E3** | **Modal deploy** `deploy/modal_app.py`: vLLM serving `NCAIR1/N-ATLaS`, weights in a Modal Volume, auth header, `scaledown_window` 15 min, memory snapshot; a **wake-up ping** function | 1 | | E0 | Cold start time measured and written down; warm reply < 3 s for a short prompt |
| **E4** | **N-ATLaS speech** in `asr.py`: the 4 Whisper-Small models via `transformers` pipeline, 16 kHz mono via ffmpeg, chunking over 30 s, **book hints as prompt** (≤ 50 terms, < 224 tokens), **repetition-loop guard**; Pidgin → `NigerianAccentedEnglish`; Intron as fallback | 2 | | E0 | Voice notes in all 4 languages transcribed on the VPS; time per 15 s note measured; loop guard test passes |
| **E5** | **Benchmark harness** `eval/bench_natlas.py`: 464 sentences + tool-call set through N-ATLaS vs base Llama-3-8B-Instruct vs Qwen, zero-shot vs few-shot, **per language**; outputs a table for `docs/RESULTS.md` | 1 | | E2 | **First results by Sat 4 Oct.** If N-ATLaS is weak in a language, lean on the rules check and templates there |
| **E6** | **Speed budget:** time each step (download, ASR, LLM, TTS, send) per message, logged as `ms` | 0.5 | | E2, E4 | Warm voice note → reply **< 10 s** (target); slow steps found |

### Week 2a (Mon 6 – Wed 8 Oct): one account + evidence + pilot-ready
| ID | Task | Est. | Owner | Depends | Accept when |
|---|---|---|---|---|---|
| **E7** | **WhatsApp → web private link** (ROADMAP 2a): `magic` table, bot "web" → `/w/<token>` (single use, 15 min, hashed) | 1 | | E1 | Tests: works once, fails twice, fails expired, opens the sender's own book |
| **E8** | **One user list** (2c): `accounts.touch()` from WhatsApp, guest and login; source, first/last seen, consent, funnel | 0.5 | | E1 | A new WhatsApp sender appears with `source=whatsapp` |
| **E9** | **Events log + `/team` dashboard + CSV export** (2d): counts only, salted phone hash, engine share, N-ATLaS active users (30 days) with a warning at 800; **team phones flagged and excluded** from evidence | 1.5 | | E8 | `/team` 403 without `ADMIN_TOKEN`; no names or amounts in `events`; export works |
| **E10** | **Tools v1** (Part 11 / tool list): routing (record / ask / act) → small tool sets: record_*, correct_last, get_balance, who_owes_me, summary, draft_reminder, **query_book**, **calculate** (safe evaluator, number provenance), **resolve_date** (Nigerian calendar), **convert_units**, **reconcile_cash** | 3 | | E2 | Tool-call test set ≥ 200 sentences; accuracy reported per language; number provenance test passes |
| **E11** | **Speech fixes** (Part 5, items 1–4): light audio prep only, two-model transcription merged by N-ATLaS (amounts only if heard), **targeted re-ask** | 1.5 | | E4, E2 | Market-noise test clips: amount/customer accuracy before vs after |
| **E12** | **WhatsApp reliability** (Part 6): retries/backoff, dedup in SQLite, `statuses` webhook, ffmpeg check, **one message per reply** (cost), message count on `/team`, CTA button "Open my book" / "Pay now" | 1.5 | | E7 | Restart doesn't reprocess messages; failed sends visible on `/team` |
| **E13** | **Payments for the pilot** (Part 10): OPay number default in reminders; **`match_payment`**: read OPay receipt screenshot / forwarded alert → match debt → one-tap confirm | 1.5 | | – | Test with sample (made-up) OPay receipts: right debt matched, nothing saved without the tap |
| **E14** | **Memory v1** (8a/8b layers 1–3): `memory` table (nicknames, usual prices, corrections → ASR hints), `chat_log`, last 10–20 turns in prompts | 1 | | E2 | "Mama T" maps to Mama Tunde; "you said ₦4,500, did you mean ₦45,000?" works |
| **E15** | **Backups + data hygiene** (Part 9a/9b): Litestream → R2, nightly integrity + retention jobs | 0.5 | | E0 | Restore tested once |

### Week 2b (Wed 8 – Sat 11 Oct): UI, Space, freeze
| ID | Task | Est. | Owner | Depends | Accept when |
|---|---|---|---|---|---|
| **E16** | **Build the P1 designs** from Figma frames marked "Ready for dev" (`web/style.css` tokens, `web/app.js`), incl. Connect my WhatsApp (2b) and listening/re-ask states | 2–3 | | Design 5 Oct | Matches Figma at 390 px light/dark; works at 320 px; all 5 languages fit |
| **E17** | **Connect my WhatsApp + merge books** (2b) `src/merge.py` | 1.5 | | E7 | Merge test: shared customer joined, balances right, guest book gone |
| **E18** | **Hugging Face Space** (demo book, calls Modal with a secret + rate limit, lists all 5 NCAIR1 models, attribution) | 0.5 | | E3 | Appears under "Spaces using NCAIR1/N-ATLaS" |
| **E19** | **Code freeze Fri 10 Oct 18:00.** Only fixes after. Tag `naic-submission` | – | all | – | Tests green; live app + bot + Space up |

**If behind schedule, cut in this order:** E17 merge (keep 2a link), E14 memory, E12 extras (keep retries + one
message per reply), E13 receipt matching (keep the OPay number in reminders), E18 Space.
**Never cut:** E2, E4, E5, E9 (that's our NAIC evidence).

## 6. Testing beyond unit tests
- **Real-phone checks** after each deploy: a voice note in each language, a photo, a question, a reminder, a
  Paystack test payment, the private link.
- **Pilot data hygiene:** team phones flagged; demo/seed data never mixed into the evidence export.
- **Load sanity:** 20 voice notes in a row; check queueing and no duplicate replies.
- **Integration-check rehearsal (Tue 14 Oct):**
  1. a fresh person follows `TECHNICAL.md` and the judge instructions;
  2. everything works from a phone not on our team;
  3. the backup demo recording is ready.

## 7. Monitoring and on-call
- A free uptime monitor on `/api/status` and the webhook; alerts to the team WhatsApp group.
- `/team` shows errors, failed sends, engine share and latency.
- **On-call rota** for the pilot (6–10 Oct) and the check (15–17 Oct): one named person per day, with Modal
  warm-up and restart steps written in `TECHNICAL.md`.

## 8. Known risks (owner in brackets once assigned)
1. **N-ATLaS weak on our sentences**, especially Yorùbá (2.69/5 on its card). Know by Sat 4 Oct (E5); fall back
   to rules check + templates.
2. **Latency** (ASR + LLM + TTS + cold start). Measure in E6; keep Modal warm during the pilot.
3. **WhatsApp test-number limit (5 recipients)**: start Meta business verification now (E0); judges also get web
   instructions.
4. **Meta billing**: no payment method means no replies (E0).
5. **Scope**: follow the cut order in §5.

## 9. After NAIC (not now)
- Nightly summaries and chat search (8b layers 4–5), and the "What TradeVoice remembers" screen.
- Consent levels 2–3 and the dataset pipeline (9c/9d).
- Fine-tuning N-ATLaS and the speech models.
- OPay merchant API and the partnership pitch.
- Morning brief (template message), ajo, apprentice mode, the call-in number.
