# TradeVoice roadmap: WhatsApp ↔ web as one account, N-ATLAS, NAIC readiness

> Status: **planned, not built yet.** File and line references point at the code as of this commit.

## Context
Market traders live on WhatsApp, so WhatsApp must be the front door and the web app the "big screen" for the
same book. Today the two are disconnected:
- Sending "web" to the bot (`src/whatsapp.py:350-352`) returns a plain `PUBLIC_URL/app` link. Since the login
  screen was removed, opening it creates a **new empty guest book** (`web.py:745` `/api/auth/guest`).
- A trader who starts on the web has a guest book (`999…`) with no way to join it to their WhatsApp number.
- We cannot see our users: WhatsApp language/consent sits in `wa_users` inside each book
  (`whatsapp.py:72-91`), web users sit in `accounts.db users`, and `STATS` (`whatsapp.py:42`) is in-memory.

NAIC Innovation & Enterprise track (deadline **12 Oct 2026, 15:59**; N-ATLAS integration check 15–17 Oct).
We enter **PS2, Voice-First Access**. The rules:
- a working build integrated with the N-ATLAS stack (wrapping other models disqualifies);
- real-world validation evidence: session logs, and around 50 real interactions according to secondary
  sources;
- 7 deliverables (see Part 4).

The interaction log and dashboard below are exactly that evidence.

Never commit `.env`, `*.db` or `books/`.

---

## Part 1: Prepare the repo (cleanup commit, done first)

**Delete (dead or unsafe)**
- **Old Gradio UI:**
  - `src/app.py` and `src/note.py` (only `app.py` uses it), plus `eval/test_note.py`.
  - Remove the `/admin` mount at `web.py:850-858` and the docstring at `web.py:1-3`.
- **Optional speech server:** `src/asr_server/` and the `ASR_URL` branch in `src/asr.py:7,22,197-201`.
- **Hackathon proxy to a dead tunnel:** `vercel.json` and `.vercelignore`.
- **Unused or empty files:**
  - `eval/cases_team.jsonl` (empty)
  - `web/icon-512.png`, `web/logo-light.svg`
  - `docs/images/customers.png`, `docs/images/insights.png`
- **Bot avatar:** move `web/whatsapp-profile-640.png` to `docs/images/`.
- **Hackathon docs:** move `docs/hackathon/` to a git tag `hackathon-2026-09` so it's kept in history, then
  delete the folder from `main`.
  - Fix links in `README.md`, `docs/TECHNICAL.md` and `docs/RESULTS.md`, pointing them to the tag.

**Fix**
- **`requirements.txt`:**
  - Add `fastapi`, `uvicorn`, `python-multipart` and `httpx`. Today they're only listed in
    `asr_server/requirements.txt`.
  - Drop `gradio` and `pandas`.
  - Mark `faster-whisper` and `spitch` as optional.
- **`.gitignore`:** add `*.db-journal`, `*.db-wal`, `*.db-shm`, `*.log`, `.DS_Store`, `.vercel/`, and `.env.*`
  with an exception for `.env.example`.
- **`.env.example`:** drop `SHOP_PHONE` (unused). Add `ADMIN_TOKEN`, `TEAM_WHATSAPP` and the N-ATLAS
  variables (Part 4).
- **Test files:** replace `15551549545` in `eval/test_auth.py:19` and `eval/test_extras.py:19` with an obviously
  fake number.
- **Login hardening:** tighten the phone-login fallback (`AUTH_STRICT` on by default).
- **Status endpoints:** trim what `/api/status` returns and put `/api/voice_check` behind `ADMIN_TOKEN`.
- **Reminders:** `extras.run_due_reminders` (`extras.py:452-499`) should skip guest `999…` books and `books/.db`.
- **WhatsApp books:** in `whatsapp._safe`, ignore messages whose sender doesn't normalise, instead of writing to
  `books/.db`.
- **Stale docs:** update the phone-login, Gradio and "one shared book" text in `docs/WHATSAPP.md`,
  `docs/TECHNICAL.md`, `docs/UI_RESEARCH.md`, the `whatsapp.py:11-12` header and `README.md:105`.

**Unreachable phone-login UI** (`web/app.js` `loginPhone`, `loginCode`, `loggedIn`, `loginShop`, lines
1107-1208): keep it. Part 2b reuses its polling screen for "Connect WhatsApp". Delete whatever isn't reused.

---

## Part 2: WhatsApp ↔ web as one account

