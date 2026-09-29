# TradeVoice design brief (hackathon day, Sun 27 Sep, final designs by ~14:30)

Live app: the link from the team (a trycloudflare.com link; it changes if it is restarted).
Code for the look: `web/style.css` (all colours at the top), `web/index.html`, `web/app.js`.

## Who it's for
A Nigerian market trader (think "Mama Chioma", 45, sells rice and garri at Balogun market).
- Uses **WhatsApp every day**, so the app deliberately looks and works like WhatsApp. Keep that familiarity.
- May **not read well** (or at all), so **voice first**: speaking and listening are the main actions; icons and
  numbers must carry meaning without text.
- Cheap Android phone, bright sunlight, noisy market, one hand busy. Big touch targets, strong contrast.
- Languages: English, Pidgin, Yoruba, Hausa, Igbo. Yoruba needs tone marks (ẹ́ ọ̀ ṣ); Hausa needs ɗ ƙ ɓ;
  Igbo needs ị ụ ṅ. Check the font shows them all; Yoruba/Hausa words are often longer than English.

## Priority 1: brand (needed for the video + submission)
- [ ] **Logo / app icon** for "TradeVoice": voice + money/market. It currently uses the 🗣️ emoji in a green circle.
      Deliver: SVG + 512×512 PNG + 192×192 PNG (icon), and a version that works small (40 px chat avatar).
- [ ] **Colours**: currently WhatsApp-like greens (`--head #008069`, `--accent #00a884`). Keep it familiar but
      give it a TradeVoice touch (e.g. a warm market accent for money/highlights). Light AND dark mode.
- [ ] **Video cover / thumbnail** (1280×720) and a **title card** for the 90-second video.
- [ ] One **team photo slot** / closing slide for the end of the video.

## Priority 2: the key screens (the demo path)
Check these on a phone (~390 px wide), light and dark:
1. **Welcome**: pick language + "Agree and continue" (consent). Should feel warm and trustworthy, not like a bank.
2. **Chat (home)**, the star of the demo:
   - bot bubble (text + small English line + **voice-note bubble** ▶ with waveform)
   - **hold 🎤 to talk** (recording bar, slide to cancel), **📎 snap your book**
   - **✅ Yes, save / ❌ No** quick replies after a record
   - reminder card with the message + **Send on WhatsApp** button
   - photo result: list of lines with tick boxes, editable amount and name, ⚠️ warnings, "Save ticked"
3. **Debts**: who owes me (late = red badge, **Remind** button) / who I owe.
4. **Book**: today's Sold / Spent / Came in + recent records.
5. **Insights**: next 7 days bar chart, busiest day, best sellers.
6. **Profile**: record score ring (0–100), why this score, **statement for lender** button.

## Priority 3: states people forget
- [ ] Empty states (new trader, nothing recorded yet): friendly, tells them to talk to the chat.
- [ ] Loading ("typing…" dots, reading photo), errors (couldn't hear, no internet), mic permission denied.
- [ ] Recording state: big, obvious, with a timer. People must know it's listening.
- [ ] Money: always "₦45,000" style; big and bold. Late debts: red and a word ("2 days late"), not colour alone.

## Rules
- Voice and icons first; any text short and simple (a 10-year-old should understand it).
- Minimum touch target 44 px; body text 16 px or more; contrast AA or better (sunlight!).
- Don't add features; polish what's there. The demo path above is what judges see.
- Fake names only in any mockup (Mama Tunde, Oga Emeka, Iya Bisi, Alhaji Sani, Madam Funke).
- Don't use the WhatsApp logo or name as our brand (only on the "Send on WhatsApp" button).

## How to hand over (pick one)
1. **Send specs**: colours (hex), font name (Google Fonts only), logo files, and screenshots with notes →
   the AI lead puts them in the code.
2. **Edit `web/style.css` directly** if you know CSS (colours are variables at the top: `--head`, `--accent`,
   `--out`, `--in`, `--bg`…), then send the file or a GitHub pull request.
3. Figma: fine for the logo and video frames; for the app, notes on screenshots are faster today.

Deadline: brand files and colours by **~13:30** (so they are in the app before recording), video frames by **~14:30**.
