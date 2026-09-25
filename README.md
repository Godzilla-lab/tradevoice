# TradeVoice 🗣️📸💰
**Speak it or snap your book: bookkeeping, debt tracking and money insights for Nigerian market traders.**

Built for **Come Build with AI** (GOMYCODE × NVIDIA, 27 Sep 2026). Primary prize: **Kredete Financial Inclusion Award**.

> ✅ **Prep checklist for the 4 of us: [`docs/PREP_PLAN.md`](docs/PREP_PLAN.md)** · 📊 **Test results: [`docs/RESULTS.md`](docs/RESULTS.md)**
>
> 👋 **New to the team? Read [`TEAM_GUIDE.md`](TEAM_GUIDE.md) first.** It covers who does what, the plan for the day and the rules we must follow.
> **WhatsApp plan:** [`docs/WHATSAPP.md`](docs/WHATSAPP.md). Traders will use TradeVoice inside WhatsApp; the web app is the dashboard.
> Other docs: [`docs/RULES_CHECKLIST.md`](docs/RULES_CHECKLIST.md) · [`docs/PITCH.md`](docs/PITCH.md) (video script + project card) ·
> [`docs/SUBMISSION.md`](docs/SUBMISSION.md) (disclosure + test results to fill in) · [`docs/RESEARCH.md`](docs/RESEARCH.md)

---

## The problem
Nigerian market traders sell on credit and keep records in their heads or in a notebook. They forget who owes them, they
don't know their real profit, and without records they can't get a loan from a microfinance bank or cooperative.

## What TradeVoice does
| Feature | What the trader does | What happens |
|---|---|---|
| 🎙️ **Speak** | Sends a voice note: *"I sell 3 bags of rice give Mama Tunde, 45k, she go pay Friday"* (or in Yoruba, Hausa, Igbo) | Whisper for English/Pidgin, **Meta omniASR for Yoruba/Hausa/Igbo**, both on our **NVIDIA Brev GPU** → text → LLM → entry: *credit sale, ₦45,000, Mama Tunde, due Fri* → trader confirms |
| 📸 **Snap your book** | Takes a photo of a notebook page or receipt | Vision AI reads every line → editable table → trader ticks and saves all |
| 🔊 **Voice replies** | Can't read? Just listen | The app reads the entry back aloud in Pidgin, English, Yoruba, Hausa or Igbo before and after saving (Spitch, Nigerian TTS) |
| 🏷️ **Credit check** | Records a credit sale | Warning if that customer is already late: *"⛔ Oga Emeka already owes ₦30,600 and is 18 days late"* |
| 📒 **Who owes me** | Opens the tab | Everyone who owes, how much, how late. Payments clear the oldest debt first |
| 📲 **WhatsApp reminder** | Picks a debtor + Pidgin / English / Yoruba | Polite reminder opens in WhatsApp; the trader presses send themselves |
| 🔮 **Insights** | Opens the tab | Next 7 days' sales forecast, expected cash, debts coming in, busiest day, best sellers, restock tip |
| 💬 **Ask my book** | *"How much Mama Tunde owe me?"*, *"Wetin sell pass this week?"* | Answer in their own style, from their own numbers only |
| 🏦 **Credit profile + statement** | Downloads a statement | A transparent 0–100 record score + weekly summary to show a lender, cooperative or ajo group |
| 🎤 **Ask my book, in your language** | "Ìrẹsì mélòó ni mo tà lóṣù yìí?" · "Shinkafa nawa na sayar a wannan makon?" | Voice or text question in English, Pidgin, Yoruba, Hausa or Igbo → the AI only turns it into a search (item, period, sold/bought/owed) → numbers added up from the book → answer as text + voice note in the same language. Works offline with word lists. `eval/test_askbook.py` |
| 🧾 **Who I owe** | "Alhaji give me 10 bags on credit, I go pay Friday" / "I don pay Alhaji 50k" | The trader's OWN debts to suppliers/lenders, with promised dates and voice replies; goods on credit count as spending, borrowed cash doesn't |
| 📒 **My year so far** | One button | Sales, money spent **by type** (restock, rent, levies, transport, power, staff), monthly totals, rent & levy payments to keep receipts for. Also in the statement. Facts from the book only, no tax advice (tax research in progress: `docs/FINANCE_RESEARCH.md`) |
| 🔒 **My data** | — | Consent first, audio and photos deleted after reading, nothing saved without confirmation, delete-everything button |