### 2a. WhatsApp → web: one-tap private link (magic link)
- **New table** in `accounts.db`: `magic(token_hash PK, phone, expires, used)`. Add `accounts.new_magic(phone)`,
  which makes a `token_urlsafe(24)` valid for 15 minutes, and `accounts.use_magic(token)`, which returns the
  phone once. Store only hashes, as in `start()` and `new_session()`.
- **Bot:** the `dashboard/web/app/book` command (`whatsapp.py:350`) replies:
  > 📊 Open your book: {PUBLIC_URL}/w/{token}. Works once, for 15 minutes. Don't forward it.
- **New route** `GET /w/{token}` in `web.py`:
  - On success: `use_magic`, then the `_logged_in` cookie logic (`web.py:681`), then a redirect to `/app`.
  - On failure: a friendly page saying "send *web* to the bot again".
- This is safe because Meta has already proved the message came from that number. The token is single-use,
  short-lived and stored as a hash.

### 2b. Web → WhatsApp: "Connect my WhatsApp" (guest book joins the phone book)
- **Me screen:** add a `data-me="connect"` button in `settingsHtml()` (`app.js:695-711`), shown when
  `S.me.guest`.
- **Flow:**
  1. The trader types their number and we call the existing `accounts.start(phone)`.
  2. The UI shows a `wa.me/<bot>?text=LINK <WORD>` button and polls. This reuses `loginCode`'s 2-second poll
     (`app.js:1150`) and the `verify_link` logic in `/api/auth/start` (`web.py:701-723`).
  3. The bot accepts `LINK <WORD>` alongside `LOGIN <WORD>` (`whatsapp.py:302`) through
     `accounts.confirm_from_whatsapp`. It requires the sender's number to match.
  4. New endpoint `POST /api/auth/connect {login_id}` (signed-in guest only): `accounts.poll(lid)` returns the
     phone, then the guest book is merged into the phone book and the browser is logged in as the phone.
- **New `src/merge.py`: `merge_guest(guest, phone)`.**
  - **If the phone book is empty:** move the file `books/<guest>.db` → `books/<phone>.db`. Keep the
    `wa_users` row if one exists.
  - **Otherwise copy rows across in one transaction:**
    - `customers`: match by case-insensitive name. Matched customers reuse the phone book's id; others are
      inserted and get a new id.
    - `entries`, `reminders` and `messages`: remap `customer_id`; don't copy `wa_users`.
    - Record `demo` and the `raw_text` provenance.
  - **In `accounts.db`:**
    - Re-key `shares.phone` and `paylinks.phone`, remapping `paylinks.customer_id`.
    - Copy `users` profile fields (shop, lang, pin_hash, bank details) only where the phone row's field is
      empty.
    - Delete the guest `users`/`sessions` rows and the guest book file.
  - **Clear caches:** `web.SESSIONS` for both book paths (`web.py:83,90`) and the `assistant.py:88` cache.
  - **Undo:** keep `books/<guest>.db.merged-<date>` for 7 days.
- **Forgot PIN** (`app.js:1180`): for a connected account, recovery goes through WhatsApp (2a) instead of
  creating a new empty guest book. For a guest, warn that the book can't be recovered unless WhatsApp is
  connected.

### 2c. One record per trader (the user list)
- **Extend `accounts.users`** (migration in `accounts.db()`): `source` (whatsapp/web), `first_seen`,
  `last_seen`, `consent_at`, `linked_at` and `funnel` stage.
- **`accounts.touch(phone, source, **fields)`**: called from `whatsapp.handle()` for every incoming message
  (creating the row on a first WhatsApp message), from `/api/auth/guest`, and from `_logged_in`.
- **Language and consent:** `wa_users.lang` and `consent_at` are mirrored into `users` through `touch`, so the
  web shows the same language. `wa_users` stays as the bot's local copy.

### 2d. Interaction log and team dashboard (also the NAIC evidence)
- **New table** `events(id, ts, phone_hash, channel, kind, lang, engine, ok, ms)` in `accounts.db`. `kind` is
  one of: first_message, lang_set, consent, record_saved, question, voice_note, photo, link_web, connect,
  error.
- **Privacy:** store no amounts, names or message text. Phones are stored as a salted hash.
- **`accounts.log_event(...)`** is called in:
  - `whatsapp.handle` (first message, language, consent, voice and photo, errors in `_safe`);
  - the web save, ask and voice endpoints;
  - 2a and 2b.
- **`GET /team?key=ADMIN_TOKEN`:** a single HTML page with counts only:
  - new traders today and this week, and how many were active in the last 7 days;
  - WhatsApp versus web, and languages;
  - the funnel: first message → language → consent → first record → came back another day;
  - voice notes, text and photos; errors; which engine served each request (Intron, N-ATLAS, Qwen).
