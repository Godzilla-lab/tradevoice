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
  - **Where it runs:** on **Modal** with vLLM on one L4 GPU (see Part 7), or on the Mac with
    `mlx_lm.server` for development.
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
  - **All four are Whisper Small (244M, ~500 MB each)**; see [`naic/NATLAS_FACTS.md`](naic/NATLAS_FACTS.md).
  - **Where it runs:** first try the **always-on server's CPU** (no cold start); if too slow, the same Modal app as
    the LLM. Notes over 30 s are chunked.
  - **Guard against repetition loops:** cap output length, detect repeats, re-ask, and never take an amount
    from a looping transcript.
  - **Decision (1 Oct): no separate Pidgin speech model.** Pidgin and English voice notes both go to
    `NigerianAccentedEnglish`, whose training includes Pidgin phrases. Pidgin sentences stay in our normal test
    set; they are not tracked as a separate risk.
  - **Backup:** Intron.
- **Startup checks:** `scripts/check_models.py` checks the Modal N-ATLAS endpoints (and wakes them). `/team` shows the share of requests each engine served.
- **Licence (confirmed on the model card; details in `naic/NATLAS_FACTS.md`):**
  - **Attribution:** the required wording goes in the app (Me → About), the README, the PDFs and the video.
  - **User cap:** at most 1,000 active users in a rolling 30 days. `/team` tracks it and warns at 800.
  - **Commercial use:** contact Awarri before charging traders.
  - **Lenders:** N-ATLaS is never used to profile or score traders for lenders.
  - **Fine-tunes** use the same terms.
- **Card settings and weak spots:**
  - Use the official chat template with `date_string`, temperature 0.1, repetition penalty 1.12, and
    `--max-model-len 8192`.
  - **Yorùbá scores 2.69/5 on the card**, so Yorùbá replies use our reviewed templates, and Yorùbá is
    benchmarked separately.
- **Prompts:** 3–5 worked examples in the trader's language in every N-ATLaS prompt. The independent AfroBench
  evaluation found about +10 points from few-shot.
