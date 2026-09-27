# 📦 Submission pack (fill in on the day, then copy into the form)

## Team
- Team name: ______ · Country: Nigeria · Location: ______
- Members: ______
- Primary prize: Kredete Financial Inclusion Award · Also applying: Thunders, Guepard, Artefact, EY Studio+, SupplyzPro

## Links
- Live prototype (Brev): ______
- 90-second video: ______
- Code: https://github.com/Godzilla-lab/tradevoice
- Pitch deck text + demo script: [`PITCH_DECK.md`](PITCH_DECK.md)

## AI / tools disclosure
| Component | What we used | Where it runs | Why |
|---|---|---|---|
| Speech-to-text (all 5 languages) | **Intron Sahara** API | Intron (Nigerian speech-AI company) | Best we found for Nigerian English, Pidgin, Yorùbá, Hausa, Igbo and mixed sentences |
| Understanding entries + questions | **Qwen2.5-Instruct (AWQ)** served with vLLM ([7B / 14B: confirm from `LOCAL_LLM_MODEL` on Brev]) | **NVIDIA Brev GPU** | Our own model, no cloud queue; NVIDIA cloud models (Nemotron, Gemma via build.nvidia.com) as backup |
| Reading notebook photos | **Qwen2.5-VL-7B-Instruct (AWQ)**, vLLM | **NVIDIA Brev GPU** (same instance) | Reads handwritten lines for the trader to check |
| Spoken replies (text-to-speech) | **Intron Sahara TTS**; Spitch and Meta MMS-TTS (CC-BY-NC, demo only) as backups | Intron / Spitch / Brev | Native Yorùbá, Hausa, Igbo voices |
| Safety checks + offline fallback | Our own rule-based parser and guards | Brev | Amounts must have been said; works when the AI is down |
| App, storage, messaging | FastAPI, SQLite, Meta WhatsApp Cloud API, Paystack (pay links) | Brev | – |
| Coding assistant | Claude (Anthropic) | – | Helped write code, tests and docs before and during the event |
| Data | Synthetic demo history (`seed_demo.py`, made-up names); test sentences written by our team | – | No real customer data |
| Generated assets | [none / list them] | – | – |

## How we used our NVIDIA Brev credits
We ran our two AI models on a Brev [GPU type] instance for ______ hours (≈ $______ of credits), served with vLLM:
the **AI brain** (______, turns each note into a bookkeeping entry and answers "Ask my book") and the **photo reader**
(______ vision model, reads handwritten notebook pages), plus the TradeVoice app and WhatsApp webhook.
Running them on our own GPU means no queue behind other users (the free cloud API timed out on ~25% of our test notes)
and the trader's notes are understood on our server. NVIDIA's cloud models are only a backup.
Speech-to-text uses Intron's API, which beat the open speech models on Nigerian languages in independent tests.
We stopped the instance when idle to use credits efficiently.
Screenshots: ______

## What we built before vs. on the day
- **Before (disclosed):** starter skeleton (app layout, rule parser, ledger, demo data), test phrases and recordings, research.
- **On the day:** ______ (e.g. Brev deployment and GPU tuning, prompt tuning on real voice notes, photo-reading fixes,
  evaluation runs, UI polish, video). See commit history from 27 Sep.

## Testing + reliability results
Run everything with `python eval/run_all.py` (no keys needed).
| Test | Result |
|---|---|
| Automated feature checks (11 suites: demo flow, corrections, WhatsApp bot, wholesale, lender/pay links, login, Intron voice…) | **252 / 252** |
| Sentence → entry, all fields correct, offline rules alone, 5 languages (464 sentences incl. 208 trap phrases) | **464 / 464** |
| Same sentences through the AI on Brev | [__ / __] (`python eval/run_eval.py --cases eval/cases_hard.jsonl`) |
| Voice note → entry, amount correct | [__ / __] |
| Notebook photo → lines, amounts correct | [__ / __] |
| LLM understanding latency on Brev (median) | [__ s] |

**Failure modes and fallbacks:** Brev model down or slow → NVIDIA cloud models → offline rules · AI amount not in the
words → rejected and flagged · a correction ("no be 20k, na 2k") → updates the waiting record, never a second one ·
unreadable handwriting → marked and not saved until fixed · no amount → can't save · credit over a customer's limit or
to a late payer → warning first · speech voice fails → next voice engine, then text only · every entry needs the
trader's confirmation.
**Known limits:** test sentences were written by our team (optimistic); Yorùbá/Hausa/Igbo wording needs a
native-speaker check; heavy market noise lowers speech accuracy; the record score is not validated against real
loan outcomes.

## Responsible AI + data
- No sign-up: each phone gets its own private book. Consent is asked before any voice note or photo is processed (web and WhatsApp).
- Audio and photos deleted immediately after reading; only confirmed text entries are stored; "erase all my data" button.
- Voice notes go to Intron (Nigerian speech-AI company) for speech-to-text, then are deleted; understanding and
  photo reading run on our own Brev GPU (NVIDIA cloud models as backup). Spoken replies are made by Intron from text only. On WhatsApp, messages travel over
  Meta's WhatsApp Business Platform before reaching our server; media is deleted after reading.
- WhatsApp: the trader opts in first, the bot is task-specific (bookkeeping only), and we never ask for card, bank account or ID numbers.
- The AI reads and phrases; all money maths is deterministic code, so the AI can't invent numbers in the books.
- Record score = published formula, no demographic data, labelled "indicator, not a credit decision; a person decides".
- Reminders, statements and receipts are never auto-sent: the trader reviews and presses send.
- The lender link is opt-in, read-only, time-limited (1, 7 or 30 days) and can be stopped at any time.
- Bias: accents and Nigerian languages are under-represented in speech models → we use a Nigerian speech provider,
  show what was heard, and editing is always possible.
