# TradeVoice: design plan for the redesign (October 2026)

For the designer. Covers who we design for, the rules, every screen and state, the WhatsApp messages, assets and
the hand-over. The product plan behind it is in [`ROADMAP.md`](ROADMAP.md); NAIC deadlines are in
[`naic/CHECKLIST.md`](naic/CHECKLIST.md).

**Key dates**
| Date | What |
|---|---|
| **Fri 3 Oct** | Direction agreed: logo, colours, type, and the 3 key screens as wireframes |
| **Sun 5 Oct** | Final designs for every "P1" screen below (light + dark, phone size) |
| **6–8 Oct** | Developers build them; designer reviews on a real phone |
| **9 Oct** | Video filmed on the new design. App screenshots and video frames needed |
| **11 Oct** | NAIC submission |

Anything marked **P2** can wait until after NAIC.

---

## 1. What TradeVoice is (one paragraph)
A market trader says what happened in a WhatsApp voice note, in English, Pidgin, Yorùbá, Hausa or Igbo:
*"I sell Mama Tunde two bags of rice for forty-five thousand, she go pay Friday."* TradeVoice understands it,
shows what it understood, saves it only when the trader agrees, and keeps the book: who owes, who paid, profit,
reminders and payments.

There are two front doors to **one book**:
- **WhatsApp** (main, where traders already are)
- **The web app** (the "big screen" for the same book)

It runs on **N-ATLaS**, Nigeria's own AI model.

## 2. Who we design for
**Primary: "Mama Chioma"**
- 45, sells rice and garri at Balogun market.
- Uses WhatsApp and OPay every day, on a cheap Android phone.
- Bright sunlight, noisy market, one hand often busy.
- May not read well (or at all). Thinks in naira and in her customers' names.
- Speaks Yorùbá or Pidgin.

**Also**
- **A young wholesaler** (25–35): reads fine, wants speed, statements and margins.
- **The customer who owes money** (Mama Tunde): only ever sees **the pay page** and messages the trader forwards.
- **A lender or judge:** sees the lender report and demo; needs trust and clarity.

## 3. Design principles (non-negotiable)
1. **Voice first.** The microphone is always the biggest, easiest thing on screen. Every key action works without
   reading: icon + number + colour + a short word.
2. **Feels like WhatsApp, isn't WhatsApp.** Familiar chat patterns (bubbles, voice-note bubbles, ticks), but our own
   brand.
   - Never use WhatsApp's logo or name as ours; only on "Send on WhatsApp" and "Open WhatsApp" buttons.
3. **Money is big and unmistakable.** Always "₦45,000" (naira sign, commas), bold.
   - **Money in = green ↓, money out = red ↑, late = amber with a word** ("2 days late").
   - Never colour alone.
4. **Nothing is saved without the trader.** The confirmation card (Save / Change / Cancel) is the heart of trust.
   It must feel calm and clear, never pushy.
5. **TradeVoice never messages customers by itself.** Reminders, receipts and statements are always **drafts the
   trader sends**. The design must make that obvious ("You send it").
6. **Plain words.** A 10-year-old should understand every label. No jargon ("ledger", "transaction", "sync").
7. **Built for sunlight and cheap phones.**
   - Contrast at least WCAG AA (aim AAA for money and buttons).
   - Body text 16 px or more, touch targets 48 px or more.
   - Works at **320 px** wide.
   - Light and dark mode.
8. **Honest AI.** When unsure, show it (a highlighted field, "I didn't catch the amount"), never hide it.

## 4. Brand
**Current tokens** (`web/style.css`, top of file). Keep the feel or improve it, but deliver **both light and dark**:

| Token | Light | Dark | Used for |
|---|---|---|---|
| `--ink` | #13233F | #EEF1F7 | Main text |
| `--bg` | #FAF7F0 | #0F1726 | Page (warm paper) |
| `--surface` | #FFFFFF | #18233A | Cards |
| `--accent` | #F2A900 | #FFC233 | Mic button, primary actions (market gold) |
| `--in` | #0B7A3E | #3FC27A | Money in |
| `--out` | #C0392B | #FF6B5E | Money out / owed |
| `--late` | #B35C00 | #FFA94D | Late |
| `--hero` | #13233F | #1E2D4A | Dark summary card |

