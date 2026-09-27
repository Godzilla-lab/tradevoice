# Submission form answers (copy-paste)

Fill in every [bracket] before pasting.

## Project summary (≤150 words)
TradeVoice is voice-first bookkeeping for Nigerian market traders. A trader sends a voice note, a photo of their
notebook or a text, in English, Pidgin, Yorùbá, Hausa or Igbo, on WhatsApp or our web app. Intron Sahara transcribes
it, a Qwen model on our NVIDIA Brev GPU turns it into a transaction, and code checks that every amount was actually
said. The trader sees what was understood and taps Save; nothing is recorded without confirmation. The book then
answers questions exactly ("Who owes me the most?"), drafts reminders with pay links, tracks credit limits and
margins, and replies by voice in the trader's language. Every confirmed record builds a trading history the trader
can choose to share with a lender through a time-limited link, turning everyday trade into a path to credit.

## Problem solved
Nigerian market traders sell on credit all day, but their records live in memory, torn notebooks and WhatsApp chats.
They forget who owes them, don't know their real profit, and can't show a lender any history, so they are shut out of
credit. Bookkeeping apps expect typing, forms and English, which doesn't fit how traders work.

## Solution and key features
**(1) Core journey and features that work now**
- Speak, snap or type a transaction in 5 languages → confirmation card (customer, amount, item, quantity, credit/paid, due date; unsure fields marked) → Save / Change / Cancel (video 0:07–0:32; `eval/test_demo_flow.py`)
- Corrections in plain speech ("no be 20k, na 2k") fix the same record (`eval/test_corrections.py`)
- Ask the book in any of the 5 languages; money answers are calculated from the book (video 0:38, 1:02; `assistant.py`)
- Who owes me / who I owe, reminders with pay links that the trader sends themselves (video 0:50; `extras.py`)
- Wholesale: credit limits, customer statements, margin per item, cheapest supplier, usual-order drafts (`eval/test_wholesale.py`)
- WhatsApp bot with voice-note replies; lender link (1/7/30 days, revocable); no sign-up; PIN, hide amounts, CSV, delete; offline queue (video 1:17; `whatsapp.py`)

**(2) Mocked, simulated or unfinished**
- Demo history is synthetic (`seed_demo.py`, made-up names, marked as sample data)
- Pay links: Paystack only works with a Paystack key; otherwise bank details + "I have paid"
- The record score is a transparent formula, not validated on real loans
- Yorùbá/Hausa/Igbo wording not yet checked by native speakers; the WhatsApp bot uses Meta's test number
- [Anything else not working on the day]

**(3) Built during the hackathon vs reused**
- Before the event (24–26 Sep, 51 commits, disclosed): Gradio prototype, rule parser, ledger, speech/LLM/vision wrappers, test sentences and eval, the multilingual conversation engine, research; built with an AI coding assistant (Claude)
- On the day (27 Sep, 49 commits, see `git log`): Brev deployment of the Qwen models (`start_brev.sh`), the mobile web app and redesign, WhatsApp bot, customer ledgers, the confirmation card, guards against invented amounts, voice assistant, lender and pay links, PIN/CSV/offline queue, corrections fix from a live WhatsApp test, wholesale tools, Intron voice replies, no-login books
- Reused: open-source libraries (FastAPI, Gradio, vLLM, SQLite), Qwen models, Intron/Spitch/Meta/Paystack APIs; no templates

## Technologies used
Python, FastAPI, SQLite, vanilla JS PWA (service worker, IndexedDB), NVIDIA Brev GPU, vLLM, Qwen2.5-Instruct AWQ
[7B/14B], Qwen2.5-VL-7B-Instruct AWQ, NVIDIA API Catalog (Nemotron/Gemma backup), Intron Sahara (speech-to-text and
text-to-speech), Spitch and Meta MMS-TTS (backup voices), Meta WhatsApp Cloud API, Paystack, Cloudflare Tunnel, ffmpeg.

## Links
- Source code URL: https://github.com/Godzilla-lab/tradevoice
- Presentation URL: [link]
- 90-second demo video URL: [link, tested in a private window]
- Live demo URL: [link]
- Project cover / screenshot: [link]

## Project next step
Pilot with [number] traders in [market] for four weeks, measuring how many transactions they record and how often
they correct the AI. Get native speakers to review the Yorùbá, Hausa and Igbo wording and voices. Partner with a
microfinance bank or cooperative to test whether TradeVoice records help traders get credit. Move WhatsApp to a
verified business number.

