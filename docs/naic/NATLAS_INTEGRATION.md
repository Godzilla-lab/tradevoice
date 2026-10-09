# TradeVoice: how it uses N-ATLaS

NAIC 2026, Innovation and Enterprise track, PS2 Voice-First Access.
Live build: https://tradevoice.duckdns.org (the web app is at `/app`). Code: this repository.

N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, and powered by Awarri Technologies.

## 1. In one paragraph

TradeVoice keeps the books for Nigerian market traders who would rather talk than type. A trader says "Iya Bisi
took 2 bags of rice for 60,000, she will pay Friday" in English, Pidgin, Yorùbá, Hausa or Igbo. TradeVoice turns that into a
record (who, what, how much, when they will pay), shows it on a check card, and saves it when the trader says yes.

N-ATLaS does the understanding and most of the hearing:
- **The N-ATLaS language model** reads what the trader said and writes the record.
- **The four N-ATLaS speech models** turn voice notes into words.
- **N-ATLaS merges two hearings** when a trader mixes languages.

Code, never the AI, does the arithmetic and checks every record before it is saved.

## 2. Which N-ATLaS models, and where they run

| Model | What TradeVoice uses it for | Where it runs |
|---|---|---|
| `NCAIR1/N-ATLaS` (Llama-3 8B base) | Writing records from what the trader said; merging two hearings; answering in Yorùbá, Hausa and Igbo first | Modal, one L4 GPU, vLLM, OpenAI-compatible API (`deploy/modal_natlas.py`) |
| `NCAIR1/Yoruba-ASR` | Hearing Yorùbá voice notes | Modal, CPU (`deploy/modal_asr.py`) |
| `NCAIR1/Hausa-ASR` | Hearing Hausa voice notes | same |
| `NCAIR1/Igbo-ASR` | Hearing Igbo voice notes | same |
| `NCAIR1/NigerianAccentedEnglish` | Hearing English and Pidgin voice notes, and the second hearing for mixed-language notes | same |

- **The official weights are served**, not a quantised copy.
- **Model card settings:** temperature 0.1, repetition penalty 1.12, context up to 8,192 tokens, and the Llama-3.1 chat template with today's date.
- **Market hours:** both Modal apps sleep when idle. The web server keeps them awake from 7am to 8pm Lagos time during the pilot and the integration check (`src/natlas_watch.py`, `NATLAS_WATCH=1`), and tells the team if N-ATLaS stops answering.
- **If Modal stops answering** (asleep, broken, or out of credits), the app marks it down after one short wait and
  checks it in the background until it answers again. Meanwhile NVIDIA models answer and Intron hears voice notes, so
  traders are still served; N-ATLaS's share of answers is what drops.

## 3. Architecture

```
 Trader (phone browser, or the Telegram bot)
   | voice note, live talk, typed words, photo of a notebook page
   v
 TradeVoice web server (FastAPI on AWS, tradevoice.duckdns.org)
   |
   |-- voice note --> N-ATLaS speech model for the trader's language (Modal)
   |                  + NigerianAccentedEnglish on the same note
   |                  -> the N-ATLaS language model merges the two hearings
   |                  (Intron hears only while the speech server is down)
   |
   |-- words -------> N-ATLaS language model writes the record as JSON
   |                  (Modal, vLLM guided decoding). Backups only if N-ATLaS
   |                  is asleep or late: NVIDIA API models, then offline rules
   |
   |-- code checks -> amounts, names, dates; "each" prices multiplied by code
   v
 Check card on the trader's screen -> "Yes" -> the trader's own book
 (one SQLite file per phone number)
```

**Live talk** (hold the mic and talk back and forth):
- Intron's streaming speech service hears and speaks, so the conversation is quick.
- N-ATLaS still writes the records and answers.

**Typed chat questions:**
- Yorùbá, Hausa and Igbo go to N-ATLaS first.
- English and Pidgin go to a larger NVIDIA model first, with N-ATLaS as the backup.

**Photos of notebook pages** are read by NVIDIA vision models, since N-ATLaS has no vision model.

## 4. Where N-ATLaS is called in the code

| Step | File and function | What happens |
|---|---|---|
| Choosing the model | `src/llm.py` `chat()` | N-ATLaS is put first for every record (`models.insert(0, "natlas")`); the backups only answer if it fails or runs out of time |
| Calling N-ATLaS | `src/llm.py` `_client()`, `_served_name()` | OpenAI-compatible call to the Modal URL (`NATLAS_URL`) with the team's key (`NATLAS_KEY`) |
| Writing a record | `src/extract.py` `llm_extract()` | The trader's words, today's date and their customer names go to N-ATLaS; it must answer in the JSON shape `REC_SCHEMA` (guided decoding), with worked examples (`SHOTS`) given to N-ATLaS only |
| Checking the record | `src/extract.py` (guards), `src/converse.py` | Code checks amounts, multiplies "each" prices, keeps names spelled as in the book, and asks when something is unclear |
| Hearing a voice note | `src/asr.py` `_natlas_transcribe()` | The note goes to the N-ATLaS speech model for the trader's language, with their customer names as hints |
| Merging two hearings | `src/hearing.py` `merge()` | For Yorùbá, Hausa and Igbo, N-ATLaS merges the language model's hearing with the English model's hearing; an amount is kept only if it was actually heard |
| Questions in local languages | `src/agent.py` `models()` | Yorùbá, Hausa and Igbo questions go to N-ATLaS first |
| Lists of many lines | `src/extract.py` (list reading) | A pasted or spoken list: N-ATLaS writes every line, the trader checks them |
| Keeping it awake | `src/natlas_watch.py` | Pings both Modal apps every 10 minutes in market hours; alerts the team if they stop answering |
| Counting its share | `src/llm.py` `_event()`, `src/events.py` `is_natlas()` | Every answer is logged with the model that gave it (no words), for the dashboard and the validation report |