- **`GET /team/export.csv`:** the anonymised interaction log for the NAIC "50 real interactions" evidence.
- **Optional:** a daily WhatsApp summary to `TEAM_WHATSAPP`, sent on the existing `auto_runs` daily tick
  (`extras.py`).
  - It goes to the team only, never to traders' customers.
  - It needs our team number to have messaged the bot in the last 24 hours, or an approved template.

---

## Part 3: Tests (`eval/`, picked up automatically by `run_all.py`)
`eval/test_link.py` follows the `test_auth.py` pattern: temp DBs, fake `graph_post`, signed webhooks, one
`TestClient` per user. It covers:
- **Magic link:** "web" → the link is sent, works once, fails a second time, and fails after expiry. It logs in
  to the sender's own book and shows that book's records.
- **Connect:** a guest with 3 records connects to a phone book that has 2 records and a shared customer name.
  Result: one customer, 5 entries, balances correct, guest book gone, cookie now the phone's. A `LINK` sent
  from the wrong number is refused.
- **Connect to an empty phone book:** the file is moved.
- **Users and events:** a new WhatsApp sender creates a `users` row with `source=whatsapp`, and the funnel
  stages advance. The `events` table contains no amounts or names.
- **Access:** `/team` returns 403 without `ADMIN_TOKEN`; `/api/status` returns only the public fields.
- **Login hardening:** covered by `test_auth.py`.

All existing suites must stay green (252 checks today).

---

## Part 4: N-ATLAS becomes the core + NAIC readiness
N-ATLAS is the main model for both understanding and hearing. Other models remain only as backups when
N-ATLAS is down, and every reply records which engine served it, so the integration check can see that
N-ATLAS does the work.
- **N-ATLAS language model** (`NCAIR1/N-ATLaS`, Llama-3 8B), set as the primary in `src/llm.py`:
  - It goes through the OpenAI-compatible API `llm.py` already uses (new `NATLAS_URL` and `NATLAS_MODEL`).
  - **Where it runs:** on Brev with vLLM, in 4-bit if needed to fit next to Qwen-VL for photos; or on the Mac
    with `mlx_lm.server` for development.
  - **What N-ATLAS handles:** turning words into a transaction, answering questions, and wording replies in
    all 5 languages.
  - **Backups:** Qwen, then the NVIDIA cloud, then the offline rules.
  - The code guards stay. N-ATLAS reads and phrases; plain code does the maths and checks every amount was
    said.
  - Prompts are re-tuned for Llama-3's chat template where needed.
- **N-ATLAS speech recognition**, the primary hearing backend in `src/asr.py`
  (`ASR_BACKEND=natlas`, now the default):
  - Models: `NCAIR1/Yoruba-ASR`, `Hausa-ASR`, `Igbo-ASR` and `NigerianAccentedEnglish`.
  - **Choosing a model:** by the trader's language. Pidgin and English use NigerianAccentedEnglish.
  - **Where it runs:** on the same Brev GPU through a small `/asr` endpoint inside `web.py`'s process. It
    loads lazily and the models are cached.
  - **Backup:** Intron.
- **Startup checks:** `scripts/start_brev.sh` and `scripts/check_models.py` start and check the N-ATLAS
  servers. `/team` shows the share of requests each engine served.
- **Licence:** the free licence covers up to 1,000 active users. Note this in the README and TECHNICAL docs.
- **Benchmark:** run our 464 sentences through N-ATLAS and Qwen side by side, and put the results in
  `docs/RESULTS.md`. This uses a Kaggle notebook or Brev, because the free GPU's 16 GB needs the 4-bit model.
- **Evidence:** 50 or more real trader interactions, using the `events` log and `/team` export from 2d.
### NAIC application, step by step (from the official NAIC page)
**Key facts**
- The deadline is **12 Oct 2026, 15:59**. Treat it as 3:59 PM Nigeria time and aim to submit on 11 Oct.
- Screening runs on a rolling basis, so submitting early helps.
- The **N-ATLAS integration check is 15–17 Oct**: the live app must be running with N-ATLAS on those days.
- Shortlisting is 18–20 Oct.
- There are cash prizes for 1st, 2nd, 3rd and special awards.

**Eligibility checks**
1. Team of 1–6, applying as individuals or as a registered entity.
2. Individuals must be Nigerian citizens aged 18 or over, with a government ID. Companies need a CAC
   certificate.
3. "Not previously awarded in another national or international competition." **Risk:** if TradeVoice wins at
   GOMYCODE × NVIDIA, ask FMCIDE whether a hackathon prize counts.