- **Typeface:** currently **Noto Sans** (Google Fonts). It covers every letter we need: Yorùbá ẹ ọ ṣ with tone marks
  (é è ẹ́ ọ̀), Hausa ɗ ƙ ɓ ƴ, Igbo ị ụ ṅ, and ₦.
  - Any new font **must pass the test line in §9**, or keep Noto Sans.
- **Logo:** `web/logo.svg` exists. Refine or replace it: voice and market or money, readable at **24 px**.
- **N-ATLaS credit (required by its licence) must appear** in: Me → About, the landing page footer, the video end
  card, and the README. The wording is in [`naic/NATLAS_FACTS.md`](naic/NATLAS_FACTS.md). Design a tidy "Powered by
  N-ATLaS" lock-up (text only unless Awarri provides a logo).

## 5. Screens to design
Phone size first (390 × 844), then check at 320 px and on a tablet or desktop (centred column). **Light + dark for
each.**

### P1: before NAIC
| # | Screen | What it must do | Notes |
|---|---|---|---|
| 1 | **Welcome / first open** | Pick a language (5 big tiles with the language's own name), then **"Use on WhatsApp"** (main) or **"Use here"** | WhatsApp-first. Desktop shows a QR code to open WhatsApp. No sign-up, no phone number asked. |
| 2 | **Consent** | One short screen in the chosen language: what we keep, what we never do, "I agree" | Warm, not legal. A "Read more" link opens the full privacy notice. |
| 3 | **Home** | Today's money in / out / net (hero card), money to collect (with a "late" count), **Tell TradeVoice** (big mic), quick actions (Scan book, Collect, Lender report), usual orders today | The existing structure is good. Make the mic dominant and the numbers readable at arm's length. |
| 4 | **Talk (chat)** | Chat with TradeVoice: trader bubbles (text and voice), TradeVoice bubbles (text, **voice-note bubble with play and waveform**, small English line under local-language replies) | Composer: text field + 📷 + big 🎤. **Hold to talk** with slide-to-cancel, or tap to start and tap to stop (both). |
| 5 | **Listening states** | Recording (big, timer, live waveform, "Listening…"), then "Hearing…", then "Understanding…", then the card | The trader must *always* know it's listening or working. Show steps, not a spinner. |
| 6 | **Confirmation card** | "I understood": amount (huge), type (Sold on credit / Paid me / Spent…), customer (with a "New customer" chip), item, quantity, pay-by date. **Save / Change / Cancel.** "Nothing is saved until you confirm." | **Unsure fields highlighted** (amber outline + "Check this"). Must fit one screen at 320 px. **Labels must never wrap mid-word** (a past bug: "Custome/r"). |
| 7 | **Re-ask** | When only one thing is unclear: "I didn't catch the **amount**. Say it again or type it", with mic and a number keypad | Highlight just that field. Quick, no blame. |
| 8 | **Saved** | Short success ("Saved ✅ Mama Tunde owes ₦45,000, pay Friday") + **Undo** for a few seconds + "Send receipt" (draft) | Celebrate lightly. |
| 9 | **Customers list** | Search, then rows: avatar initials, name, **balance first** (owes me / I owe), late badge | Sort: late first, then biggest balance. |
| 10 | **Customer page** | Big balance, due date, timeline (sold on credit, paid me, with running balance), **You gave / You got**, **Prepare reminder**, Send statement, credit limit | The existing design is good. Polish hierarchy and spacing. |
| 11 | **Reminder draft** | Message preview in the customer's language, with the **pay link** and the trader's OPay or bank number. **"Send on WhatsApp"** (opens WhatsApp with the text) and Edit | Must say clearly: "TradeVoice prepared this. **You** send it." |
| 12 | **Pay page (customer sees it)** | Shop name, "Mama Tunde, you owe **₦12,000**", **Pay now** (Paystack: card / transfer / USSD), **or** the trader's OPay or bank number with **"I have paid"**, then "Paid ✅ Thank you" | Opens from a link; **no app, no login**. Must look trustworthy (not like a scam page): clear shop name, secure-payment note, no clutter. |
| 13 | **"Just paid" moment** | The trader sees "💸 Mama Tunde just paid ₦12,000. Still owes ₦0" (in-app banner + the customer's timeline) | Mirrors the WhatsApp message (§6). |
| 14 | **Ask your book** | Ask by voice or text; answer card with the number big + **the working shown** ("₦45,000 − 10% = ₦40,500") + example questions as chips | Show when the answer comes from the book. If it can't answer: honest "I can't calculate that yet". |
| 15 | **Scan book (photo)** | Camera / pick photo, then "Reading…", then a list of lines with tick boxes, editable name and amount, ⚠️ unsure lines, **Save ticked** | |
| 16 | **Me** | Shop name, language, voice on/off, **WhatsApp connection status** ("Connected ✓ +234 ••• 4567" or a **"Connect my WhatsApp"** card), bank / OPay details for pay links, PIN, hide amounts, export, lender links, delete, **About (N-ATLaS credit)** | |
| 17 | **Connect my WhatsApp** | Step 1: your number. Step 2: tap "Open WhatsApp" (message ready to send), then "Waiting for your message…". Step 3: "Connected ✓". If both books have records: "We joined your records: 12 records, 4 customers" | Calm, 3 steps max, with progress dots. |
| 18 | **Private link landing** (`/w/…` from WhatsApp) | "Opening your book…", then the Home screen. Expired: "This link has expired. Send *web* to TradeVoice on WhatsApp for a new one" | |
| 19 | **PIN lock** | 4-digit keypad, "Forgot PIN? Get back in with WhatsApp" | Big keys. |
| 20 | **Lender report** (lender sees it) | Shop, trading history summary, statement, period, **masked phone**, "Shared by the trader until <date>" | Professional, printable, one page. |

### P2: after NAIC
- **Insights:** next 7 days, busiest day, best sellers, margins, cheapest supplier.
- **"What TradeVoice remembers":** nicknames, usual prices, corrections, each editable or deletable.
- **Consent levels:** "Help improve TradeVoice" and "Donate your voice", each its own clear opt-in.
- **Morning brief settings**, **ajo/esusu**, **apprentice mode**, **cash count**.
- **Team dashboard (`/team`):** internal; counts only, never names or amounts. Simple and functional.
- **Landing page** (`web/landing.html`) refresh to match the new brand.

## 6. WhatsApp messages (design the content, not pixels)
Most traders will only ever see TradeVoice **inside WhatsApp**. We can use: text (with *bold*, _italic_, emoji),
**voice notes**, **up to 3 reply buttons**, **lists** (up to 10 rows), and a **link button**.

**Cost:** every message costs us about ₦14 (Meta charges Nigerian businesses per message from 1 Oct 2026). **Fewer,
fuller messages.**

Please write or design each of these (in English; we translate):
1. **Welcome:** language list, then the consent message with an "I agree" button.
2. **Record understood:** the summary (amount, customer, item, date) with **Yes, save / Change / Cancel** buttons.
3. **Saved:** confirmation + new balance, with an optional voice note.
4. **Answer to a question:** the number first, then one line of explanation.
5. **Re-ask:** "I didn't catch the amount…".
6. **Daily "collect today" note:** the first message of the day.
7. **"Just paid":** "💸 Mama Tunde just paid ₦12,000 online. Still owes you: ₦0."
8. **Private link:** "📊 Open your book: <link>. Works once, for 15 minutes. Don't forward it", with an **"Open my
   book"** button.
9. **Errors:** couldn't hear, couldn't read the photo, something went wrong, each with one next step.
10. **Help / menu:** list message (record, ask, who owes me, open my book, language, voice on/off).

**Tone:** warm, short, respectful ("Ma" / "Oga" only if the trader uses it), local but not slangy, never
patronising.

## 7. States people forget (design all of them)
- **Empty:**
  - new trader with nothing recorded: "Tell me your first sale" with mic;
  - no customers;
  - no debts ("Nobody owes you 🎉").
- **Loading:** listening / hearing / understanding steps, reading a photo, sending.
- **Errors:**
  - couldn't hear (too noisy, too short);
  - no internet (**saved offline, will send later**, with a small "offline" chip);
  - microphone permission denied (how to turn it on);
  - payment failed;
  - link expired.
- **Slow AI:** after ~3 seconds, show "Still working…". If the model is starting, "⏳ One moment…".
- **Long content:**
  - long names ("Alhaji Abdulrahman Mohammed-Bello");
  - long Yorùbá or Hausa labels;
  - big numbers ("₦12,450,000");
  - 30+ customers.
- **Privacy:** "hide amounts" mode (••••), PIN locked.

## 8. Accessibility checklist
- Contrast AA at least; money and primary buttons AAA where possible. Test in dark mode too.
- Touch targets 48 px or more; mic button 64 px or more.
- Text scales to 200% without breaking (Android font size large).
- Never colour alone (icons + words for in / out / late).
- Every icon button has a label (for screen readers).
- Motion: subtle; respect "reduce motion".
- Works one-handed: main actions within thumb reach (bottom half).

## 9. Languages
- **Every screen must work in all 5:** English, Pidgin, Yorùbá, Hausa, Igbo.
- **Allow 40% longer labels** than English. Labels wrap at word boundaries, never mid-word.
- **Font test line** (must render perfectly, including stacked tone marks):
  `Ẹ kú àárọ̀ · Ọjà · Ṣé mo ní gbèsè? · Ɗan kasuwa ƙwarai · Ụgwọ ị kwụrụ · ₦45,000`
- Bottom tab labels in the trader's language (current Yorùbá: Ilé, Oníbàárà, Sọ̀rọ̀, Ìmọ̀ràn, Èmi).
- Native speakers will check the wording later. Design with real strings from `src/ui_text.py`, not lorem
  ipsum.
- **Money labels "Money in" / "Money out" stay in English in every language** (team decision).

## 10. Assets to deliver
| Asset | Sizes / format | When |
|---|---|---|
| Logo (full + mark) | SVG, plus PNG 512 and 192 | 3 Oct |
| App icon (PWA / Android) | 512, 192 (maskable safe zone) | 3 Oct |
| WhatsApp bot profile picture | 640 × 640 PNG; must read at 40 px | 3 Oct |
| Favicon | SVG + 32 px | 5 Oct |
| Icon set | SVG, one stroke style: mic, camera, money in, money out, late, customer, reminder, pay, lock, eye, export, WhatsApp-send, N-ATLaS credit | 5 Oct |
| Screens (P1 list) | Figma frames, 390 px, light + dark | 5 Oct |
| README screenshots (to replace the removed ones) | 4 × phone screenshots of the built app | 9 Oct |
| Video frames | Title card, cover / thumbnail 1280 × 720, end card (team + N-ATLaS credit) | 9 Oct |
| Hugging Face Space banner | 1200 × 600 | 9 Oct |
| Social card (link preview) | 1200 × 630 | 9 Oct |

## 11. Working in Figma (the design tool for this project)
**File set-up**
- **One Figma file: "TradeVoice: App 2026".** Share it with the team as **"can view"**, and give the developers
  **Dev Mode** access.
- **Pages in this order:**
  1. **Cover:** status, version, date, links to this plan and the roadmap.
  2. **Foundations:** colours, type, spacing, radius, shadows, icons.
  3. **Components.**
  4. **P1 screens:** numbered like §5 ("06 Confirmation card").
  5. **States:** §7.
  6. **WhatsApp messages:** mock chats for §6.
  7. **Prototype: demo path.**
  8. **Brand and assets:** logo, app icon, video frames, banners.
  9. **P2 / ideas.**
  10. **Archive.**

**Foundations as Figma Variables**
- **One "Color" collection with two modes, Light and Dark.** Variable names match the CSS tokens exactly: `ink`,
  `muted`, `bg`, `surface`, `sunk`, `line`, `accent`, `accent-ink`, `accent-soft`, `in`, `in-soft`, `out`,
  `out-soft`, `late`, `late-soft`, `hero`, `hero-ink`, `hero-muted`, `bubble-in`, `bubble-out`.
  - Developers copy values straight into `web/style.css`.
  - If you rename or add a token, add a note on the Foundations page.
- **Number variables:** spacing (4, 8, 12, 16, 24, 32), radius (`r` = 16, plus 8 and 999 for pills), touch target
  (48) and mic size (64+).
- **Text styles** (Noto Sans unless agreed otherwise): `Money XL`, `Money L`, `Title`, `Body`, `Body strong`,
  `Label`, `Caption`. Body is 16 px or more.
- **Components** with **variants** and **auto layout**, so they stretch for long Yorùbá and Hausa text:
  - **Buttons:** primary, secondary, danger, WhatsApp-send, mic (idle, recording, disabled).
  - **Chat:** bubble (trader, TradeVoice, voice note), confirmation card (normal, unsure field, saved).
  - **Money and customers:** money row (in, out, late), customer row, chips (new customer, late, offline).
  - **Navigation:** bottom tab bar, top bar.
  - **Containers:** sheet or modal, toast, empty state, keypad.

**Frames**
- **Phone frame: 390 × 844.** Duplicate the key screens at **320 px** wide to prove nothing breaks.
- **Light and dark:** switch the frame's variable mode; don't duplicate colours by hand.
- **Languages:** for the confirmation card, Home and Customer page, add **Yorùbá and Hausa versions** using real
  strings from `src/ui_text.py`.

**Prototype (for the video and judges)**
- **Click-through of the demo path:** Welcome → Talk → hold mic → listening steps → confirmation card → Save →
  Customer page → Prepare reminder → Pay page → "Just paid".
- **Mobile prototype setting:** use it, so the team can open it on a phone.

**Hand-over to developers**
- **Mark frames "Ready for dev"** in Dev Mode when final. Developers only build frames marked ready.
- **One comment thread per screen** for questions; resolve when answered.
- **Name versions** in version history at each milestone: "v1 Direction (3 Oct)", "v2 P1 final (5 Oct)", "v3 Video
  (9 Oct)".
- **Exports:**
  - icons as **SVG** (outlined strokes, 24 px grid, `currentColor`-friendly: single colour, no hard-coded fills);
  - logo and app icon as **SVG + PNG** (512, 192);
  - video frames and banners as **PNG**.

  Name files `tv-<thing>-<size>.<ext>` (for example `tv-icon-mic.svg`, `tv-appicon-512.png`) and put them in a
  shared folder. The developers add them to `web/` and `docs/images/`.
- **Fonts:** Google Fonts only, so the app can load them.
- **Small fixes on the live app:** annotate a screenshot in the Figma "Archive" page, or edit `web/style.css`
  tokens and send a pull request. Don't change `web/app.js` logic.

**Keep out of the Figma file**
- Real customer names, phone numbers, account numbers or photos of real people (without written permission).
- API keys or real links to the live server.

## 12. Rules for mockups
- **Made-up names and numbers only:** Mama Tunde, Oga Emeka, Iya Bisi, Alhaji Sani, Madam Funke, Mama Ngozi; shop
  "Chioma Stores".
- No real phone numbers, account numbers or faces without written permission.
- Don't add features. Design what's listed; send new ideas as a separate note.
- Don't use WhatsApp's or OPay's logos as ours. Use theirs only on their own buttons, as they allow.

## 13. Done when (acceptance checklist)
- [ ] Every P1 screen in light and dark, at 390 px and checked at 320 px
- [ ] All states from §7 designed for Talk, the confirmation card, the pay page and Connect WhatsApp
- [ ] Font test line renders correctly; the longest Yorùbá and Hausa labels fit
- [ ] Contrast checked (AA+) for text, money and buttons in both modes
- [ ] WhatsApp message set (§6) written
- [ ] N-ATLaS credit placed (Me → About, landing footer, video end card)
- [ ] Assets in §10 exported and named
- [ ] Figma: Variables (Light/Dark) match the CSS token names; P1 frames marked "Ready for dev"; demo-path prototype works on a phone
- [ ] Reviewed on a real low-end Android phone outdoors (sunlight test) before 9 Oct

## Questions for the team (answer before 3 Oct)
1. Keep the current navy + market-gold palette, or a new direction?
2. Keep the logo, or redesign it?
3. Who reviews the design for each language (native speakers)?
4. Which phone do we test on (model)?
