# NAIC to-do list: TradeVoice (Innovation & Enterprise track, PS2 Voice-First Access)

**Deadline: Monday 12 Oct 2026, 15:59. Our target: submit Sunday 11 Oct.**
The N-ATLAS integration check is 15–17 Oct, so the live app must stay up and running on N-ATLAS until then.

Write a name in **Owner** and tick each box when it's done. The full technical plan is in
[`../ROADMAP.md`](../ROADMAP.md).

---

## 0. Before anything else (this week)
- [ ] 🚨 **TODAY: add a payment method in Meta Business Manager** (WhatsApp account → Payment settings).
      **From 1 Oct 2026, Meta charges Nigerian businesses about ₦14 (US$0.0101) per service or utility message,
      and stops delivering service messages for accounts with no payment method on file.** Without this, the
      bot goes silent. Owner: ____
- [ ] **Email FMCIDE:** ask whether a prize at the GOMYCODE × NVIDIA hackathon counts as "previously awarded"
      under the eligibility rules. Owner: ____
- [ ] **Decide how we apply:** as individuals (government ID) or as a company (CAC certificate). Owner: ____
- [ ] **Confirm the team list** (1–6 people) and each person's role. Owner: ____
- [ ] **Create the account** on ondi.innox.africa and read the form fields. Paste them into the team chat so we
      can draft the answers. Owner: ____
- [ ] **Create a Modal account** (team workspace), add `HF_TOKEN` as a Modal Secret, and set a spending
      limit. Owner: ____
- [ ] **Accept the N-ATLAS licence** on Hugging Face (NCAIR1/N-ATLaS and the 4 speech models) and create a
      Hugging Face token. Keep it in `.env` only and never share it. Owner: ____
- [ ] **Add the required N-ATLaS attribution** to the app, the README, the PDFs and the video: "N-ATLaS is an
      initiative of the Federal Ministry of Communications, Innovation and Digital Economy, and powered by Awarri
      Technologies." Owner: ____
- [ ] **Email Awarri (datasupport@awarri.com)** to say we're building TradeVoice on N-ATLaS, and ask about
      commercial terms for later. Owner: ____
- [ ] **Rotate the Spitch, Intron and NVIDIA keys** that were visible in screenshots. Owner: ____
- [ ] **Get a permanent WhatsApp token** (Meta System User) and install ffmpeg on the web server. Owner: ____

---

## 1. Working artefact (URL)
**What NAIC wants:** a working build the judges can open: a repository, deployed app, model, live API or dataset.

- [ ] **Code:** N-ATLAS is the main model for understanding and hearing, with backups only when it's down.
      See ROADMAP Part 4. Owner: ____  Due: 6 Oct
- [ ] **Code:** WhatsApp ↔ web as one account (ROADMAP Part 2). Owner: ____  Due: 6 Oct
- [x] **Code:** Paystack payments: auto-settle, a "just paid" WhatsApp to the trader, and a return check
      (ROADMAP Part 10-0). Done 1 Oct.
- [ ] **Switch Paystack on in test mode:**
  1. Create a Paystack account and add the `sk_test_` key to the server `.env` (never in chat or GitHub).
  2. Set the webhook to `https://<public link>/paystack/webhook`.
  3. Pay a test reminder with Paystack's test card and check that the trader's WhatsApp says "just paid".

  Owner: ____  Due: 5 Oct
- [ ] **Pilot traders:** each adds their OPay or bank number in the app (Me → Bank details) for the pay page.
      Owner: ____
- [ ] **Native speakers:** check the Yorùbá, Hausa and Igbo "just paid" message (`src/ui_text.py`, `paid_notice`).
      Owner: ____
- [ ] **Live app:** the always-on web server and the WhatsApp bot, plus the N-ATLAS models on **Modal**, kept
      warm from 6 to 17 Oct. Set a Modal spending limit. Photos are read by the NVIDIA API, so the NVIDIA key
      needs credit. Owner: ____
- [ ] **WhatsApp bot number** working for judges. Write the steps to try it in the README. Owner: ____
- [ ] **Repo cleanup** (ROADMAP Part 1) and the README updated with links and how to test. Owner: ____
- [ ] **Submit:** GitHub link `https://github.com/Godzilla-lab/tradevoice`, the live app link and the WhatsApp
      number.

## 2. N-ATLAS integration evidence (PDF)
**What NAIC wants:** clear documentation and a demonstration of how the build uses the N-ATLAS model, API, ASR
or training pipeline.

- [ ] **Architecture diagram:** voice note → N-ATLAS speech → N-ATLAS language model → code checks → book.
      Owner: ____
- [ ] **Where in the code:** the file and function where N-ATLAS is called, for both the LLM and speech.
      Owner: ____
- [ ] **Benchmark:** N-ATLAS against Qwen on our 464 test sentences, as a table. Owner: ____  Due: 8 Oct
- [ ] **Usage share:** how many real requests N-ATLAS answered, with a screenshot of the `/team` dashboard.
      Owner: ____
