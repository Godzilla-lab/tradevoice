# UI research behind the 27 Sep redesign

**Why:** the team didn't like the old UI. It looked like a WhatsApp clone, had 5 thin-icon tabs, used green for everything, and had no login.

## What the research says
- **Pictures and voice beat text for low-literacy users.** In Medhi et al. (Microsoft Research, CHI 2009 / ToCHI 2011), none of the non-literate users finished a task on a text-only interface; 72% did with spoken dialog and 100% with a graphical interface. So: big icons plus short words, and a big mic.
- **Numbers are the one "text" everyone reads.** Users recognised numbers on receipts even when they couldn't read the words (Medhi), and CGAP finds numeracy doesn't depend on literacy. So: huge amounts in tabular figures, never abbreviated.
- **Copy the ledger traders already know.** Khatabook and OkCredit grew by copying the paper khata: one ledger per customer with "You gave" (red) and "You got" (green).
- **Keep it flat and never rush the user.** Medhi found deep menus and scrolling hard for non-literate users, and CGAP says oral users need to feel they can finish without being rushed. So: at most 2 levels, one clear main action, and Yes/No before anything is saved.
- **Show that the app is safe to trust.** OPay- and Moniepoint-style "hide balance" eye, the trader's own name and shop on screen, and data tied to their own phone number.
- **Nigeria Data Protection Act (NDPA) 2023:** consent before collecting data, the right to delete, data portability, and a way to contest decisions made purely by machine (s.37), which is why the score has a "tell us" route.

## What we changed
| | Before | Now |
|---|---|---|
| Look | WhatsApp green header | Navy ink + marigold mic; green = money in, red = money out, always with ↓/↑ and +/− |
| Tabs | 5 thin tabs (Chat first) | Home · Customers · **big mic (Talk)** · Insights · Me |
| Home | Chat | Today card (sold − spent), who owes / you owe, 4 big actions, next-7-days insight, recent records |
| Customers | Chat-style thread | Khatabook ledger: "You gave" / "You got" cards and buttons, red balance pills, WhatsApp reminder |
| Me | Score only | Who's logged in, score + "Share with a lender", year, tax, settings, log out, delete account |
| Login | None (one shared book) | Phone number → WhatsApp code or "Confirm with WhatsApp" → shop name + consent. One book per number, shared with the WhatsApp bot |
| Privacy | — | 👁 hide amounts, delete account and book |

## Still missing (ranked by value for the Kredete award vs effort)
1. Consented, time-limited lender link for the score and statement (S–M)
2. Pay link inside reminders, with the debt settling itself (Paystack/Flutterwave test mode) (M)
3. Automatic reminders on the due date (S)
4. WhatsApp receipt or statement to the customer after each record (S)
5. PIN lock on the phone (S)
6. Offline voice-note queue (service worker) (M)
7. CSV export of the book (S)
8. Stock from voice, with low-stock alerts (M)
9. Staff accounts (L), not for the hackathon

Sources: Medhi et al. CHI'09 (microsoft.com/en-us/research/wp-content/uploads/2016/02/medhi_chi2009.pdf); CGAP on illiteracy and innumeracy; Khatabook and OkCredit product pages; Material touch targets (48dp); NDPA 2023 text (cert.gov.ng). The full list is in the research notes from 27 Sep.

## Refinement round (team plan "TRADEVOICE UI/UX CHANGES" + taste-skill redesign audit)
Principle: **You talk. TradeVoice keeps the book.** Speak → AI understands → trader confirms → book updates.

| Plan item | Done |
|---|---|
| Voice → confirmation → ledger (P0) | Every draft shows a card: amount, what happened (↓ in / ↑ out / ⏳ credit), customer ("New customer" tag), item ("2 bags of rice"), pay-by date. **Save / Change / Cancel**. "Nothing is saved until you confirm." Change edits every field (`POST /api/draft`). "✓ Saved to your book" |
| AI uncertainty (P0) | Unsure fields get a "?" and a plain reason: no amount heard (then "Add amount" replaces Save, never guessed), no customer on a debt, no pay-by date, unclear type. Invented amounts are still dropped by the extract guards |
| Home hierarchy (P0) | Today card = **Money in − money out** (real cash: sales paid now + payments in, minus spending + paying suppliers; credit sales shown on their own line, never called profit) → Money to collect (big red, "2 late", "See who owes you →") → big **Tell TradeVoice** button → Scan book · Collect · Lender report → Next 7 days → Recent. Fewer cards |
| Customers (P0/P1) | Rows lead with the balance ("₦16,800" + "2 days late"); detail = balance pinned on top ("You are owed", "18 days overdue"), a dated timeline with running balance, notes and receipts; reminder = **Send on WhatsApp / Edit / Cancel**, never sent automatically |
| Contextual Ask (P0) | Example questions per screen (Home, Customers, Insights, Me) in 5 languages, tappable (a visible alternative to speaking); answered exactly from the book (`assistant.book_answer`), no AI needed |
| Empty states (P1) | Empty home ("Your book is empty. Tell me your first sale." + example sentence + sample records), customers, insights, chat ("Don't know where to start? Just talk.") |
| Rename (P1) | "For lender" → **Lender report**; "Say it / Snap book" → **Tell TradeVoice / Scan book / Collect** |
| Tax UX | **Tax records** (your numbers) + **Tax information** ("General information… confirm with a qualified tax professional") |
| Trust | Sign-up shows: nothing is saved until you confirm · voice notes are deleted after reading · delete your records any time |

**Taste-skill audit applied:** no em/en dashes anywhere visible · sentence-case section titles (no all-caps eyebrows) · no emoji in buttons/labels/toasts (kept only inside chat messages, where they help low-literacy users recognise mic/camera) · toasts say what happened ("Copied", "Link stopped", "PIN set") instead of a bare ✓ · browser `prompt()/confirm()` replaced by in-app sheets (type DELETE to delete an account) · press feedback (scale .98), calm 120-200 ms transitions, hover only on hover devices · `text-wrap: pretty/balance` · tabular numbers · one accent colour (marigold) with semantic green/red only. Kept Noto Sans on purpose: it renders Yoruba tone marks and Hausa hooked letters (ɓ ɗ ƙ) correctly, which most "characterful" fonts don't.

**Also fixed while testing the demo sentence:** amounts said in words followed by a full stop ("…forty-five thousand.") were missed, and quantities said in words ("two bags of rice") were not read. Both fixed; 470 rule cases still pass.