## Partner awards to tick
Kredete, Thunders, Guepard, EY Studio+, Artefact (all countries). Optional: Palete.AI (customer experience).
Do NOT tick Yassir (Morocco only), DigiFemmes (Côte d'Ivoire only), Click Mobile (Kenya only), or SupplyzPro
(a specific challenge we didn't solve).

## Primary prize
Kredete — Financial Inclusion Award

## Award application
**Kredete — Financial Inclusion Award** → TradeVoice turns informal traders' everyday sales and debts into a
confirmed trading history they can share with lenders, the missing piece for credit. Evidence: the lender link
(read-only, 1/7/30 days, revocable), pay links on reminders, debt tracking and credit limits (`extras.py`,
`eval/test_extras.py`, video 0:50 and 1:24). We are a team based in Nigeria; the award is open to all countries (allocation TBC).

**Thunders — Engineering Excellence Award** → A working prototype with layered fallbacks (Brev model → NVIDIA cloud
→ offline rules; three voice engines) and guards so the AI can't invent amounts. Evidence: 252/252 automated checks
across 11 suites and 464/464 test sentences in 5 languages with offline rules (`eval/run_all.py`, `docs/SUBMISSION.md`).
No country restriction stated.

**Guepard — AI Automation Award** → An AI workflow from voice/photo to ledger: speech-to-text, LLM extraction,
code validation, human confirmation, then automated reminder drafts, statements and daily WhatsApp summaries.
Evidence: `converse.py`, `whatsapp.py`, `extras.py` (scheduled reminder drafts), video 0:07–0:50. No country
restriction stated.

**EY Studio+ — Human-Centred Innovation Award** → Designed for traders who may not read or type: voice in their
language, spoken replies, a confirmation card before anything is saved, no sign-up, and hide-amounts for busy stalls.
Evidence: `docs/UI_RESEARCH.md`, `web/`, and a correction flow rebuilt after a real WhatsApp test (`eval/test_corrections.py`).
No country restriction stated.

**Artefact — Data & AI Award** → Turns unstructured voice notes and notebook photos into structured data and
actionable insights: who to chase, margin per item, cheapest supplier, usual orders. Evidence: `insights.py`,
`eval/test_wholesale.py`, video 0:38. Open to all participating countries.

## AI/tool disclosure
**AI inside the product**
- Intron Sahara speech-to-text (API): hears Nigerian English, Pidgin, Yorùbá, Hausa and Igbo. Example: Pidgin voice note → "I sell Mama Tunde two bags of rice for forty-five thousand, she go pay Friday".
- Qwen2.5-Instruct AWQ [7B/14B] on our NVIDIA Brev GPU (vLLM): text → transaction. Example: that sentence → credit sale, ₦45,000, Mama Tunde, rice ×2 bags, due Friday. Our code then checks that 45,000 was actually said and marks unsure fields; the trader confirms.
- Qwen2.5-VL-7B-Instruct AWQ on Brev: notebook photo → lines the trader ticks and saves.
- Intron Sahara text-to-speech (Spitch and Meta MMS-TTS as backups): spoken replies in the trader's language.
- Fallbacks: NVIDIA API Catalog models (build.nvidia.com) if Brev is down; an offline rule-based parser if all AI fails. Money answers and totals are always computed by code, never by the AI.
- Brev: the LLM and vision model run on one Brev [GPU type] instance for [hours], so there is no shared-API queue (the free cloud API timed out on about 25% of our test notes) and the trader's words are understood on our own server.
- Nothing in the demo is simulated except the synthetic demo history.

**AI used to build it**
- Claude (Anthropic) as a coding assistant for code, tests and docs, before and during the event. The team reviewed the changes, tested on real phones and WhatsApp, and reported bugs that were then fixed (e.g. corrections being saved as new records).

**Data, APIs, assets:** synthetic demo data (`seed_demo.py`); test sentences written by the team; APIs: Intron,
Spitch, Meta WhatsApp Cloud, Paystack, NVIDIA API Catalog. Generated assets: [none / list]. No keys or personal data
are in the repository.

## Testing, results and known limitations
- Automated suites (demo flow, corrections, WhatsApp, wholesale, login, lender and pay links, voice) → 252/252 pass → `python eval/run_all.py`.
- 464 sentences in 5 languages, including 208 trap phrases → 464/464 all fields correct with offline rules alone → `eval/run_eval.py --rules-only`. The sentences were written by our team, so this is optimistic; AI and voice-note accuracy on real traders is [not yet measured / result].
- Edge case found in a live WhatsApp test: "2000 no be 20000" was saved as a new ₦20,000 record → fixed so corrections update the waiting record (`eval/test_corrections.py`). Known limits: heavy market noise, native-speaker review pending.

## Responsible AI and data
All demo data is synthetic with made-up names; test sentences were written by our team, and no real customer data
is used. Traders consent before any voice note or photo is processed; audio and photos are deleted after reading;
nothing enters the book without the trader's confirmation; reminders are never sent automatically; and the lender
link is opt-in, read-only, time-limited and revocable. The AI can't invent amounts because code checks every number
against what was said and does all the maths. Unresolved risks: speech models are weaker on some accents and noisy
markets, voice notes pass through Intron and Meta, and the record score is not validated on real loan outcomes.