- [ ] **N-ATLAS's 4 known limits:** show the table from ROADMAP Part 5. Owner: ____
  - **Noise:** ✅ solved for market use; show before and after.
  - **Mixing languages:** ✅ solved for bookkeeping sentences; show before and after.
  - **Accents:** 🟡 partly solved, for names and items in the trader's book; show week 1 vs week 2.
  - **Children's speech:** ❌ out of scope; say so plainly.
  - Only claim what the numbers show.
- [ ] Export to PDF. Owner: ____

## 3. Real-world validation (PDF)
**What NAIC wants:** evidence of testing with real users, real data or live benchmarks: session logs, benchmark
results, or confirmation from beta testers.

- [ ] **Recruit 10–20 real traders:** market women and men, in Yorùbá, Hausa, Igbo and Nigerian English/Pidgin. Owner: ____
      Due: 5 Oct
- [ ] **Get consent:** a simple consent form, read to each trader in their language. Owner: ____
- [ ] **Pilot from 6 to 10 Oct:** reach **50 or more real interactions**, meaning recordings, questions and
      corrections. Owner: ____
- [ ] **Collect short quotes or confirmations** from 3–5 testers, as written notes or voice notes, with
      permission. Owner: ____
- [ ] **Export the anonymised session log** (`/team/export.csv`): no names and no amounts. Owner: ____
- [ ] **Write up the results:** the number of traders, languages, interactions, the funnel, what went wrong and
      what we fixed. Owner: ____
- [ ] Export to PDF. Owner: ____

## 4. Technical documentation (PDF)
**What NAIC wants:** architecture, setup and usage documentation good enough for an independent party to run or
integrate the build.

- [ ] **Update `docs/TECHNICAL.md`:**
  - architecture;
  - setup on Modal, the web server and a Mac;
  - every setting in `.env.example`;
  - the API endpoints;
  - the WhatsApp setup;
  - how to run the tests.

  Owner: ____
- [ ] **Have someone outside the team follow it** on a fresh machine and fix whatever they get stuck on.
      Owner: ____
- [ ] Export to PDF. Owner: ____

## 5. Video demonstration (URL)
**What NAIC wants:** 3–5 minutes showing the build working end to end, ideally with a real user speaking a
Nigerian language.

- [ ] **Write the script:** problem → a trader sends a WhatsApp voice note in Yorùbá, Hausa or Igbo →
      confirmation → asks "who owes me?" → the private link opens the book on the web → reminder draft → N-ATLAS
      explained → results. Owner: ____
- [ ] **Film a real trader** at the market, with their consent. Have a backup take in a quiet place.
      Owner: ____  Due: 9 Oct
- [ ] **Screen-record** the WhatsApp and web parts. Add English subtitles for the Nigerian-language speech.
      Owner: ____
- [ ] **Edit to 3–5 minutes.** Upload to YouTube (unlisted) or Google Drive with "anyone with the link" access,
      and test the link logged out. Owner: ____

## 6. Team profile (PDF)
**What NAIC wants:** bios, affiliations and roles of all team members.

- [ ] Each member sends: full name, role on TradeVoice, a 2–3 line bio, their school or company, and their
      LinkedIn or GitHub. Owner: everyone  Due: 7 Oct
- [ ] Put them into one PDF. Owner: ____

## 7. Endorsement or registration evidence (PDF)
**What NAIC wants:** a CAC certificate for a registered entity, or a valid government-issued ID for an individual
developer.

- [ ] **If applying as a company:** a CAC certificate PDF. Owner: ____
- [ ] **If applying as individuals:** a scan of a valid government ID (NIN slip, passport, driver's licence or
      voter's card). Owner: ____
- [ ] ⚠️ **Never put IDs or the CAC certificate in GitHub.** Keep them in a private folder only.

---

## Final check (Sunday 11 Oct)
- [ ] All 7 items are uploaded. Every link opens in a private, logged-out browser window.
- [ ] Problem statement selected: **PS2, Voice-First Access** (one only).
- [ ] Everything is in English (non-English speech in the video has subtitles).
- [ ] The live app and WhatsApp bot are running and stay up through **17 Oct** for the N-ATLAS integration
      check.
- [ ] Submitted, and the confirmation screenshot is saved.

## Timeline at a glance
| Date | What |
|---|---|
| 1–3 Oct | Step 0 done; code for N-ATLAS and WhatsApp ↔ web started |
| 4–5 Oct | Traders recruited; consent form ready |
| 6 Oct | N-ATLAS and WhatsApp ↔ web live (Modal kept warm); pilot starts |
| 6–10 Oct | Pilot running: 50+ real interactions |
| 8 Oct | Benchmark done |
| 9 Oct | Video filmed (include a Paystack test payment → "just paid" WhatsApp) |
| 10 Oct | All PDFs written; video edited |
| 11 Oct | **Submit** |
| 15–17 Oct | N-ATLAS integration check: keep everything running |
| 18–20 Oct | Shortlisting |
