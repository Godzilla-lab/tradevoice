# 📲 TradeVoice on WhatsApp: research + build plan

**Decision:** one engine, two front doors.
- **WhatsApp**: how traders actually use it. Send a voice note, a photo of the notebook, or a text; get the record back.
- **Web app**: dashboard + demo + backup if WhatsApp fails live. Same data.

We use **Meta's official WhatsApp Cloud API** directly (no Twilio account). Researched 24 Sep 2026. Meta's docs were
blocked for our research tool, so facts come from search summaries of Meta docs and vendor guides. **⚠️ UNVERIFIED**
items must be checked during setup.

---

## 1. How it fits together
```
Trader's WhatsApp ──► Meta Cloud API ──► webhook (our server on Brev, via tunnel)
                                              │  reply 200 at once, work in background
                                              ▼
            voice → Whisper / omniASR (Brev GPU)   photo → vision model   text → as is
                                              ▼
                        extract.py → entry → "✅ Save / ✏️ Fix" buttons
                                              ▼
                             ledger.py (same SQLite as the web app)
                                              ▼
                  Web app dashboard shows the same records (per trader phone number)
```
Everything below the webhook **already exists** (asr.py, vision.py, extract.py, ledger.py, insights.py). The new part is
the **WhatsApp adapter** (`whatsapp.py`), about 200 lines. **We build it on the day**: that's our main "built today"
work, which also answers the "you built it before the event" risk.

## 2. Setup checklist: do this BEFORE Sunday (≈ 1.5–2 h, one person)
| # | Step | Time |
|---|---|---|
| 1 | Log in at **developers.facebook.com** with a Facebook account; register as developer | 10 min |
| 2 | **Create App** → use case *"Connect with customers through WhatsApp"* → create/select a Business portfolio. Meta gives a **free test phone number** (no business verification needed for it) | 10 min |
| 3 | WhatsApp → **API Setup** → "To" → *Manage phone number list* → add up to **5 recipient numbers** (each gets a WhatsApp code). **This is a hard allowlist: pick the 5 demo phones (team + one spare for a judge).** +234 numbers are fine | 10 min |
| 4 | Copy **Phone Number ID**, **WhatsApp Business Account ID**, **App Secret** (App settings → Basic). Send the default `hello_world` test message to your phone | 15 min |
| 5 | **Permanent token:** Business Settings → System Users → add Admin system user → assign the app + WABA (full control) → generate token, expiry **Never**, scopes `whatsapp_business_messaging`, `whatsapp_business_management`. Shown once: save it in a password manager. (Business verification reportedly only "recommended" here, ⚠️ UNVERIFIED) | 20 min |
| 6 | On a laptop (Saturday) or Brev (Sunday): run the webhook + a tunnel → WhatsApp → **Configuration** → Callback URL + Verify token → **Verify and save** → **Subscribe to `messages`** | 20 min |
| 7 | From each allowlisted phone send a text, a voice note and a photo; confirm they arrive | 15 min |

**If step 5 fails:** the temporary token on the API Setup page **expires in ~24 h**. Generate a fresh one on Sunday
morning and put it in `.env`; never hard-code it.

**Backup if Meta setup fails completely:** 360dialog sandbox. Send "START" on WhatsApp to **+55 11 4673-3492** to get
an API key instantly (messages only your own number; payloads similar to Cloud API). https://docs.360dialog.com/docs/waba-messaging/sandbox

## 3. The API: what the adapter needs
Graph API version: **v26.0** (current; v25.0 also works). Base: `https://graph.facebook.com/v26.0`

**Webhook verify (GET):** if `hub.mode == "subscribe"` and `hub.verify_token == WHATSAPP_VERIFY_TOKEN` → return
`hub.challenge` as **plain text**, status 200 (not JSON).

**Webhook messages (POST):**
- Check header `X-Hub-Signature-256: sha256=<hex>` = HMAC-SHA256 of the **raw body** with the App Secret (`hmac.compare_digest`).
- **Return 200 immediately**; do speech/photo work in a background task (Meta times out after ~5–10 s and retries
  for days). **Dedupe on the message `id`**: duplicates happen.
- Message: `entry[0].changes[0].value.messages[0]` → `from` (e.g. `234803…`), `id`, `type`. Ignore `value.statuses`.
  - text → `msg["text"]["body"]`
  - voice note → `msg["audio"]` = `{id, mime_type: "audio/ogg; codecs=opus", voice: true}`
  - photo → `msg["image"]` = `{id, mime_type: "image/jpeg", caption?}`
  - button tap → `type: "interactive"`, `msg["interactive"]["button_reply"]["id"]`

**Download media:** `GET /v26.0/{media-id}` (Bearer token) → `{url}` → `GET url` **with the same Bearer header** → bytes.
The URL expires in ~5 min. Our `asr.to_wav16k()` already converts ogg/opus with ffmpeg.