## How it works
```
 Voice note ─► Whisper (English/Pidgin) or Meta omniASR (Yoruba/Hausa/Igbo), on NVIDIA Brev GPU ┐
                                                                                 ├─► text lines
 Book photo ─► Nemotron Nano VL vision model (build.nvidia.com, or self-hosted on Brev) ┘
                                         │
                                         ▼
          NVIDIA Nemotron LLM (build.nvidia.com) ─► entries ◄─ rule-based parser (offline fallback
                                         │                      + checks every amount against the text)
                                         ▼
                    Trader CONFIRMS / edits ─► SQLite ledger
                                         │
     ┌──────────────┬───────────────┬────┴─────────┬──────────────────┬──────────────────┐
   Today      Who owes me +     Insights +     Ask my book        Credit profile +
              reminders         forecast       (LLM phrases       lender statement
                                               computed facts)
```
**Design rule: AI reads and phrases; plain Python does the maths.** Totals, balances, the forecast and the score are
deterministic and explainable, so the AI can never invent a number in your books.

## Code map
| File | What it does |
|---|---|
| `app.py` | Gradio web app with all the tabs |
| `llm.py` | Every NVIDIA API call, with automatic fallback to the next model if one is deprecated |
| `check_models.py` | Lists the models your key can see and tests ours. **Run this first** |
| `eval/lang_check.py` | Scoreboard: which model reads/understands Yoruba, Hausa, Igbo, Pidgin best |
| `asr.py` | Speech-to-text: Whisper for English/Pidgin, Meta omniASR for Yoruba/Hausa/Igbo (Whisper has no Igbo); or calls `asr_server/` |
| `requirements-omni.txt` | Extra install for Yoruba/Hausa/Igbo voice (Brev GPU only) |
| `asr_server/server.py` | Optional standalone speech API (FastAPI) for a Brev GPU, same engines as `asr.py` |
| `vision.py` | Book photo → text lines (shrinks the image to fit NVIDIA's inline-image limit) |
| `extract.py` | Text → entries. LLM first; rules as fallback and amount cross-check. `extract()` for one, `extract_many()` for many lines |
| `ledger.py` | SQLite storage, daily summary, debtors (oldest debt paid first), customer credit check, record score |
| `insights.py` | Forecast, best sellers, WhatsApp reminders, Ask-my-book, lender statement |
| `seed_demo.py` | 3 weeks of **synthetic, flagged** demo history for the presentation |
| `eval/run_eval.py` + `eval/cases*.jsonl` | Accuracy and speed test with 95% ranges, per language and per trap (`docs/TESTING.md`) |
| `eval/make_hard_cases.py` | Generates 211 trap phrases in 5 languages (`eval/cases_hard.jsonl`) |

## Quick start (laptop, no GPU, no key: everything except photos works offline)
```bash
git clone https://github.com/Godzilla-lab/tradevoice.git && cd tradevoice
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed_demo.py --wipe      # demo history (optional)
python app.py                   # open http://localhost:7860
python eval/run_eval.py         # accuracy report (hard traps: --cases eval/cases_hard.jsonl, see docs/TESTING.md)
```
Tick the consent box, then try typing `I sell 2 crates of eggs give Oga Emeka, 10,800, he go pay Monday`.

With AI switched on:
```bash
cp .env.example .env            # put your nvapi-... key in it
set -a; source .env; set +a
python check_models.py          # which NVIDIA models work with your key
python app.py
```

## Run on NVIDIA Brev (event day)
1. Activate the voucher → create a GPU instance (an L4 / A10-class 24 GB GPU is plenty; pick the cheapest that works).
2. On the instance:
   ```bash
   git clone https://github.com/Godzilla-lab/tradevoice.git && cd tradevoice
   pip install -r requirements.txt
   export NVIDIA_API_KEY=nvapi-...
   # eval/audio/ is empty in git: upload one of the team's recorded voice notes first (e.g. with scp)
   python -c "import asr; print(asr.transcribe('eval/audio/01.m4a'))"   # downloads + warms up Whisper on the GPU
   GRADIO_SHARE=1 python app.py      # prints a public https://….gradio.live link for demo + submission
   ```
   Why the Gradio link: Brev's own tunnels sit behind a Cloudflare login, so judges' phones can't open them directly.
   For team-only testing you can also use `brev port-forward <instance> --port 7860:7860`.
3. **Yoruba / Hausa / Igbo voice (Meta omniASR).** Start this early: it downloads ~17 GiB the first time.
   ```bash
   sudo apt-get install -y ffmpeg libsndfile1
   pip install -r requirements-omni.txt
   python -c "import asr; print(asr.omni_languages_ok())"          # expect all True
   python -c "import asr; print(asr.transcribe('eval/audio/yo1.m4a', 'Yoruba'))"   # downloads + warms up
   ```
   Default model `omniASR_LLM_3B_v2` (~10 GB GPU memory) fits next to Whisper on a 24 GB L4. On a 48 GB L40S you can
   use `OMNI_MODEL=omniASR_LLM_7B_v2` (~17 GB, more accurate). Voice notes are cut at 39 s (model limit).
   If the install clashes with other packages: make a second virtualenv, run `asr_server` there
   (`cd asr_server && uvicorn server:app --port 8000`) and start the app with `ASR_URL=http://localhost:8000`.
4. If faster-whisper complains about missing cuDNN/cuBLAS (fix from the faster-whisper README):
   ```bash
   pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
   export LD_LIBRARY_PATH=`python3 -c 'import os; import nvidia.cublas.lib; import nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ":" + os.path.dirname(nvidia.cudnn.lib.__file__))'`
   ```
5. **Stop the instance whenever you're not using it.** Screenshot the Brev console (GPU type, runtime, cost) for the submission.

Optional stretch (more Brev usage): self-host an open vision model on the same GPU with vLLM and set
`VISION_BASE_URL=http://localhost:8001/v1`, `VISION_MODELS=<model>`, `VISION_API_KEY=none`. Bonus: package the whole
stack as a **Brev Launchable** (one-click template) and show it in the video. See `docs/RESEARCH.md`.

## Environment variables
| Variable | Default | Purpose |
|---|---|---|
| `NVIDIA_API_KEY` | – | build.nvidia.com key. Without it: offline rules, no photo reading |
| `LLM_MODELS` | `nvidia/nemotron-3-super-120b-a12b,google/gemma-4-31b-it,qwen/qwen3.5-397b-a17b,meta/llama-3.3-70b-instruct` | Text models, tried in order |
| `VISION_MODELS` | `google/gemma-4-31b-it,qwen/qwen3.5-397b-a17b,nvidia/nemotron-nano-12b-v2-vl,meta/llama-3.2-90b-vision-instruct` | Photo models, tried in order (multilingual first) |
| `VISION_BASE_URL` / `VISION_API_KEY` | NVIDIA API / `NVIDIA_API_KEY` | Point at a self-hosted vLLM server instead |
| `ASR_MODEL` | `large-v3-turbo` | Whisper model on GPU (`small` on CPU); try `large-v3` for max accuracy |
| `OMNI_MODEL` | `omniASR_LLM_3B_v2` | Meta omniASR model for Yoruba/Hausa/Igbo voice (`omniASR_LLM_7B_v2` on a 48 GB GPU) |
| `ASR_URL` / `ASR_TOKEN` | – | Use a remote `asr_server` instead of local speech models |
| `DB_PATH` | `tradevoice.db` | SQLite file |
| `SHOP_NAME` | `Chioma Stores` | Default shop name on reminders and statement |
| `GRADIO_SHARE` | – | `1` = public link |

## Honesty notes
- The starter code was prepared before the event with an AI coding assistant (Claude) and open-source parts. It is disclosed
  in `docs/SUBMISSION.md`, and the commit history shows what was built on the day.
- Demo history from `seed_demo.py` is synthetic and marked as such in the app and on the statement.
- The 20 test phrases in `eval/cases.jsonl` were written together with the rules, so their score is optimistic. We
  report results on new phrases written by teammates (see `TEAM_GUIDE.md`).

License: MIT
