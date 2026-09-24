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
| 0:00–0:12 | Photo of a real trader's notebook / market (take your own at a market; ask permission) | "Nigeria has 39 million small businesses. Almost all have a bank account, but only 1 in 5 has a loan, because they have no records. Traders sell on credit and keep it in their heads or a notebook." _(caption sources: SMEDAN/NBS, World Bank)_ |
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
