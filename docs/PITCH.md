# 🎬 Pitch: 90-second video + project card

The jury picks the country top 3 **from the submitted video and materials**. Only the top 3 demo live. The video is our pitch.

## Recording tips
- Screen-record the app on the **public Brev link** (proves it's live), phone-sized window. Voice-over recorded separately with a good mic.
- Rehearse; one take per scene; edit together (CapCut is fine). **Hard limit: 90 seconds.**
- Big text captions for key numbers (judges may watch muted).
- Use fake names only (Mama Tunde, Oga Emeka…) and the flagged demo data.
- Upload as **unlisted YouTube** or Google Drive "anyone with link". Test the link in a private window.

## Script
| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:12 | Photo of a real trader's notebook / market (take your own at a market; ask permission) | "Nigeria has 39 million small businesses. Even among registered SMEs, 95% have a bank account but only 1 in 5 has a loan, and weak records are a big reason why. Most traders sell on credit and keep it in their heads or a notebook." _(caption sources: SMEDAN/NBS 2021; World Bank Enterprise Survey via BusinessDay. The 95% / 1-in-5 figures are for surveyed SMEs, not all 39M micro-businesses, so don't merge them.)_ |
| 0:12–0:30 | **WhatsApp** on a phone: trader sends Pidgin voice note → bot replies with the entry + [✅ Save] → tap (fallback: **Speak** tab in the web app). Pidgin voice note plays → fields fill → ⛔ credit check on Oga Emeka → Confirm | "With TradeVoice, the trader just talks. Whisper, running on our own NVIDIA Brev GPU, hears the Pidgin; NVIDIA Nemotron turns it into a record. And before giving more credit, it warns: Oga Emeka is already 18 days late." |
| 0:30–0:42 | **Snap your book**: handwritten page → table → Save all | "Old notebook? Snap it. NVIDIA's Nemotron vision model reads every line, and the trader checks before anything is saved." |
| 0:42–0:55 | Yoruba voice note → entry, then **Who owes me** → 🔴 late → Pidgin reminder → WhatsApp opens | "Prefer Yoruba, Hausa or Igbo? Meta's omniASR on the same Brev GPU hears it. Then: who owes me, who's late, and a polite reminder, one tap to WhatsApp." |
| 0:55–1:07 | **Insights** + **Ask my book** + **Credit profile** → statement | "It forecasts next week's cash, answers questions like 'how much Mama Tunde owe me?', and builds a transparent record score and statement: a credit history for traders who have none." |
| 1:07–1:20 | Test results table + Brev console screenshot | "We tested __ real voice notes and __ notebook photos: __% of amounts correct, __ seconds per note on Brev. If the AI is down, it falls back to offline rules; every amount is cross-checked." |
| 1:20–1:30 | Privacy tab → team photo | "Audio and photos are deleted, nothing is saved without the trader's OK, and the score is advice, not a loan decision. Next: a WhatsApp bot and a pilot with real traders. We're TradeVoice." |

## Project card (copy into the submission)
- **Name:** TradeVoice
- **One-line story:** Nigerian market traders speak or snap their sales and debts in Pidgin or English; TradeVoice keeps the book,
  chases who owes them, and builds a record they can take to a lender.
- **Team:** ______ (names + roles)
- **Tools:** NVIDIA Brev (Whisper large-v3-turbo + Meta omniASR on GPU) · NVIDIA API (Nemotron text + vision, with fallbacks) · Gradio · SQLite · Python
- **Demo:** ______ (public link) · **Video:** ______ · **Code:** https://github.com/Godzilla-lab/tradevoice
- **Next step:** WhatsApp voice-note bot; tune Yoruba/Hausa/Igbo speech on real traders' notes; pilot with 10 traders in Yaba & Balogun markets;
  partner with a microfinance bank/cooperative to accept the statement.

## 30-second live demo (if we make the top 3)
Speak (Pidgin voice note live) → credit check warning → Who owes me → WhatsApp reminder → statement. Have the demo data
seeded and the voice note pre-recorded as backup in case the room is noisy.

## Roadmap slide / Q&A answers (researched, NOT in the app yet: see `docs/FINANCE_RESEARCH.md`)
Say: *"We researched the new 2026 tax laws and traders' money problems. We only put facts in the app after a tax
professional checks them. Here's what's next."*
- **"Your book protects you" tax card:** tax is on **profit, not sales**; first ₦800k of taxable profit at 0%;
  "nobody will debit your account"; NIN is your free Tax ID; illegal levies → Tax Ombud. Laws are under review (Sep 2026),
  so this ships after a professional check.
- **Rent & school-fees pot:** rent is paid a year upfront (₦500k to ₦5M in big markets) and 42% of informal businesses can't
  survive a month without income → save a little daily; rent history = credit (Kredete's own direction).
- **Loan cost checker:** loan apps charge 2.5–30% **per month** → "₦50k, pay back ₦65k in 4 weeks = 30%/month";
  checks the FCCPC list of ~505 approved lenders and explains the harassment rules.
- **Cash vs transfer on each entry:** lenders trust verifiable records; the statement marks "transfer (verified)" vs
  "cash (self-reported)"; tip against fake transfer alerts.
- **True profit under 15% inflation:** "you sold rice at the same price for 3 weeks but restock went up 12%".
- **Photos as proof (opt-in):** keep supplier receipts and stock photos with the entry they belong to
  (today photos are deleted after reading, for privacy). A photo of goods alone can't be a record: it needs a voice
  note ("I buy these 10 cartons from Alhaji, 90k").
- **Family access & export:** Kippa (about 500k users) shut down and users lost their books. Your book is yours: export it
  anytime, and optionally let family see it if you fall sick.

**Kredete line:** *"Kredete turns rent and payments into credit abroad; TradeVoice turns a market trader's daily voice
notes into the record a lender can trust at home."*