4. The submission is in English, for one problem statement only. We choose **PS2, Voice-First Access**.
5. It must be a working build integrated with the N-ATLAS stack. Concept-only entries are not eligible.

**The 7 deliverables we must prepare**

| # | Deliverable | Format | Built from |
|---|---|---|---|
| 1 | Working artefact | URL | The public GitHub repo and the live app link (Brev and Cloudflare tunnel, kept up through 17 Oct) |
| 2 | N-ATLAS integration evidence | PDF | `docs/naic/NATLAS_INTEGRATION.md`: architecture diagram; where N-ATLAS LLM and ASR are called (file and function); engine-share stats from `/team`; benchmark of N-ATLAS against Qwen on the 464 sentences |
| 3 | Real-world validation | PDF | `docs/naic/VALIDATION.md`: anonymised session log (`/team/export.csv`) with 50 or more real trader interactions in Nigerian languages, the funnel, screenshots, and beta-tester confirmations |
| 4 | Technical documentation | PDF | `docs/TECHNICAL.md` updated: architecture, setup, environment variables, running N-ATLAS on Brev or the Mac, API |
| 5 | Video demonstration | URL | 3–5 minutes, end to end, **ideally a real trader speaking Yorùbá, Hausa or Igbo** on WhatsApp, then the private link to the web book. We write the script; the team films it. |
| 6 | Team profile | PDF | `docs/naic/TEAM.md`: bios, affiliations and roles. Filled in by the team. |
| 7 | Registration evidence | PDF | CAC certificate or government ID. Provided by the team. |

- **PDFs:** generated from the Markdown with the existing pymupdf or Playwright tooling, into
  `docs/naic/pdf/`. That folder is gitignored, since the PDFs may hold personal information.
- **Team to-do list:** [`docs/naic/CHECKLIST.md`](naic/CHECKLIST.md) tracks the 7 items, owners and dates.
- **Plan:** have about 3 days of real-trader pilot before the 11 Oct submission.

## Part 5: Working around N-ATLAS's speech limits (based on research)
N-ATLAS lists four limits: accent and dialect bias, children's speech, mixing languages, and noise.
`NCAIR1/Yoruba-ASR` is Whisper-small or MMS fine-tuned mostly on read speech, so it is weaker on market
conversation.

**Must do before 12 Oct**
1. **Light audio preparation only:** 16 kHz mono, volume levelling, trimming silence.
   - **No heavy denoising.** A 2025 study found denoising made Whisper worse at every noise level, for
     example 8.8% → 25.8% WER. We A/B test any filter before keeping it.
   - Code: `src/asr.py`, using the ffmpeg we already have.
2. **The trader's book as hints.** Because the NCAIR models are Whisper-based, we can pass a short prompt of the
   trader's own customer names and items, about 50 terms, kept under Whisper's 224-token limit.
   - Research shows a short, accurate list beats a giant one.
   - The list comes from `ledger` customers and items.
3. **Two hearing models plus N-ATLAS merging.**
   - Run the language model (Yorùbá, Hausa or Igbo) and NigerianAccentedEnglish on the same voice note.
   - The N-ATLAS LLM merges the two transcripts and repairs names against the book. This is "generative error
     correction"; the HyPoradise study found it beats simply picking the better transcript.
   - **Guard:** an amount is only kept if one of the raw transcripts contains it.
4. **Targeted re-ask when unsure:**
   - Low confidence on one field → ask for just that part: *"Say the amount again."*
   - Very low confidence, usually noise → a quiet re-prompt.
   - The confirmation card stays the final check.
5. **TradeVoice market test set** (consented voice notes, tagged by language, mixing and noise level).
   - Measure word error rate **and** whether the amount and customer came out right, since that is what
     matters to traders.
   - Report N-ATLAS raw versus with fixes 1–4 in the NAIC PDFs.

**After submission: the data loop and fine-tuning**
6. **Learning from corrections, opt-in only:**
   - Edits on the confirmation card become pairs of what was heard and what was meant.
   - With consent, keep the audio with names and amounts redacted.
   - This follows Intron's AfriSpeech (2,463 speakers, 120 accents) and Google and IISc's Vaani (speakers
     describe pictures, record their dialect themselves, and every district is covered).
7. **LoRA fine-tuning of the N-ATLAS speech models** on that data, plus real market noise mixed in at 0–20 dB
   and speed changes.
   - Research reports big gains from a few hours of data, and self-training up to −20.5% relative WER.
   - Possibly separate adapters per accent.