**Send text:** `POST /v26.0/{PHONE_NUMBER_ID}/messages`
```json
{"messaging_product":"whatsapp","to":"234XXXXXXXXXX","type":"text","text":{"body":"..."}}
```
**Send Save/Fix buttons** (max 3 buttons, title ≤ 20 chars, body ≤ 1024 chars):
```json
{"messaging_product":"whatsapp","to":"234…","type":"interactive",
 "interactive":{"type":"button","body":{"text":"📒 Credit sale · ₦45,000 · Mama Tunde · due Fri"},
  "action":{"buttons":[{"type":"reply","reply":{"id":"save:ab12","title":"✅ Save"}},
                       {"type":"reply","reply":{"id":"fix:ab12","title":"✏️ Fix"}}]}}}
```
A **list message** (up to 10 rows) suits "pick a debtor". Documents (the lender statement) can be sent with
`"type":"document"` and a `link` or an uploaded media `id`.

## 4. The conversation design
```
Trader → 🎤 voice note (or 📸 photo, or text)
Bot    → Heard: "I sell 3 bag rice give Mama Tunde 45k, she go pay Friday"
         📒 Credit sale · ₦45,000 · Mama Tunde · due Fri 26 Sep
         ⚠️ Mama Tunde already owes ₦21,600
         [✅ Save] [✏️ Fix]
Trader → ✅ Save      → "Saved. Mama Tunde now owes ₦66,600."
Trader → ✏️ Fix       → "Send the correct version as text or a new voice note."
Trader → 📸 notebook   → "Found 5 entries: … " [✅ Save all] [✏️ Fix]
Trader → "who owe me"  → list, late ones 🔴
Trader → "remind Oga Emeka" → polite Pidgin reminder to forward (trader sends it, not us)
Trader → "today" / "how market today?" → today's sales and expenses
Trader → "language yoruba" → voice notes go to omniASR in Yoruba
Trader → "statement"   → lender statement as a document
Trader → "delete my data" → confirm, then erase
First message ever → short welcome + consent: "Reply YES to let TradeVoice keep your records"
```
Keep it **task-specific** (see policy): anything off-topic → "I only help with your shop records."

## 4b. What goes where (WhatsApp vs web dashboard)
One shared record book: anything saved on WhatsApp shows on the dashboard instantly, and the other way round.
WhatsApp = **quick capture + quick answers**. Web = **anything with tables, charts or editing**.

| Task | WhatsApp | Web dashboard |
|---|---|---|
| Record a sale by voice note | ✅ **main way** | ✅ |
| Snap notebook page / receipt | ✅ **main way** | ✅ |
| Confirm or fix an entry | ✅ buttons | ✅ full edit form |
| "Who owe me?" / "How market today?" | ✅ short answer | ✅ full table |
| Credit warning before giving credit | ✅ | ✅ |
| Debt reminder message | ✅ bot writes it, **trader forwards it** | ✅ |
| Charts, forecast, best sellers | ❌ one-line summary only | ✅ **main place** |
| Edit/delete old entries, full history | ❌ | ✅ **main place** |
| Lender statement | ✅ sent as a document | ✅ download |
| Delete all my data | ✅ with confirmation | ✅ |

**The bridge: a dashboard link.** Trader types **"dashboard"** → bot replies with a private link to *their* dashboard
(e.g. `https://…/?t=<random token>`, token stored against their number, expires after 24 h). No passwords, no sign-up:
the WhatsApp number is the account. Good moment for the demo video.

**Short answer + "👉 See more" link.** Replies that have more behind them end with a deep link to that exact dashboard
page, so WhatsApp gives the quick answer and the web gives the full power:

| WhatsApp reply | Link opens |
|---|---|
| "5 people owe you ₦247,050 · 🔴 Oga Emeka ₦30,600, 18 days late" | `?t=…&tab=debtors`: full list, reminders, credit check |
| "Today: sales ₦82,300 · expenses ₦9,500" | `?t=…&tab=today`: all entries, edit/delete |
| "Next 7 days ≈ ₦620k · Saturday busiest" | `?t=…&tab=insights`: forecast table, best sellers |
| "Found 5 entries in your photo" | `?t=…&tab=photo`: editable table for tricky pages |
| "Record score 82/100" | `?t=…&tab=profile`: score breakdown + statement |

Rules:
- **Answer first, link second.** Many traders have small data plans or weak network, so the reply must be useful without opening the link.
- **Only link when there's more to see.** A plain "✅ Saved" gets no link, or it starts to feel like spam.
- **Links are private and expire:** random token tied to the trader's number, valid 24 h; opening it shows only their book.

