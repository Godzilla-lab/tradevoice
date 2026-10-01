# N-ATLAS: what the models are (facts for building and for the NAIC PDFs)

Collected 1 Oct 2026 from the Hugging Face model cards (as quoted in search results) and public projects that
use them. Hugging Face itself was not reachable from our build machine, so **re-check each card** when
downloading and correct anything here that differs.

## The models (all under https://huggingface.co/NCAIR1)
| Model | What it is | Size | Notes |
|---|---|---|---|
| [`NCAIR1/N-ATLaS`](https://huggingface.co/NCAIR1/N-ATLaS) | Language model, fine-tuned from **Llama-3 8B** (`LlamaForCausalLM`, 32 layers, vocabulary 128,256) | ~16 GB at 16-bit, ~5 GB at 4-bit | English, Hausa, Igbo, Yorùbá. **Context 8,092 tokens.** Human-evaluation averages: English 4.21, Hausa 3.98, Igbo 3.87, **Yorùbá 2.69** (see below). |
| [`NCAIR1/Yoruba-ASR`](https://huggingface.co/NCAIR1/Yoruba-ASR) | Speech-to-text, **Whisper Small** fine-tune (the card also mentions MMS) | 244M parameters, ~500 MB | **You must accept conditions on the card before the files unlock.** Evaluated with WER and tone error rate. |
| [`NCAIR1/Hausa-ASR`](https://huggingface.co/NCAIR1/Hausa-ASR) | Speech-to-text, **Whisper Small** fine-tune | 244M | Training data from all 6 geopolitical zones, **about 120 hours** |
| [`NCAIR1/Igbo-ASR`](https://huggingface.co/NCAIR1/Igbo-ASR) | Speech-to-text, **Whisper Small** fine-tune | 244M | — |
| [`NCAIR1/NigerianAccentedEnglish`](https://huggingface.co/NCAIR1/NigerianAccentedEnglish) | Speech-to-text, **Whisper Small** fine-tune | 244M | Speakers from all 6 zones; **Nigerian English conventions and some Pidgin phrases** in training |

- **No dedicated Pidgin model exists.** Pidgin goes to `NigerianAccentedEnglish` and is *untested*, so we must
  measure it ourselves.
- **Download access:** the models are public, so no token is needed except where a card asks you to accept
  conditions (Yorùbá does). We use an HF token after accepting, to be safe.
- **Official usage** (from the cards): load each model with the `transformers` ASR pipeline, and feed it
  16 kHz mono audio, e.g. `librosa.load(..., sr=16000)`.
- **Format conversion:** WhatsApp voice notes (`.ogg` Opus) must be converted to 16 kHz mono WAV with ffmpeg
  first.
- **Quantised build:** a community 4-bit build exists, `inuwamobarak/N-ATLaS-8B-GGUF-Q4_K_M`, usable with
  llama.cpp or Ollama on a Mac. It's handy for development, but **for NAIC we serve the official
  `NCAIR1/N-ATLaS` weights** and say so.

## What this changes in our plan (ROADMAP Parts 4, 5 and 7)
1. **All 4 speech models are Whisper Small**, so the "trader's book as hints" fix (Part 5, item 2) works. We
   pass customer names and items as the Whisper prompt, about 50 terms, kept under 224 tokens.
2. **Whisper Small is small, about 500 MB per language**, so the speech models can run on the **always-on
   server's CPU**. That means no GPU wait for hearing; it's slower per note but always ready. We test speed on
   the server before deciding; if it's too slow, they share the Modal GPU with the LLM.
3. **Whisper's 30-second window:** voice notes over 30 s must be split into chunks (the pipeline's
   `chunk_length_s=30`).
4. **Whisper-small fine-tunes can get stuck repeating themselves** on hard audio. An independent benchmark saw
   whisper-tiny loop on 7 of 20 Hausa clips, worst on number-heavy sentences.
   - **Guard:** detect repeated words and characters, cap the output length relative to the audio length, and
     re-ask the trader if a loop is detected.
   - Never take an amount from a looping transcript.
5. **About 8K context for the LLM** confirms the memory budget in Part 8b.
6. **Pidgin is our biggest unknown:** it's a top priority in the market test set (Part 5, item 5).
7. **Hausa has 120 hours of training data**, a useful number for the integration PDF. Find the figures for the
   other languages on the cards.


---

## Confirmed from the N-ATLaS model card (read by the team, 1 Oct 2026)
**Model**
- Llama-3 8B base, BF16, about 8B parameters.
- Hidden size 4,096, 32 layers, 32 attention heads and 8 key-value heads.
- Max position embeddings 131,072, but **usable context is 8,092 tokens** ("for optimal performance"). Serve
  with `--max-model-len 8192`.
- **Chat template:** the Llama-3.1 style, with "Cutting Knowledge Date" and "Today Date". Pass `date_string`
  to `apply_chat_template`.
- **Recommended settings on the card:** `temperature=0.1`, `repetition_penalty=1.12`.
- The card lists **"Tool Integration: built-in support"**, so test tool or JSON calling for turning words into
  records.
- **Training:** about 392M tokens of supervised fine-tuning; about 318k samples in English and about 200k each
  in Hausa, Igbo and Yorùbá. Sources: open datasets, Google Translate and GPT translations, synthetic data from
  Nigerian web sources (BBC Pidgin, Punch), human cleaning, and Langeasy contributors from all 6 zones.
- Version 1.0, September 2025.

**Human evaluation (out of 5)**
| | English | Hausa | **Yorùbá** | Igbo |
|---|---|---|---|---|
| Evaluations | 1,662 | 140 | 542 | 296 |
| Average | 4.21 | 3.98 | **2.69** | 3.87 |
| Fluency | 4.30 | 4.23 | **2.71** | 3.89 |
| Accuracy | 4.23 | 3.72 | 3.13 | 3.92 |
| Bias/Fairness | 3.18 | **1.11** | 2.23 | 4.01 |

**Limitations stated on the card:**
- some bias issues;
- 8,092-token context;
- trained mainly on instruction-following tasks;
- plus the four speech limits (accent and dialect bias, children's speech, code-switching, noise).

### What this means for TradeVoice
1. **Yorùbá is N-ATLaS's weakest language (2.69/5)**, and Yorùbá traders are a big share of our users.
   - N-ATLaS *reads and understands*; the record is still checked by our rules, and amounts must have been said.
   - **Replies the trader hears in Yorùbá use our reviewed sentence templates (`ui_text.py`)**, not free text
     from the model.
   - Benchmark Yorùbá separately and report it honestly.
2. **Hausa's Bias/Fairness score is 1.11/5.** Keep model output factual and short, use templates for anything
   sensitive, and never let the model describe customers.
3. **Use the card's settings:** official chat template with `date_string`, temperature 0.1, repetition penalty
   1.12, and the system prompt kept short (8K context).
4. **Tool calling:** try structured output for extraction. Our rules stay as the check either way.

### Licence obligations ("Terms of Use for N-ATLaS", v1.0, September 2025)
- **Attribution is required in all public use**, in the app's About or Me screen, the README, the NAIC PDFs and
  the video. The required wording: "N-ATLaS is an initiative of the Federal Ministry of Communications,
  Innovation and Digital Economy, and powered by Awarri Technologies."
- **If renamed**, the model must carry "Powered by Awarri". We don't rename the model; TradeVoice is our app.
- **Derivatives:** any fine-tune or LoRA of N-ATLaS must be released **under the same terms** (relevant to
  ROADMAP Part 5, item 7).
- **User cap:** **at most 1,000 active end-users in a rolling 30 days.** Above that, a commercial licence from
  Awarri and the Ministry is needed.
  - **`/team` shows "N-ATLaS active users (30 days)" and warns at 800.**
- **Commercial use:** the model is "not an enterprise-grade or commercial system", and commercial use needs a
  separate agreement.
  - The pilot is civic/innovation use.
  - **Contact Awarri (datasupport@awarri.com) before charging traders.**
- **Prohibited uses** include discriminatory profiling and unauthorised personal data collection.
  - **Never use N-ATLaS to score or profile traders for lenders.** The lender report stays plain code over the
    trader's own book, shared only with the trader's consent.
- **Must report accuracy, bias and limitations transparently**, which matches our plan (ROADMAP Part 5).
- **Law:** Nigerian law; disputes go to mediation through the Federal Ministry of Justice first.

### Others building on N-ATLaS
About 20 Hugging Face Spaces use it, including `seun-ajayi/n-atlas-evaluations` (worth checking for evaluation
ideas). There are 5 quantised versions and 2 adapters in the model tree.

## Still to confirm on the cards (team: please check and fill in)
- [x] Context length (8,092 tokens) and chat template (Llama-3.1 style with `date_string`)
- [x] Licence: the 1,000-active-user cap is confirmed, and commercial use needs an agreement (see above)
- [ ] Training hours and published WER for Yorùbá, Igbo and Nigerian-accented English
- [ ] Whether any card states known limitations beyond the four on GitHub (accent, children, code-switching,
      noise)