- **Benchmark:** run our 464 sentences, plus a tool-call test set, through **N-ATLaS, base Llama-3-8B-Instruct
  and Qwen**, zero-shot and few-shot, **per language**. Put the results in `docs/RESULTS.md`.
  - This shows how much N-ATLaS improves market bookkeeping over its own base model.
  - Same method as the [AfroBench N-ATLaS report](https://huggingface.co/blog/seun-ajayi/n-atlas-evaluation-report).
  - This uses Modal or a Kaggle notebook, because the free GPU's 16 GB needs the 4-bit model.
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
| 1 | Working artefact | URL | The public GitHub repo and the live app link (always-on web app plus the N-ATLAS models on Modal, kept warm through 17 Oct) |
| 2 | N-ATLAS integration evidence | PDF | `docs/naic/NATLAS_INTEGRATION.md`: architecture diagram; where N-ATLAS LLM and ASR are called (file and function); engine-share stats from `/team`; benchmark of N-ATLAS against Qwen on the 464 sentences |
| 3 | Real-world validation | PDF | `docs/naic/VALIDATION.md`: anonymised session log (`/team/export.csv`) with 50 or more real trader interactions in Nigerian languages, the funnel, screenshots, and beta-tester confirmations |
| 4 | Technical documentation | PDF | `docs/TECHNICAL.md` updated: architecture, setup, environment variables, deploying N-ATLAS on Modal or running it on the Mac, API |
| 5 | Video demonstration | URL | 3–5 minutes, end to end, **ideally a real trader speaking Yorùbá, Hausa or Igbo** on WhatsApp, then the private link to the web book. We write the script; the team films it. |
| 6 | Team profile | PDF | `docs/naic/TEAM.md`: bios, affiliations and roles. Filled in by the team. |
| 7 | Registration evidence | PDF | CAC certificate or government ID. Provided by the team. |

- **PDFs:** generated from the Markdown with the existing pymupdf or Playwright tooling, into
  `docs/naic/pdf/`. That folder is gitignored, since the PDFs may hold personal information.
- **Team to-do list:** [`docs/naic/CHECKLIST.md`](naic/CHECKLIST.md) tracks the 7 items, owners and dates.
- **Plan:** have about 3 days of real-trader pilot before the 11 Oct submission.

## Part 5: Working around N-ATLAS's speech limits (based on research)
N-ATLAS's GitHub lists four known limitations. **Rule: we only take on the ones we can clearly solve and prove
with numbers.** Everything else is stated openly as a limit, not hidden.

| N-ATLAS limitation | Do we solve it? | How (simple version) | How we prove it |
|---|---|---|---|
| **Degraded performance in noisy environments** | ✅ **Yes**, for market use | Light audio preparation (no heavy denoising, which research shows makes it worse); ask again for only the unclear part; the confirmation card before saving | The same voice notes with real market noise mixed in: amount and customer correct, **before vs after** |
| **Limited handling of code-switching** (mixing languages) | ✅ **Yes**, for bookkeeping sentences | Two hearing models (Yorùbá, Hausa or Igbo plus Nigerian-accented English) on the same note, merged by N-ATLAS; amounts kept only if actually heard | A mixed-language test set: amount and customer correct, **before vs after** |
| **Dialectal and accent bias** | 🟡 **Partly**: names and words that matter for the trader's book | The trader's own customer names and items passed as hints, plus learning from their corrections. Full accent fixing needs fine-tuning on donated voices, which comes later, after NAIC | Per-trader accuracy over time (week 1 vs week 2), with results reported by region and accent where traders share it |
| **Reduced accuracy with children's speech** | ❌ **No**, out of scope | Our users are adult traders. We don't claim to fix it. | Stated as a known limit in the docs and the NAIC PDF |

**What "solved" means here:** the result that matters for the trader is right, meaning the **amount, customer
and type** of each record. It doesn't mean every word of the transcript is perfect. We report both numbers
honestly, plus anything that got worse.

**Background:** `NCAIR1/Yoruba-ASR` is Whisper-small or MMS fine-tuned mostly on read speech, so it is weaker on
market conversation.

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
- 🚨 **Meta billing (Nigeria, from 1 Oct 2026):**
  - **Charges:** service messages, and utility messages inside the 24-hour window, cost about **US$0.0101
    (≈₦14) each**; marketing messages about US$0.062 (≈₦84).
  - **Payment method:** a payment method must be on the Meta account, or service messages stop.
  - **Cost control:**
    - send **one combined message per reply**, with voice only when the trader has voice on;
    - never send a separate "typing" or "done" message;
    - count messages sent on `/team` (cost per trader per month).
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

## Part 7: Hosting: Modal for N-ATLAS, NVIDIA API for photos
| Job | Where | Why |
|---|---|---|
| N-ATLAS LLM (understanding, answers, replies) | **Modal**, vLLM on 1× L4 (24 GB) | Pay per second, scales to zero, $30/month free credit |
| N-ATLAS speech (4 ASR models) | Same Modal app | Small models; share the GPU |
| Notebook photo reading | **NVIDIA API** (build.nvidia.com), already built in `src/vision.py` (`VISION_MODELS`) | No GPU to host, no cold start, photos are rare |
| Photo backup | Qwen-VL as a separate Modal function, **off unless the API fails** | Emergency only |
| Web app + WhatsApp webhook | Small **always-on VPS** with a persistent disk, behind Cloudflare Tunnel (Part 9a-0) | Must always receive Meta's webhooks; needs no GPU |

**Waking up automatically:** when the GPU is off and a WhatsApp message arrives:
1. The web app answers Meta at once.
2. It calls the Modal URL, and **Modal starts the GPU on that request.**
3. The reply goes out once the model has loaded.
4. After `scaledown_window` (for example 15 minutes) with no requests, it switches off again.

**Hiding the first-message wait:**
- **Wake-up ping:** the moment a voice note or photo arrives, the web app pings Modal, so the model loads while the
  media downloads.
- **Holding message:** if the model isn't ready within a few seconds, the bot sends "⏳ One moment…".
- **Memory snapshots:** use Modal's memory snapshots to shorten the cold start.

| Period | Setting | Rough cost (L4 ≈ $0.80/h, check the Modal dashboard) |
|---|---|---|
| Build and test (now to 5 Oct) | Scale to zero | Mostly covered by the $30 credit |
| Pilot (6–10 Oct) and N-ATLAS integration check (15–17 Oct) | `min_containers=1`, always warm | ≈ $19/day, ≈ $150 for the 8 days |
| After NAIC | Scale to zero, or warm only during market hours | Low |

**Rules:**
- **Spending:** set a spending limit in Modal.
- **Secrets:** keep `HF_TOKEN` and the other keys as Modal Secrets, never in code.
- **Code:** a new `deploy/modal_app.py` (N-ATLAS LLM + ASR) and `NATLAS_URL` / `NATLAS_ASR_URL` in `.env`.
- **Privacy:** photos go to NVIDIA's cloud. The consent text says so, and photos are deleted after reading, as
  today.
- **NAIC:** N-ATLAS has no vision. The lines read from a photo are passed to N-ATLAS to understand, so N-ATLAS
  still does the bookkeeping. This is stated in the integration PDF.

---

## Part 8: Memory and data

### 8a. Personal memory: what TradeVoice remembers about each trader
Stored only in that trader's book. It's deleted with the account, and shown on a **"What TradeVoice remembers"**
screen where the trader can edit or clear any item.

| Remembers | Used for |
|---|---|
| Nicknames ("Mama T" = Mama Tunde) | The right customer without asking |
| Usual price per item | Catching mistakes: "You said ₦4,500. Did you mean ₦45,000?" |
| Usual orders | "Same as last week" records the whole order (builds on repeat orders) |
| Corrections (heard "Mama tune" → "Mama Tunde") | Personal word list passed to N-ATLAS speech as hints (Part 5, item 2) |
| How each customer pays | Better reminders and suggested credit limits |
| Preferences (language, voice on or off, summary time) | No repeated questions |

New table `memory(id, kind, key, value, source, created_at, updated_at)` in the book.

### 8b. Long chat memory: two to three weeks and more, without overflowing the model
N-ATLAS (Llama-3 8B) reads about 8,000 tokens at a time, so we never send the whole history. Five layers:
1. **The book:** every record, forever. **Money questions are answered by code reading the book, never from the
   model's memory**, so they're always exact. This is our "AI never invents amounts" rule.
2. **Full chat history:** a new `chat_log(id, ts, role, channel, text, record_id)` table in the trader's book. It
   holds every message, transcript and reply, kept 90 days (setting `CHAT_DAYS`).
3. **Recent messages:** the last 10–20 turns go into every prompt, so "change that to 2k" and "same as before"
   work.
4. **Summaries and facts:**
   - Each night N-ATLAS writes a few lines about the day, then rolls them into a weekly note (`chat_summary`
     table).
   - Promises, nicknames and preferences go into `memory` (8a).
   - Summaries point to records; they never restate amounts as facts.
5. **Search:** when the trader asks about the past, search `chat_log` by customer, date or topic (SQLite FTS5,
   embeddings later if needed) and add only the matching lines.

**Prompt budget, about 7,000 tokens in total:**

| Part | Tokens |
|---|---|
| Instructions | ~1,000 |
| Facts | ~500 |
| Summaries | ~1,000 |
| Search results | ~1,500 |
| Recent messages | ~2,000 |
| Answer | ~1,000 |

**Example:**
- "Wetin Alhaji Musa tell me about the money last time?"
- Search finds 12 Sept: "He said he'll pay after Sallah." The book shows ₦85,000 owed, 18 days late.
- Answer: "On 12 Sept, Alhaji Musa said he'll pay after Sallah. He still owes ₦85,000, 18 days late. Should I
  draft a reminder?"

**Controls:**
- "Forget" clears the chat history and memory.
- Deleting the account deletes everything.
- Nothing is ever shared between traders.

### 8c. Using data to improve the platform: three consent levels
| Level | What | Consent | Used for |
|---|---|---|---|
| 1. Usage counts | Events only: kind, language, engine, OK or error. No names, amounts or text (Part 2d). | On for all, disclosed in the consent message | `/team` funnel, finding what breaks; NAIC validation evidence |
| 2. "Help improve TradeVoice" | Heard → meant corrections and text → saved-record pairs, **names replaced, amounts shifted** | Opt-in, off by default | New real-world test sentences; fine-tuning N-ATLAS for market bookkeeping |
| 3. "Donate your voice" | Audio clips with names and amounts bleeped, stored apart from books | Separate opt-in, off by default | Fine-tuning the N-ATLAS speech models for accents, noise and mixed languages (Part 5); an N-ATLAS dataset contribution |

- **Give back:**
  - Thank voice donors, for example with airtime per donated hour (Karya-style), and show them "Your voice
    helped TradeVoice understand Ijebu Yorùbá better."
  - Publish **market price insights** ("rice up 8% in Lagos markets"), but only from groups of **10 or more
    traders**, so no single trader can be identified.
- **Credit and lenders:** only through the existing lender link, with explicit per-lender consent. **Data is
  never sold.**

### 8d. Rules (Nigeria Data Protection Act 2023, regulator: NDPC)
- **Consent and purpose:** clear consent in all 5 languages for each purpose; collect only what's needed.
- **Trader rights:** traders can see, export and delete their data, and withdraw consent at any time.
- **Separate storage:** traders' books, the usage log and the training data are kept apart. Only anonymised,
  consented data is used for training.
- **Retention:**
  - raw voice notes are deleted after reading unless donated;
  - chat history is kept 90 days;
  - training data is reviewed yearly.
- **Before collecting voice at scale:** do a short data-protection impact assessment, and get legal advice.

### 8e. When
- **Before 12 Oct:**
  - Level 1 usage counts (`/team`).
  - Personal memory: nicknames, usual prices and corrections, because they directly help N-ATLAS hear
    better.
  - Chat history plus recent messages (layers 2 and 3).
- **After NAIC:**
  - Nightly summaries and search (layers 4 and 5).
  - The "What TradeVoice remembers" screen.
  - Levels 2 and 3 with consent screens.
  - Market price insights.

---

## Part 9: Where data is stored, and how it is cleaned

### 9a-0. The stack (what we use for data and processes)
| Job | Use | Why |
|---|---|---|
| Public link, HTTPS, domain | **Cloudflare Tunnel and DNS** (`cloudflared`, already used) | Free; no open ports on the server |
| Backups and training-data storage | **Cloudflare R2** (S3-compatible) | No download fees, so Modal can pull training data for free; small free tier |
| Web app, WhatsApp webhook, traders' books | **Small VPS with a persistent disk** (Hetzner, DigitalOcean or similar, ~$5–10/month) | Python plus one SQLite file per trader needs a normal disk; Cloudflare Workers and Modal volumes don't fit this |
| Live backups | **Litestream** on the VPS → R2, restore tested monthly | Lose seconds, not days, if the server dies |
| Nightly jobs (9b checks, retention, summary triggers) | **cron or systemd timers** on the VPS | Simple; summaries call N-ATLAS on Modal |
| N-ATLAS LLM and speech | **Modal** (Part 7) | GPU only when needed |
| Photo reading | **NVIDIA API** | No GPU to host |
| Training-data pipeline (9c) | **Modal job**: reads R2, writes the cleaned version back to R2 | On demand; a GPU only for the timestamp step |
| Dataset versions | R2 folders (`v0.1/`, `v0.2/`…) plus a private Hugging Face dataset when shared with NCAIR | Clear history; easy hand-over |

**Not now:**
- **Cloudflare D1:** it would mean rewriting how the per-trader books are stored.
- **A data warehouse** (BigQuery or Snowflake): overkill. SQLite plus `/team` is enough until thousands of
  traders.

### 9a. Where each kind of data lives
| Data | Where | Format | Kept | Who can access |
|---|---|---|---|---|
| **Trader's book**: records, customers, `memory`, `chat_log`, `chat_summary` | Web server disk, `books/<phone>.db`, **one SQLite file per trader** (as today) | SQLite, WAL mode | Until the trader deletes it; `chat_log` 90 days | Only that trader through the app; the team only for support, logged |
| **Accounts**: users, sessions, logins, shares, pay links, `magic` | Web server, `accounts.db` | SQLite | While the account exists | App only |
| **Usage counts** (`events`, Part 2d) | Separate `analytics.db` on the web server | SQLite → daily anonymised CSV | 12 months | Team, via `/team` |
| **Voice notes and photos in transit** | Temporary files on the web server | Original | **Deleted right after reading** (as today) | Nobody |
| **Training data** (consent levels 2 and 3) | **Separate private bucket** (`tradevoice-training`), never left on the app server | Text JSONL; audio FLAC, 16 kHz mono; plus a manifest | Per dataset version, reviewed yearly | 1–2 named people, access logged |
| **Backups** | Encrypted object storage on **Cloudflare R2** | Encrypted SQLite snapshots | 30 days, rolling | Restore only |
| **Model weights** | Modal Volume | HF format | — | Deploy only |
| **Secrets** | `.env` on the server, Modal Secrets | — | Rotated when exposed | Admins |

**Storage rules:**
- **Modal keeps no trader data.** It receives a request, answers, and logs nothing that contains content.
  Prompt and request logging is turned off.
- **Backups:** Litestream streams each SQLite file continuously to the encrypted bucket. A restore is tested
  every month.
- **Encryption:** disks and backups are encrypted at rest; everything travels over TLS.
- **Where data is stored:** choose the storage region on purpose. Cross-border transfers need the safeguards in
  the NDPA, so this is written down in the privacy notice.
- **Data breaches:** a written breach plan; the NDPA requires notifying the NDPC within 72 hours.

### 9b. Keeping the live books clean (every day, automatic)
- **Duplicate customers:** "Mama Tunde", "mama tunde" and "Mama T" are spotted by fuzzy matching plus the
  nicknames in `memory`. The trader is **asked** to merge them, never merged automatically.
- **Validation on save:**
  - amount above 0 and below a sanity limit;
  - dates make sense;
  - the customer exists;
  - the type matches the words (a credit sale has a customer);
  - unsure fields flagged (as today).
- **Nightly integrity check:** orphan `customer_id`s, negative balances caused by bad data, and SQLite
  `PRAGMA integrity_check`. Problems are reported on `/team`.
- **Retention jobs:** delete `chat_log` older than `CHAT_DAYS`; drop expired `magic`, `logins` and `sessions`
  rows; delete merged guest books after 7 days.

### 9c. Cleaning pipeline for training data (`scripts/build_dataset.py`, run by hand per release)
1. **Consent filter:** only rows whose trader has level 2 or 3 consent *today*. Withdrawn consent drops them
   from the next version.
2. **Remove personal details (text):**
   - Customer names → `[CUSTOMER]`, using **the trader's own customer list and nicknames first**, which beats
     generic tools on Nigerian names. A general PII detector (for example Microsoft Presidio) is a second
     pass.
   - Phone numbers, bank account numbers, BVN/NIN and emails, found by pattern → `[PHONE]`, `[ACCOUNT]`.
   - Amounts → scaled by one random factor per sample, so the maths stays consistent.
   - Market and street names → city level.
3. **Remove personal details (audio):** use word timestamps from the speech model to **bleep** names and numbers.
   If a clip can't be cleaned with confidence, it is dropped.
4. **Audio quality:**
   - convert to 16 kHz mono and trim silence;
   - reject clips under 1 s or over 30 s, clips that are clipped (distorted), and clips that are only noise;
   - store the estimated noise level (SNR) as a label, not a reason to reject, because we need noisy
     examples.
5. **Text normalisation:**
   - Unicode NFC, so Yorùbá tone marks are stored one consistent way.
   - Keep both the raw and normalised text.
   - Pidgin spelling map ("dey"/"de"), applied only when scoring.
   - Numbers kept both as said ("45k") and normalised ("45000").
6. **Labels:**
   - language, from the trader's setting plus automatic language ID;
   - a **code-switch** flag;
   - noise level;
   - channel (WhatsApp or web);
   - accent or region, only if the trader opted to share it.

   **Trader-corrected pairs are marked "gold".**
7. **Remove duplicates:**
   - exact and near-duplicate text, using a hash of the normalised text;
   - duplicate audio, using an audio fingerprint;
   - a limit on clips per speaker, so no single trader dominates.
8. **Human check:**
   - Native speakers review a sample of about 10% per language and check the redaction.
   - Agreement between reviewers is measured, and a batch is rejected if names leak.
9. **Splits by speaker:** train, dev and test, with no speaker in more than one, so results aren't inflated.
   The **test set is frozen**; it is our market benchmark (Part 5, item 5).
10. **Version and document:**
    - Each release is versioned (v0.1, v0.2…).
    - A **dataset card** records the sources, consent basis, languages, hours, label meanings, known gaps and
      licence.
    - A deletion log records whose data was removed and when.

**Automated test:** `eval/test_dataset.py` feeds samples with known names, phone numbers and amounts through the
pipeline and **fails if any of them survive**.

### 9d. Release outside the team (for example an N-ATLAS contribution)
Only with explicit level 3 consent, after redaction checks pass, with the dataset card and a licence that
NCAIR/Awarri can use. Individual books are never released.

---

## Part 10: Payments (OPay first)
**Why OPay:**
- About 50M users and 39M monthly actives in 2025.
- Installed on **69% of Nigerian smartphones**, with about 40% of the mobile money market.
- OPay-to-OPay transfers are **free**.

Most traders and their customers already have it.

**Rule:** TradeVoice **never holds anyone's money**. Money goes from the customer to the trader's own OPay or bank
account through licensed companies. TradeVoice only records it. Collecting for others would need a CBN PSSP
licence. A fintech lawyer checks the setup before real money is used.

| When | What |
|---|---|
| **Pilot (6–10 Oct)** | **Reminders default to OPay:** the trader's OPay number in every drafted reminder. **Reading receipts:** the customer's OPay receipt screenshot or the trader's forwarded OPay alert is read by `vision.py`, matched to the debt (name, amount, time), and confirmed with one tap ("Mark Mama Tunde paid ₦20,000?"). This is the `match_payment` tool. |
| **NAIC demo** | **Paystack virtual account in test mode** (1%, capped at ₦300, when live): a test transfer arrives, the webhook marks the debt paid (part-payments too), and the trader gets a WhatsApp voice note, "Mama Tunde just paid ₦20,000. She still owes ₦25,000." The receipt to the customer is a draft. |
| **After NAIC** | **OPay merchant API** (OPay Checkout): an account number per debt, OPay wallet QR and USSD, with **webhooks for automatic confirmation**. Needs an OPay business account, TradeVoice CAC registration, and identity checks (BVN/NIN) for traders. |

- **Never in code or the repo:** traders' real account numbers live only in their own profile (`users.bank_*`).
- **Code:** `src/extras.py` (pay links and bank details), a new `src/payments.py` (provider webhooks with
  signature checks, `match_payment`), and `vision.py` prompts for OPay receipts.

- **WhatsApp's own in-chat Payments API is not available in Nigeria.** It currently works only in places like
  India and Brazil, through local gateways. So the "Pay" button is a **WhatsApp call-to-action URL button**
  that opens the OPay or Paystack link.
- **Others doing payments in WhatsApp chat:**
  - **Xara** (send money and pay bills by voice note, text or image; works with licensed bank partners; about
    45k users).
  - **Finnova** (banking chatbot).
  - **MYPADI AI** (crypto to naira).

  These are consumer *banking* bots. TradeVoice is *bookkeeping and collecting what customers owe*, so these are
  possible partners (for example, a trader paying a supplier), not the same product.
- **Agent-payment protocols** (Mastercard Agent Pay, Visa Intelligent Commerce and Agentic Ready, which now
  includes Africa, Google AP2, OpenAI and Stripe ACP) are card-based and early in Nigeria. We'll watch them but
  not build on them now.

### 10a. The bigger idea: partner with OPay (pitch once pilot results are in)
OPay has millions of merchants and a growing lending business: about $938M lent in 2025.

**TradeVoice = the voice bookkeeping layer for OPay merchants.** Traders keep clean records by talking. With the
trader's explicit consent, those records help OPay lend to them safely and help traders get fairer loans.

**What we bring to the pitch:**
- pilot numbers: traders, interactions, records kept, and payments matched;
- traders' feedback;
- N-ATLaS / NAIC credibility;
- the OPay receipt-matching feature already working.

**What it would need:**
- a commercial N-ATLaS licence (the free terms cap at 1,000 active users and exclude commercial use);
- a data-sharing agreement where **the trader chooses** and records are shared only with consent, as the lender
  link works today;
- a legal and NDPA review.

**Credit rule:** any lending view is **plain arithmetic over the trader's own book**, never N-ATLaS. The N-ATLaS
terms prohibit profiling, and we keep it out of credit decisions anyway.

**Similar partners to approach later:** Moniepoint, PalmPay and microfinance banks.

**Owner and timing:** draft a one-page pitch after the pilot (late October). Find a warm introduction through
ONDI, the NAIC network or the investor introductions.

---

## Order of work
1. Part 1 cleanup: commit, run tests, push.
2. Part 2a magic link and 2c users: commit.
3. Part 2b connect and merge: commit.
4. Part 2d events and `/team`: commit.
5. Part 4 and Part 7: N-ATLAS backends on Modal, photo reading via the NVIDIA API, benchmark: commit.
   Part 8a and 8b (personal memory, chat history, recent messages): commit.
6. Part 6 WhatsApp reliability: commit. Part 5, items 1–5 (speech fixes and the market test set): commit.
7. Part 6 UI/UX, after agreeing the screens with the team: commit.
8. Then the `docs/naic/` documents, the PDFs and the video script, aiming to submit on 11 Oct.
9. Before the pilot (by 6 Oct): Part 9a backups and encryption, 9b validation and retention jobs.
10. Pilot payments (Part 10): OPay default in reminders, OPay receipt matching; Paystack test-mode demo.
11. After submission: OPay merchant API and the OPay partnership pitch (Part 10a); Part 9c and 9d dataset pipeline; Part 5, items 6–9 (data loop, fine-tuning, contributing back) and Part 8 (summaries,
   search, memory screen, consent levels 2–3, market insights).

Each step runs `python eval/run_all.py` before pushing.

## Critical files
- `src/accounts.py`, `src/whatsapp.py`, `src/web.py`, `web/app.js`
- `src/ledger.py` (read only, for merging), new `src/merge.py`
- `src/extras.py`, `src/llm.py`, `src/asr.py`, `src/vision.py`, new `deploy/modal_app.py`
- `src/converse.py` and `src/assistant.py` (memory and chat history in prompts)
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
