# N-ATLAS: what the models are (facts for building and for the NAIC PDFs)

Collected 1 Oct 2026 from the Hugging Face model cards (as quoted in search results) and public projects that
use them. Hugging Face itself was not reachable from our build machine, so **re-check each card** when
downloading and correct anything here that differs.

## The models (all under https://huggingface.co/NCAIR1)
| Model | What it is | Size | Notes |
|---|---|---|---|
| [`NCAIR1/N-ATLaS`](https://huggingface.co/NCAIR1/N-ATLaS) | Language model, fine-tuned from **Llama-3 8B** (`LlamaForCausalLM`, 32 layers, vocabulary 128,256) | ~16 GB at 16-bit, ~5 GB at 4-bit | English, Hausa, Igbo, Yorùbá. 400M+ tokens of multilingual instruction data. **Context about 8K tokens** (the card is quoted as "8,092"; probably 8,192). Reported scores: English 4.21/5, Hausa 3.98/5, Igbo 3.87/5; Yorùbá "ongoing improvements". |
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

## Still to confirm on the cards (team: please check and fill in)
- [ ] Exact context length of `N-ATLaS` and its chat template (Llama-3 instruct format?)
- [ ] Licence text for the LLM and ASR models (the reported 1,000-active-user free limit, and commercial terms)
- [ ] Training hours and published WER for Yorùbá, Igbo and Nigerian-accented English
- [ ] Whether any card states known limitations beyond the four on GitHub (accent, children, code-switching,
      noise)
