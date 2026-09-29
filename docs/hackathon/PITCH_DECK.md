# TradeVoice pitch deck: slide by slide

Kawasaki structure: cover → problem → value proposition → underlying magic → business model.
11 slides, about 5 minutes plus the live demo. **On the slide** = what the audience reads (keep it short).
**Say** = what the presenter says. Fill in everything in [brackets] before presenting.

---

## 1. Cover

**On the slide**
> **TradeVoice**
> Records that speak your language.
> Voice-first bookkeeping for Nigerian market traders, on WhatsApp and the web.
>
> [Team name] · GOMYCODE × NVIDIA "Come Build with AI" · 27 September 2026
> [Presenter name], [role] · [email] · [phone]

**Say**
"Good afternoon. We're [team]. TradeVoice lets a market trader keep proper business records just by talking, in
English, Pidgin, Yorùbá, Hausa or Igbo."

---

## 2. The problem

**On the slide**
> **Business happens fast. Record-keeping doesn't.**
>
> Where the records live today: memory · notebooks · WhatsApp chats · scattered transfers
>
> Questions that stay hard to answer:
> How much did I sell? · Who still owes me? · What did I spend? · How much cash should I have?

**Say**
"A trader in Balogun sells on credit all day. 'Mama Tunde, take it, pay me Friday.' By evening, that debt lives in
her head or a torn notebook. She loses money to debts she forgot, and when she goes to a bank or a lender for a loan,
she has nothing to show. No records, no credit."

---

## 3. The insight

**On the slide**
> **Traders do keep records. Accounting software just doesn't fit how they work.**
>
> Voice · photos · messages → **TradeVoice** → a reliable ledger
>
> We meet traders where they already are: talking, and on WhatsApp.

**Say**
"The problem isn't discipline. It's that bookkeeping apps expect typing, forms and English. Traders already talk and
already use WhatsApp. So we built the book into the conversation."

---

## 4. The product

**On the slide**
> **Just say what happened.**
>
> 🎙 **Speak**: "I sell Mama Tunde two bags of rice for forty-five thousand. She go pay Friday."
> 📷 **Snap**: a photo of today's notebook page
> 💬 **Type**: or just type it
>
> 5 languages: English · Pidgin · Yorùbá · Hausa · Igbo
> Works in the web app **and** as a WhatsApp bot, on the same book.

**Say**
"The trader sends a voice note, in the language they think in. TradeVoice replies in that language, as text and as a
voice note, so traders who can't read are included too."

---

## 5. Trust: AI proposes, the trader confirms

**On the slide**
> **Nothing is saved until the trader says yes.**
>
> Capture → Understand → **Review** → Confirm → Record
>
> - The trader sees exactly what TradeVoice understood: customer, amount, item, due date
> - Anything unsure is marked, never guessed
> - Wrong amount? "No be 20,000, na 2,000" fixes the same record
> - **The AI can never invent an amount the trader didn't say**

**Say**
"Money is serious, so the AI never writes to the book by itself. It shows a card: this is what I heard. The trader
taps Save, Change or Cancel. If they correct it, even in Pidgin, the same card is fixed; it doesn't create a second
record. We added that after real testing on WhatsApp."

---

## 6. Under the hood (the magic)

**On the slide** (draw it as a flow, left to right)
> Voice note / photo / text (WhatsApp or web)
> ↓
> **Intron Sahara**: hears Nigerian English, Pidgin, Yorùbá, Hausa, Igbo, and mixed sentences
> ↓
> **Qwen2.5-14B on an NVIDIA Brev GPU** (vLLM): turns words into a transaction
> **Qwen2.5-VL on Brev**: reads photographed notebook pages
> ↓
> **Code guards**: amounts must have been said · corrections merged · unsure fields flagged
> ↓
> Confirmation card → the trader's own book (one private book per phone)
> ↓
> Answers **calculated from the book, not guessed by the AI**, and spoken back by **Intron** voices

**Say**
"Hearing is Intron, built for African languages. Understanding runs on our own GPU on NVIDIA Brev: a 14-billion
parameter Qwen model, plus a vision model for notebook photos. But we don't trust the model with money. Code checks
every number against what was actually said. And when you ask 'who owes me the most?', the answer is added up from
the book, never made up by the AI. Now let me show you."

---

## 7. Live demo (≈90 seconds)

**On the slide**
> **Live demo**

**Do** (in this order)
1. Say: "I sell Mama Tunde two bags of rice for forty-five thousand. She go pay Friday."
2. Show the card: customer, ₦45,000, rice ×2, credit, due Friday, "new customer".
3. Tap **Change** → make it ₦46,000 → **Save**. Home updates: Mama Tunde owes ₦46,000.
4. Ask: "Who owes me the most?" → exact answer from the book.
5. **Prepare reminder** → WhatsApp message with a pay link, sent only when the trader taps Send.
6. Switch to Yorùbá: "Ṣé mo ní gbèsè lọ́wọ́ Alhaji?" → answer in Yorùbá, spoken.
7. (If time) The same thing on WhatsApp with a voice note.

**Backup**: if the internet fails, play the recorded demo video.

---

## 8. Beyond bookkeeping

