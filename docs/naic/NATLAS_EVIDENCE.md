# TradeVoice: evidence of the N-ATLaS integration

NAIC 2026, Innovation and Enterprise track, PS2 Voice-First Access. Live app: https://tradevoice.duckdns.org/app.
Code: this repository, branch `claude/tradevoice-handoff-b7942v` (submission commit `c50a209`).

N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, and powered by Awarri Technologies.

This document holds the evidence the form asks for:
- **Section 2:** API call samples, the exact requests the app sends to N-ATLaS.
- **Section 3:** the benchmark scripts and their results.
- **Section 4:** the automated test log.
- **Section 5:** how evaluators can reproduce a live run on the server.

The design and code map are in `TradeVoice-NATLAS-integration.pdf`.

## 1. What runs, and where

| N-ATLaS model | What TradeVoice uses it for | Where it runs |
|---|---|---|
| `NCAIR1/N-ATLaS` (Llama-3 8B, official weights, BF16) | Turning the trader's words into a record (JSON); merging two hearings of one voice note; answering Yorùbá, Hausa and Igbo questions first | Modal, 1 x NVIDIA L4, vLLM, OpenAI-compatible API (served as `natlas`) |
| `NCAIR1/Yoruba-ASR` | Hearing Yorùbá voice notes | Modal (`deploy/modal_asr.py`) |
| `NCAIR1/Hausa-ASR` | Hearing Hausa voice notes | Modal |
| `NCAIR1/Igbo-ASR` | Hearing Igbo voice notes | Modal |
| `NCAIR1/NigerianAccentedEnglish` | Hearing English and Pidgin; the second hearing of every Yorùbá, Hausa and Igbo note | Modal |

**Where the app calls them:**
- the language model: `src/llm.py` `chat()`, from `src/extract.py`, `src/hearing.py` and `src/agent.py`;
- the speech models: `src/asr.py` `_natlas_transcribe()`.

- **N-ATLaS is first for every record** (`models.insert(0, "natlas")` in `src/llm.py`). Backups answer only if it is
  down or out of time: NVIDIA models for words, Intron for voice.
- **Live talk:** Intron's streaming speech hears, for speed; N-ATLaS still writes every record.
- **Every answer is logged** with the model that gave it (no words, names, numbers or amounts), so the share N-ATLaS
  answered is measured, not estimated (`src/events.py`, `/team`, `scripts/validation_report.py`).
- **Monitoring:**
  - `src/natlas_watch.py` keeps both Modal apps awake in market hours and alerts the team when they stop answering.
  - `/team` counts N-ATLaS active users against the licence's 1,000 a month and warns at 800.

## 2. API call samples (the exact requests, captured from the app's own code)

The samples below were produced by running the app's own functions (`extract._rec_call` + `llm.chat`,
`asr._natlas_transcribe`) with the server address pointed at a recording stub. They are the request bodies the live
server sends to our Modal apps. The key is sent as `Authorization: Bearer ...` and is never shown. Section 5 shows
live answers.

### 2a. A record from the trader's words: `POST {NATLAS_URL}/chat/completions`

```json
{
  "model": "natlas",
  "temperature": 0.1,
  "repetition_penalty": 1.12,
  "max_tokens": 250,
  "chat_template_kwargs": {"date_string": "10 Oct 2026"},
  "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": {
      "type": "object", "required": ["type", "amount", "customer"],
      "properties": {"type": {"enum": ["sale", "credit_sale", "payment_received", "expense",
                                       "credit_purchase", "payment_made"]},
                     "item": "...", "quantity": "...", "unit": "...", "amount": "...", "each": "...",
                     "customer": "...", "due_date": "...", "confidence": "...", "note": "..."}}}},
  "messages": [
    {"role": "system", "content": "You turn a Nigerian market trader's voice note (English, Nigerian Pidgin, or mixed) into ONE bookkeeping record.\nToday is 2026-10-10 (Saturday).\nReturn ONLY a JSON object with these keys: ... (3,260 characters, src/extract.py SYSTEM_PROMPT) ...\nNever invent an amount or a name that was not said.\nPeople already in this trader's book: Iya Bisi, Mama Ngozi. If the note names one of them (even misheard or misspelt), use that exact spelling."},
    {"role": "user", "content": "Mrs Adaeze took 3 rolls of lace, 4,500 each, she will pay later"},
    {"role": "assistant", "content": "{\"type\": \"credit_sale\", \"item\": \"lace\", \"quantity\": 3, \"unit\": \"roll\", \"amount\": 4500, \"each\": true, \"customer\": \"Mrs Adaeze\", \"due_date\": null, \"confidence\": 0.9, \"note\": null}"},
    "... 5 more worked examples (user, assistant): 2 in Pidgin, 1 each in Yorùbá, Hausa and Igbo (src/extract.py SHOTS) ...",
    {"role": "user", "content": "Iya Bisi took 2 bags of rice for 60000, she will pay Friday"}
  ]
}
```