**Reminders go through the trader, not straight to the debtor.** WhatsApp only lets the bot message people who wrote to
it in the last 24 h (otherwise Meta-approved templates are needed). So the bot writes the polite reminder and the trader
forwards it. That keeps the trader in control (Responsible AI). Automatic reminders = "next step" in the pitch.

**Don't copy the whole web app into chat.** Keep replies short; send the dashboard link when they need more.

## 5. Code changes needed (on the day)
1. **`ledger.py`**: add an `owner` column (the trader's WhatsApp number) so each trader has their own book. The web
   app opens the owner from the dashboard link token (`?t=…`), falling back to `SHOP_PHONE` in `.env` for the demo,
   so web and WhatsApp display the same records.
2. **`whatsapp.py`** (new, FastAPI):
   - `GET /webhook` verify
   - `POST /webhook` signature check → dedupe → background task
   - media download
   - route by type
   - send text/buttons
   - pending entries in a table keyed by button id
   - consent + per-trader language setting
   - "dashboard" command and "👉 See more" links → link token (new `links` table: token, owner, expires_at);
     `app.py` reads `?t=` and `?tab=` to open the right trader and tab
3. **Run both** on Brev: `uvicorn whatsapp:app --port 8000` + `python app.py` (Gradio). Tunnel only port 8000 for Meta.
4. **Tests:** fake webhook payloads (text/voice/photo/button) against the handler, plus the real 5-phone test.

New `.env` values: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`
(any random string you choose), `SHOP_PHONE`.

## 6. Tunnel: how Meta reaches our server
The webhook needs a public **HTTPS** URL. Brev's own links sit behind a login, so we use a tunnel on the Brev box:
- `cloudflared tunnel --url http://localhost:8000` gives a free `trycloudflare.com` URL. **It changes on every restart**,
  so re-enter it in Meta's dashboard and keep the process alive.
- Backup: **ngrok free static domain** (stays the same). Some reports say Meta occasionally rejects tunnel domains as
  "malicious"; restarting or switching tunnel fixed it. **Test the tunnel on Saturday.**

## 7. Rules, policy, money
- **24-hour window:** we can reply freely only within 24 h of the trader's last message. Outside it we'd need a
  pre-approved template, so automatic debt reminders pushed by us are a *future* feature. For the demo the trader
  messages first (fine).
- **Pricing:** replies to traders are free today. ⚠️ **From 1 Oct 2026 Meta charges ~$0.0101 (≈ ₦14) per service
  message to Nigerian numbers.** Hackathon day (27 Sep) is before that. Say it honestly in the pitch as a running
  cost (a business model question judges may ask).
- **Opt-in:** the trader must agree first (our consent message). Never ask for card numbers, bank account numbers or ID
  numbers.
- **General-purpose AI chatbots are banned on WhatsApp since 15 Jan 2026.** Task-specific bots are allowed, so
  TradeVoice must stay a bookkeeping assistant, not a "chat about anything" bot.
- **Never use unofficial libraries** (whatsapp-web.js, Baileys). They break WhatsApp's terms and the number can be banned.
- **Privacy claim changes:** voice notes and photos now pass through Meta's servers before reaching ours. Update the
  Responsible AI text: *"Messages travel over WhatsApp (Meta); speech and photo AI run on our own Brev GPU; media is
  deleted after reading."*

## 8. Risks and fallbacks
| Risk | Fallback |
|---|---|
| Meta setup/verification blocks us | 360dialog sandbox (10 min), or demo the web app only |
| Tunnel rejected or URL changes | Switch cloudflared ↔ ngrok; re-enter URL; test Saturday |
| Temporary token expires | System-user token; else fresh temp token Sunday morning |
| Judge's phone not allowlisted | Pre-add a spare demo phone; show on our phone |
| WhatsApp slow/flaky during live demo | Pre-recorded screen video of the WhatsApp flow + live web app |

## Sources
- Meta get started: https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started
- Audio messages: https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/audio-messages
- Media: https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media
- Reply buttons: https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/interactive-reply-buttons-messages
- Pricing: https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing
- Nigeria charges from Oct 2026: https://www.vanguardngr.com/2026/08/meta-set-to-charge-whatsapp-business-messages-from-october/
- Chatbot policy: https://techcrunch.com/2025/10/18/whatssapp-changes-its-terms-to-bar-general-purpose-chatbots-from-its-platform
- Permanent token guide: https://developers.facebook.com/blog/post/2022/12/05/auth-tokens/
- Webhook security: https://hookdeck.com/webhooks/platforms/guide-to-whatsapp-webhooks-features-and-best-practices
- Python examples: https://github.com/daveebbelaar/python-whatsapp-bot · https://github.com/leandcesar/wa_me
- 360dialog sandbox: https://docs.360dialog.com/docs/waba-messaging/sandbox
