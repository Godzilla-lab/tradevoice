# 📦 Submission pack (fill in on the day, then copy into the form)

## Team
- Team name: ______ · Country: Nigeria · Location: ______
- Members: ______
- Primary prize: Kredete Financial Inclusion Award · Also applying: Thunders, Guepard, Artefact, EY Studio+, SupplyzPro

## Links
- Live prototype (Brev): ______
- 90-second video: ______
- Code: https://github.com/Godzilla-lab/tradevoice

## AI / tools disclosure
| Component | What we used | Where it runs | Why |
|---|---|---|---|
| Speech-to-text (English/Pidgin) | Whisper large-v3-turbo via faster-whisper (open source, MIT) | **NVIDIA Brev GPU** (______ GPU) | Traders' voice + financial data stay on our own server; handles Nigerian English/Pidgin; fast on GPU |
| Speech-to-text (Yoruba/Hausa/Igbo) | Meta Omnilingual ASR `omniASR_LLM_3B_v2` (Apache-2.0) | **NVIDIA Brev GPU** (same instance) | Whisper has no Igbo and is weak at Yoruba/Hausa; omniASR covers all three |
| Understanding entries + Ask-my-book | ______ (model shown in app, e.g. `nvidia/nemotron-3-super-120b-a12b`), with automatic fallback models | NVIDIA API (build.nvidia.com) | Turns Pidgin/English into structured JSON; fallback keeps working if a model is retired |
| Reading book photos | ______ (e.g. `nvidia/nemotron-nano-12b-v2-vl`, built for documents) | NVIDIA API (or Brev) | Reads handwriting into lines the trader can check |
| Offline fallback + amount check | Our own rule-based parser | Brev | Works when AI is down; catches wrong amounts |
| App / storage | Gradio, SQLite, pandas | Brev | Simple and mobile-friendly |
| Coding assistant | Claude (Anthropic) | – | Helped write starter code, tests and docs before and during the event |
| Data | Synthetic demo history (`seed_demo.py`); test phrases, voice notes and notebook photos made by our team | – | No real customer data used |
| Generated assets | ______ (e.g. none / thumbnail) | – | – |

## How we used our NVIDIA Brev credits
We ran two speech models on the GPU: Whisper large-v3-turbo (English/Pidgin, float16 on CUDA) and Meta's omniASR 3B
(Yoruba, Hausa, Igbo), together with and the TradeVoice app on a Brev
______ GPU instance for ______ hours (≈ $______ of credits). Self-hosting speech on Brev means traders' voice notes are
never sent to a third-party speech API and are deleted right after transcription. On the GPU a voice note takes
≈ ______ s vs ≈ ______ s on a laptop CPU. We stopped the instance when idle to use credits efficiently.
(Optional: we also self-hosted ______ vision model on the same GPU with vLLM.)
Screenshots: ______

## What we built before vs. on the day
- **Before (disclosed):** starter skeleton (app layout, rule parser, ledger, demo data), test phrases and recordings, research.
- **On the day:** ______ (e.g. Brev deployment and GPU tuning, prompt tuning on real voice notes, photo-reading fixes,
  evaluation runs, UI polish, video). See commit history from 27 Sep.

## Testing + reliability results
| Test | Result |
|---|---|
| Text → entry, all fields correct (15 **new** team phrases) | __ / 15 |
| Voice note → entry, amount correct | __ / __ |
| Voice note → entry, all fields correct | __ / __ |
| Notebook photo → lines, amounts correct | __ / __ lines |
| Speech-to-text latency on Brev GPU (median) | __ s |
| LLM understanding latency (median) | __ s |
| Noisy-market voice notes, amount correct | __ / 5 |
| Yoruba / Hausa / Igbo voice notes (omniASR), amount correct | __ / __ · __ / __ · __ / __ |
| Same notes through Whisper (for comparison) | __ / __ · __ / __ · __ / __ |

**Failure modes and fallbacks:** NVIDIA API down or slow → offline rules (tested) · LLM amount disagrees with the words
→ flagged and confidence lowered · unreadable handwriting → marked [?] and not saved until fixed · no amount → cannot
save · credit to a late customer → warning · every entry needs the trader's confirmation.
**Known limits:** Yoruba/Hausa/Igbo voice uses omniASR (not yet tested on many real traders; notes cut at 39 s); heavy noise lowers accuracy; the forecast is a simple
weekday average; the score is not validated against real loan outcomes.

## Responsible AI + data
- Consent checkbox before any voice note or photo is processed.
- Audio and photos deleted immediately after reading; only confirmed text entries are stored; "erase all my data" button.
- Speech and photo AI run on our own Brev GPU / NVIDIA API; no third-party speech API. On WhatsApp, messages travel over
  Meta's WhatsApp Business Platform before reaching our server; media is deleted after reading.
- WhatsApp: the trader opts in first, the bot is task-specific (bookkeeping only), and we never ask for card, bank account or ID numbers.
- The AI reads and phrases; all money maths is deterministic code, so the AI can't invent numbers in the books.
- Record score = published formula, no demographic data, labelled "indicator, not a credit decision; a person decides".
- Reminders are never auto-sent: the trader reviews and presses send.
- Bias: accents and Nigerian languages under-represented in speech models → confidence shown, editing always possible,
  local-language speech on the roadmap.