## 5. What N-ATLaS adds: the benchmark

We compared N-ATLaS with the model it was built from, Meta-Llama-3-8B-Instruct.
- **Setup:** same size, same GPU (Modal L4, vLLM), same prompt, same 6 worked examples, one model at a time, no backups.
- **Score:** a sentence counts as right only if the record's type, amount and customer are all right.

**1,000 bookkeeping sentences, 200 per language** (2 Oct 2026, `eval/cases_1000.jsonl`; 95% range in brackets):

| | N-ATLaS alone | Llama-3-8B alone | Full TradeVoice (N-ATLaS + code checks) |
|---|---|---|---|
| All | **69%** (66 to 71) | 51% (47 to 54) | **100%** |
| English | 85% | 59% | 100% |
| Pidgin | 62% | 57% | 100% |
| Yorùbá | 69% | 60% | 100% |
| Hausa | **67%** | 27% | 100% |
| Igbo | 62% | 52% | 100% |
| Amounts said in Nigerian number words | **62%** | 12% | 100% |
| Wrong amount written | 68 | 170 | **0** |
| Median time (warm GPU) | 5.0 s | 5.3 s | 5.1 s |

**What we take from it:**
1. **N-ATLaS is 18 points better than its base model.** The biggest gaps are Hausa (67% against 27%) and amounts said in Yorùbá, Hausa or Igbo number words (62% against 12%).
2. **Neither model alone is safe for money.** N-ATLaS wrote a wrong amount 68 times in 972. TradeVoice is safe because code does the maths and checks every record: 0 wrong amounts in the same 972.
3. **N-ATLaS mistakes we found and now guard against** (tests in `eval/test_guards.py`):
   - copying an example's price;
   - taking the balance instead of the part paid;
   - re-spelling customer names ("Mallam Sani" to "Mr. Sani"), which would split one customer in two.
4. **Limits of this test:**
   - The sentences were written by the team, not by native speakers.
   - Our rules were built on similar sentences.
   - On 100 sentences written later from research (never used to tune anything), the full app scored 69% before fixes.

   That is why the pilot's real use matters more than these numbers (section 7).

The full log of runs, with commands, is in `docs/RESULTS.md`.

## 6. The four known limits of N-ATLaS speech, and what we did

| Limit (from N-ATLaS) | What TradeVoice does | Status |
|---|---|---|
| Noisy places | Light audio preparation only (16 kHz mono, level, trim quiet ends; no heavy denoising, which makes Whisper models worse); asks again for just the unclear part; nothing is saved without the check card | Built. Before and after on real market notes: script ready (`deploy/server/speech_ab.sh`), not yet run on consented notes |
| Mixing languages | Two N-ATLaS speech models on the same note (the trader's language and Nigerian-accented English), merged by the N-ATLaS language model; an amount is kept only if it was heard | Built and tested in code (`eval/test_hearing.py`); real-note numbers not yet measured |
| Accents and dialects | The trader's own customer names and items are passed to the speech model as hints; corrections are remembered (nicknames, usual prices) | Partly: helps names and items in the trader's book; full accent work needs fine-tuning on donated voices (after NAIC, with consent) |
| Children's speech | Not addressed | Out of scope: TradeVoice is for adult traders |

We only claim what the numbers show. Where a number is not yet measured, this table says so.

## 7. N-ATLaS in real use (the pilot)

How often N-ATLaS answered during the pilot comes from the live app's own log:
- the share of AI answers given by N-ATLaS;
- how often a backup answered instead;
- the time each step took;
- which speech model heard each voice note.

The numbers are in the validation report (`scripts/validation_report.py`, run on the server; see
`docs/naic/VALIDATION.md` for how) and on the team dashboard (`/team`).

[Paste here, from the validation report: N-ATLaS share of AI answers, number of AI answers, voice notes heard by
N-ATLaS speech, typical step times.]

## 8. Licence and use

- TradeVoice uses N-ATLaS under its licence.
- **Attribution:** the sentence at the top of this document appears on the website, in the app (Me > About), in the privacy notice, on the team dashboard, in the README and in every NAIC document.
- **User cap:** the licence's limit of 1,000 active users in 30 days is watched on the team dashboard.
- **Commercial use:** before any commercial use, the team will contact Awarri as the licence asks.

N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, and powered by Awarri Technologies.