8. **Mixed-language fine-tuning:**
   - Use the YECS Yorùbá-English corpus (over 20% lower WER reported).
   - Test on the AfriSwitch benchmark.
   - Normalise Pidgin spellings ("dey"/"de") before scoring, in the spirit of Google's single-writing-system
     approach for Hinglish.
9. **Contribute back:** release the adapters, the benchmark and the dataset card. This targets NAIC's special
   award, "integration into the N-ATLAS ecosystem / co-credit on v2".
10. **Children's speech:** out of scope; documented as such.

## Part 6: UI/UX refresh and a more reliable WhatsApp connection
**WhatsApp reliability** (`src/whatsapp.py`)
- **Permanent token:** use a Meta System User token instead of the 24-hour test token. `check_whatsapp.py` warns
  when the token expires soon.
- **Retries:** `graph_post` and media `download` retry with backoff on 5xx, 429 and timeouts. They log once
  instead of failing silently.
- **Duplicate messages:** `SEEN` currently lives only in memory, so a restart can re-process Meta's retries.
  Move it into a SQLite table with a time-to-live.
- **Delivery tracking:** handle Meta `statuses` webhooks (sent, delivered, read, failed) and count failures on
  `/team`.
- **24-hour window:**
  - Track each trader's last inbound message time.
  - Inside the window, send freely. Outside it, use approved **template messages** (morning brief, private
    link, reminders to the trader).
  - Template names go in `.env`.
- **ffmpeg check** at startup. If it's missing, voice-note replies fall back to text with a clear log line,
  never a broken message.
- **Health checks:** `scripts/check_whatsapp.py` covers webhook reachability, signature, token expiry,
  templates and a test send. `/team` shows the bot's health.
- **Interactive messages:** use buttons and lists for Save, Change and Cancel, language and menus. A
  WhatsApp-native "Open my book" button carries the private link from 2a.

**UI/UX** (`web/app.js`, `web/style.css`, `src/ui_text.py`)
- **WhatsApp-first welcome:** the first screen offers "Use on WhatsApp" (wa.me deep link) and "Use here". There
  is a QR code for desktop.
- **Connection status on Me:** "Connected to WhatsApp ✓ +234 ••• 4567" or a "Connect my WhatsApp" card (2b).
  Records added on WhatsApp show a small WhatsApp badge.
- **Better listening feedback:** a recording waveform and "Listening… / Hearing… / Understanding…" steps. The
  targeted re-ask screen (Part 5) shows the uncertain field highlighted.
- **Clearer Forgot PIN:** the PIN recovery flow goes through WhatsApp.
- **Before building:** the detailed UI changes will be agreed with the team (screens, references) and then
  checked at 320–430px in all 5 languages and dark mode, as in earlier QA.

## Order of work
1. Part 1 cleanup: commit, run tests, push.
2. Part 2a magic link and 2c users: commit.
3. Part 2b connect and merge: commit.
4. Part 2d events and `/team`: commit.
5. Part 4 N-ATLAS backends and benchmark: commit.
6. Part 6 WhatsApp reliability: commit. Part 5, items 1–5 (speech fixes and the market test set): commit.
7. Part 6 UI/UX, after agreeing the screens with the team: commit.
8. Then the `docs/naic/` documents, the PDFs and the video script, aiming to submit on 11 Oct.
9. After submission: Part 5, items 6–9 (data loop, fine-tuning, contributing back).

Each step runs `python eval/run_all.py` before pushing.

## Critical files
- `src/accounts.py`, `src/whatsapp.py`, `src/web.py`, `web/app.js`
- `src/ledger.py` (read only, for merging), new `src/merge.py`
- `src/extras.py`, `src/llm.py`, `src/asr.py`
- `requirements.txt`, `.gitignore`, `.env.example`, `README.md`
- `docs/WHATSAPP.md`, `docs/TECHNICAL.md`
- new `eval/test_link.py`

## Verification
- **Tests:** `python eval/run_all.py` shows every suite passing, including the new `test_link.py`.
  `python eval/run_eval.py --rules-only --cases eval/cases_hard.jsonl` still shows 464/464.
- **Manual run:** `python src/web.py`, then:
  1. Simulate a signed webhook "web" message and open the `/w/<token>` link: the same book loads.
  2. As a guest, add records, use Connect, then simulate `LINK WORD` from the right number: the books merge.
  3. Open `/team?key=…`: the counts are correct and the page shows no names or amounts.
- **Clean checkout:** `git ls-files` shows no `.db`, `.env`, tunnel URLs or deleted files. A fresh clone plus
  `pip install -r requirements.txt` plus `python src/web.py` starts with no other installs.
- **Screenshots:** take Playwright screenshots of the Me screen's Connect sheet and `/team` at 390px wide.