What the code does with the answer (`src/extract.py`, tests in `eval/test_guards.py`):
- reads the JSON;
- keeps the amount only if it was said;
- multiplies "each" prices itself;
- keeps names spelled as in the trader's book;
- fills gaps from the offline rules;
- shows the trader a check card.

Nothing is saved before the trader says yes.

### 2b. Hearing a voice note: `POST {NATLAS_ASR_URL}/transcribe` (multipart form)

```
file  = note.wav        (16 kHz mono after light preparation)
lang  = yoruba          (yoruba | hausa | igbo | english: picks NCAIR1/Yoruba-ASR, Hausa-ASR, Igbo-ASR, NigerianAccentedEnglish)
also  = english         (Yorùbá, Hausa and Igbo notes are heard a second time by NigerianAccentedEnglish)
prompt= Iya Bisi, rice  (the trader's own customer names and items, as hints)
prep  = 1
```

### 2c. Merging the two hearings: `POST {NATLAS_URL}/chat/completions`

```json
{"model": "natlas", "temperature": 0.1, "repetition_penalty": 1.12, "max_tokens": 120,
 "chat_template_kwargs": {"date_string": "10 Oct 2026"},
 "messages": [{"role": "user", "content": "Two speech models heard the same short voice note from a Nigerian market trader who may mix\nYoruba and English.\nA (Yoruba model): <words from NCAIR1/Yoruba-ASR>\nB (English model): <words from NCAIR1/NigerianAccentedEnglish>\nCustomer names and items in the trader's book: Iya Bisi, rice\nWrite the ONE sentence the trader most likely said, in the words they used (keep Yoruba words in Yoruba and\nEnglish words in English). Use a name from the book only when A or B clearly sounds like it. Never add a number,\nan amount or a name that is not in A or B. Reply with the sentence only."}]}
```

An amount is kept only if one of the two hearings actually contains it (`src/hearing.py`).

## 3. Benchmark: what N-ATLaS adds (scripts and results)

**Setup:**
- **Models:** N-ATLaS and its base model, Meta-Llama-3-8B-Instruct.
- **Same conditions:** the same GPU (Modal L4, vLLM), the same prompt and worked examples, one model at a time, no
  backups.
- **Scoring:** a sentence counts as right only if the record's type, amount and customer are all right.

**How to rerun it:**
- **Base model:** deploy it with `NATLAS_MODEL_ID=meta-llama/Meta-Llama-3-8B-Instruct modal deploy deploy/modal_natlas.py`.
- **N-ATLaS alone:** `python eval/run_eval.py --cases eval/cases_1000.jsonl --llm natlas --raw --workers 8`.
- **Base model alone:** the same with `--url <base app>/v1 --shots all`.
- **Full app:** the same without `--raw`.
- **Where everything is:** results in `eval/results/`, the log of all runs in `docs/RESULTS.md`.

**1,000 sentences** (`eval/cases_1000.jsonl`, 200 per language, 2 Oct 2026):

| | N-ATLaS alone | Llama-3-8B alone | Full app (N-ATLaS + code checks) |
|---|---|---|---|
| All | **69%** (66 to 71) | 51% (47 to 54) | 100% |
| English | 85% | 59% | 100% |
| Pidgin | 62% | 57% | 100% |
| Yorùbá | 69% | 60% | 100% |
| Hausa | **67%** | 27% | 100% |
| Igbo | 62% | 52% | 100% |
| Amounts said in Nigerian number words | **62%** | 12% | 100% |
| Wrong amount written | 68 | 170 | **0** |
| Median time (warm GPU) | 5.0 s | 5.3 s | 5.1 s |