**On the slide**
> **From records to a better-run business**
>
> - **Who owes me**: balances, promised dates, late payers
> - **Reminders with pay links**: drafted, the trader sends them (never automatic)
> - **Credit limits**: "Iya Bisi limit 30k", with a warning before selling over it
> - **Statements**: one tap, a customer's open items and balance
> - **Margins and cheapest supplier**: from what the trader already said
> - **Usual orders**: "Mama Tunde buys 4 crates every Monday" as a ready draft
> - **Privacy**: hide amounts at the stall, PIN lock, download or delete the book, offline voice notes

**Say**
"Once the records exist, the useful things follow: who to chase, what to charge, where to buy cheaper. We built these
for wholesalers after talking to traders."

---

## 9. Financial inclusion: a credit history from everyday trade

**On the slide**
> **No records → no credit. TradeVoice creates the record.**
>
> - Every confirmed sale, payment and debt builds a real trading history
> - **Lender link**: the trader chooses to share a read-only report for 1, 7 or 30 days, and can stop it any time
> - Lenders see sales, repayments and how reliably customers pay, without asking for bank statements the trader doesn't have

**Say**
"This is the part we care about most. Millions of traders are invisible to lenders. Their history already exists in
their daily trade; it just isn't written down. TradeVoice writes it down, and the trader decides who sees it."

---

## 10. Business model

**On the slide**
> **Free for traders. Paid by the value around them.**
>
> 1. **Lenders** pay per consented trader report: [₦ price]
> 2. **Pay links**: a small fee on customer payments collected through TradeVoice (Paystack): [x%]
> 3. **Wholesaler plan**: credit limits, statements, repeat orders, multiple shops: [₦ / month]
>
> Traders never pay to keep their own records.

**Say**
"Traders keep their records for free, because adoption and trust come first. Money comes from lenders who want
reliable borrowers, from payments collected through pay links, and from bigger wholesalers who need more tools."

---

## 11. Proof, team and ask

**On the slide**
> **Built and tested, not a mock-up**
> - Working web app + WhatsApp bot on NVIDIA Brev
> - 464 test sentences understood correctly; about 250 automated feature checks passing
> - Tested with real traders' WhatsApp messages, and improved from their corrections
>
> **Team**: [Name, role] · [Name, role] · [Name, AI & Brev lead] · [Name, role]
>
> **Next**: pilot with [number] traders in [market] · native-speaker review of the 5 languages · lender partner
>
> **TradeVoice: business records, in your own words.**

**Say**
"TradeVoice works today: web and WhatsApp, five languages, running on NVIDIA Brev. Next, we want to pilot it in a real
market and bring in a lender partner. Thank you."

---

### Checklist before presenting
- [ ] Fill in all [brackets]: names, contacts, prices, pilot plan.
- [ ] Delete the blank last slide from the old deck.
- [ ] Demo data loaded (Me → Try with sample records) and a hard refresh on the demo phone.
- [ ] Brev app running; tunnel URL set in Meta; `check_whatsapp.py` all green.
- [ ] Demo video downloaded offline as a backup.

---

## The 90-second demo script

One presenter talks, one drives the phone (screen mirrored). Times are cumulative. Start on the app's Home screen with
an **empty book**, language English.

| Time | Do | Say |
|---|---|---|
| 0:00 | Hold up the phone, Home screen | "Meet Chioma. She sells rice and provisions in the market. This is her book. Watch her use it." |
| 0:07 | Tap the mic, speak | *"I sell Mama Tunde two bags of rice for forty-five thousand. She go pay Friday."* |
| 0:15 | The card appears | "TradeVoice heard her in Pidgin and shows exactly what it understood: Mama Tunde, forty-five thousand, two bags of rice, on credit, due Friday. And it flags Mama Tunde as a new customer." |
| 0:25 | Tap **Change**, set ₦46,000 | "The price was actually forty-six. She fixes it. Nothing is saved until she says so." |
| 0:32 | Tap **Save**, go to Home | "Saved. Her book now shows Mama Tunde owes forty-six thousand, due Friday." |
| 0:38 | Tap Ask, say *"Who owes me the most?"* | "She can ask her book anything." |
| 0:44 | Answer shows + speaks | "That answer is added up from her records, not guessed by the AI." |
| 0:50 | Customers → Mama Tunde → **Prepare reminder** | "Friday comes. One tap drafts a polite WhatsApp reminder with a pay link. Chioma sends it herself; TradeVoice never messages her customers on its own." |
| 1:02 | Switch the language pill to **Yorùbá**, speak *"Ṣé mo ní gbèsè lọ́wọ́ Alhaji?"* | "Now in Yorùbá: 'Do I owe Alhaji?'" |
| 1:10 | Answer in Yorùbá, spoken | "Same book, her language, spoken back so she doesn't need to read." |
| 1:17 | Show the WhatsApp chat with the bot | "And if she never installs anything, it all works on WhatsApp with voice notes." |
| 1:24 | Back to the slide | "Every record she confirms builds a trading history she can choose to share with a lender. That's TradeVoice." |
| 1:30 | End | |

**If something breaks:** say "Let me show you the recording" and play the backup video from the same timestamp.
Don't debug on stage.

**Rehearse** with a stopwatch at least three times. Speak into the phone from about 20 cm, in a quiet corner of
the room if possible.
