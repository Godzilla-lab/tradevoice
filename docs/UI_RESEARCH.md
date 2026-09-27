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