**Read honestly:**
- **The model comparison is the result:** N-ATLaS is 18 points above its base model, and Hausa improves the most.
- **The full app's 100% is not proof:** our rules were built on similar template sentences, and the rules alone also
  score 100% on this set.
- **Fresh sentences:** on 100 sentences written later from research on how traders talk (`eval/cases_research.jsonl`,
  never used for tuning), the full app scored 69% before fixes.
- **Not settled:** on 210 other sentences (`eval/cases_fresh.jsonl`) the base model was ahead in Yorùbá and Pidgin.
- **No native-speaker check yet:** the Yorùbá, Hausa and Igbo test sentences were written by the team.
- **What will decide:** real traders' words, measured in the pilot.

**N-ATLaS mistakes found by the benchmark and now guarded** (tests in `eval/test_guards.py`):
- copying a worked example's price;
- taking the balance instead of the part paid;
- re-spelling customer names, which would split one customer in two.

## 4. Automated test log (run 10 Oct 2026, this commit)

`python eval/run_all.py` and `NODE_PATH=$(npm root -g) node eval/browser_test.cjs`:

```
✓ test_accounts.py           46/46
✓ test_agent.py              30/30
✓ test_ask.py                51/51
✓ test_askbook.py            31/31
✓ test_auth.py               38/38
✓ test_backup.py             16/16
✓ test_chat_smart.py         118/118
✓ test_clock.py              39/39
✓ test_converse.py           24/24
✓ test_corrections.py        35/35
✓ test_degraded.py           32/32
✓ test_demo_flow.py          25/25
✓ test_design.py             10/10
✓ test_extras.py             47/47
✓ test_guards.py             39/39
✓ test_hearing.py            47/47
✓ test_intron_tts.py         15/15
✓ test_language.py           9/9
✓ test_list.py               25/25
✓ test_live_intron.py        38/38
✓ test_natlas.py             42/42
✓ test_natlas_evidence.py    12/12
✓ test_preflight.py          12/12
✓ test_sms.py                36/36
✓ test_team.py               32/32
✓ test_telegram.py           42/42
✓ test_tools.py              47/47
✓ test_training.py           22/22
✓ test_validation_report.py  9/9
✓ test_whatsapp.py           19/19
✓ test_whatsapp_send.py      22/22
✓ test_wholesale.py          20/20

1030/1030 checks pass in 32 suites
80/80 browser checks pass   (eval/browser_test.cjs, real Chromium)
```

**What the suites cover:**
- **Integration checks:**
  - `test_natlas.py`: N-ATLaS first, its settings, waking, resting when down, the early start in live talk.
  - `test_degraded.py`: the app keeps serving traders when N-ATLaS is down.
  - `test_hearing.py`: two hearings merged, an amount kept only if heard.
  - `test_guards.py`: the N-ATLaS mistakes above.
  - `test_natlas_evidence.py`: the live evidence run in section 5.
- **The browser test:** sign-up, voice, live talk, check card, save, reminders, Telegram, and the privacy notice, in
  a real browser.

## 5. Live run on the server (for the evaluators, 15 to 17 Oct)

One command on the live server calls N-ATLaS exactly as the app does and prints:
- what is served;
- five record calls, one per language, with N-ATLaS's JSON, the time, and the record after code checks;
- five speech round trips through the N-ATLaS speech models;
- the N-ATLaS share of the pilot's AI answers and voice notes.

The command fetches the evidence script from the branch, so the app keeps running the submitted code and nothing
restarts:

```
sudo bash -c 'cd /opt/tradevoice/app && git fetch -q origin claude/tradevoice-handoff-b7942v && git show FETCH_HEAD:deploy/server/natlas_evidence.sh | bash'
```

Script: `scripts/natlas_evidence.py`, tested in `eval/test_natlas_evidence.py`. The output holds no keys, no names
and no phone numbers.

_The output of this command goes here. The team runs it on the live server and adds the output before submitting._

## 6. Licence and use

- TradeVoice uses N-ATLaS under the N-ATLaS Terms of Use v1.0. The attribution sentence appears on the website, in
  the app (Me > About), in the privacy notice, on the team dashboard, in the README and in every NAIC document.
- **Active users:** the licence allows up to 1,000 a month, and `/team` counts them. Beyond that, or before charging
  traders, we will agree commercial terms with Awarri and the Ministry.
- **N-ATLaS is never used to profile or score traders.** The lender report is plain code over the trader's own
  book, shared only by the trader.
