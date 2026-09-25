# 🔎 Research notes (checked 24 Sep 2026)

Some NVIDIA / Hugging Face pages were blocked for our research tool, so several facts come from search summaries.
**⚠️ UNVERIFIED** = check it yourself before Sunday.

## What changed in our setup because of this research
| Finding | What we did |
|---|---|
| `meta/llama-3.3-70b-instruct` model card says it **will be deprecated on 25 Aug 2026** | All AI calls go through `llm.py`, which tries a list of models and uses the first one that works. Default order: `nvidia/nemotron-3-super-120b-a12b` → Llama 3.3 70B → Llama 3.1 70B. **Run `python check_models.py` with your key.** |
| Newer NVIDIA vision model `nvidia/nemotron-nano-12b-v2-vl` is built for documents/receipts (tops OCRBench v2) | Vision default order: Nemotron Nano 12B v2 VL → Llama 3.2 90B Vision → 11B |
| Inline images on NVIDIA's API must be small (~180 KB, ⚠️ UNVERIFIED); OpenAI `image_url` data-URL format is the current format | Photos are resized to ≤1024 px JPEG (~20–170 KB) and sent as `image_url` |
| Nemotron models may print reasoning (`<think>…</think>`) before the answer | `llm.clean()` strips it before reading the JSON |
| NVIDIA free-tier rate limits vary by model and are not published | Client retries with backoff (`max_retries=3`); on failure the app falls back to offline rules |
| `large-v3-turbo` is much faster than `large-v3` with similar accuracy | Default `ASR_MODEL=large-v3-turbo` (set `large-v3` to compare) |
| Brev's own tunnels sit behind Cloudflare login, so phones/webhooks can't call them directly | We use **Gradio's share link** (`GRADIO_SHARE=1`) from the Brev instance, which gives a public `gradio.live` URL. Backup: `brev port-forward <instance> --port 7860:7860` for team testing |

## NVIDIA Brev
- **Launchables** = one-click templates (GPU + container + repo). A TradeVoice Launchable = great proof of Brev use for the
  jury (and anyone can reproduce our demo). https://docs.nvidia.com/brev/concepts/launchables
- **Stop** = GPU released, data kept (storage may still cost). **Delete** = everything gone, no charges. When credits run
  out, Brev pauses/deletes instances. A restarted instance may get a new IP. https://docs.nvidia.com/brev/concepts/gpu-instances
- Credits are redeemed in the Brev console (event voucher steps ⚠️ UNVERIFIED).
- Prices ⚠️ check in the console: L40S seen at ~$1.06/hr; typical market L4 ~$0.7/hr. An **L4 (24 GB)** is enough for
  Whisper turbo + the app. An **L40S (48 GB)** could also self-host a vision model (Qwen2.5-VL-7B / Nemotron Nano VL) with vLLM.
- Port forward: `brev port-forward <instance> --port 8000:8000`. https://docs.nvidia.com/brev/cli/connectivity

## Speech (ASR)
- faster-whisper needs **CUDA 12 + cuDNN 9** (fix in README). A 10–20 s voice note should take ~1–2 s on an L4
  (estimate; measure it and put the real number in the submission).
- NVIDIA Parakeet is weak on Nigerian English (~33% word error rate on the AfriSpeech benchmark); Whisper is the right choice.
  https://arxiv.org/html/2511.14255
- **N-ATLaS** (NCAIR/Awarri, Sept 2025): Nigerian LLM + Whisper-Small fine-tunes for Nigerian-accented English, Yoruba,
  Hausa, Igbo on Hugging Face (`NCAIR1/...`). **Research-only licence**. Mention it as our local-language roadmap;
  commercial use needs an agreement. https://huggingface.co/NCAIR1

## Kredete (our primary prize partner)
US-based fintech (founded 2023 by Adeola Adedewe): remittances to 30+ African countries **plus credit-building**
(reports payments to US credit bureaus). ~700k monthly users, $22M Series A (Sept 2025).
**Pitch angle:** Kredete turns everyday money flows into credit history. TradeVoice does the same for informal traders
who have **no credit file at all**: their daily sales, repayments and records become a history a lender can read.
https://fintech.global/2025/09/16/fintech-firm-kredete-raises-22m-series-a-for-global-expansion/

## Nigeria numbers for the pitch (quote 2–3, with source on screen)
| Stat | Source |
|---|---|
| **39+ million MSMEs**, 87.9% of jobs, 46.3% of GDP | SMEDAN/NBS MSME survey 2021: https://www.nigerianstat.gov.ng/download/290 |
| **92.2%** of employed Nigerians work informally | NBS 2023: https://www.vanguardngr.com/2024/02/92-of-nigerian-workers-are-in-informal-employment-nbs/ |
| **26%** of adults financially excluded | EFInA A2F 2023: https://a2f.ng/efina-report-nigerias-formal-financial-inclusion-grows-to-64-in-2023/ |
| **$32.2B** MSME finance gap | IFC (2023): https://businessday.ng/business-economy/article/nigerian-small-businesses-suffer-32-2bn-finance-gap-ifc/ |
| **1 in 4** informal business owners keep no records; **38%** of record-keepers track "mentally" | Moniepoint: https://moniepoint.com/blog/nigeria-small-business-statistics |
| **94.8%** of SMEs have bank accounts but only **20.2%** have bank loans (weak records) | World Bank Enterprise Survey via BusinessDay: https://businessday.ng/business-economy/article/smes-face-credit-squeeze-over-weak-records/ |

Best single line: *"Even among registered Nigerian SMEs, 95% have a bank account but only 1 in 5 has a loan, and weak
records are a big reason why."* (The 94.8% / 20.2% figures come from a survey of SMEs, not from all 39M micro-businesses,
most of which are informal. Don't say "nearly every small business".)

## Winning the 90-second video (Devpost guidance)
- Hook in the first 5 seconds: the trader's problem, not a title slide.
- Show the **working product**, not slides. Clean audio. Captions for numbers.
- One quick architecture frame showing **Brev GPU + Whisper + NVIDIA models** (for the AI + Brev criterion).
- Upload early (uploads can take a long time) and test links in a private window. Keep a backup take.
- https://info.devpost.com/blog/6-tips-for-making-a-hackathon-demo-video · https://info.devpost.com/blog/hackathon-judging-tips

## Nigerian languages: which models to use (researched 24 Sep 2026)
Source pages were mostly blocked for our research tool; numbers come from search summaries. **Run `python eval/lang_check.py`
with your key: our own scoreboard beats any of this.**

**Text benchmarks (IrokoBench, Hausa / Igbo / Yoruba average):** GPT-4o 75 / 68 / 72 · Aya-101 57 / 56 / 55 · Gemma 2 27B
50 / 46 / 45 · Llama 3.1 70B 43 / 42 / 39. Gemma is the strongest *open* family for these languages; Llama is weakest.
(https://arxiv.org/pdf/2406.03368, AfroBench: https://github.com/McGill-NLP/AfroBench)

**Photos:**
- **Llama 3.2 Vision: "English is the only language supported" for image+text** (Meta model card), so it's now last in our list.
- **Gemma 4** (Apr 2026): 140+ languages in pre-training, multilingual OCR + handwriting listed. **Qwen 3.5**: 201 languages.
- **No benchmark exists for handwritten Yoruba/Igbo/Hausa.** Our own photo test is the only real evidence we'll have.

**New default order** (IDs from search results; `check_models.py` shows which your key can actually use):
```
LLM_MODELS=nvidia/nemotron-3-super-120b-a12b,google/gemma-4-31b-it,qwen/qwen3.5-397b-a17b,meta/llama-3.3-70b-instruct
VISION_MODELS=google/gemma-4-31b-it,qwen/qwen3.5-397b-a17b,nvidia/nemotron-nano-12b-v2-vl,meta/llama-3.2-90b-vision-instruct
```

**Speech (important):**
- **Whisper does NOT support Igbo at all**, and is poor at Yoruba (error rates can exceed 100% on FLEURS) and Hausa (~8 h of
  training data). Whisper is fine for **English and Pidgin**, which is what we demo.
- Better options for local-language voice notes:
  - **Meta omniASR** (`facebook/omniASR-LLM-7B`, Apache-2.0, 1,600+ languages incl. Yoruba, Igbo, Hausa, ~15 GB GPU),
    self-hostable on Brev. **Strong Brev story.** https://github.com/facebookresearch/omnilingual-asr
  - **NCAIR1 Yoruba-ASR / Hausa-ASR / Igbo-ASR** (Whisper-small fine-tunes, N-ATLaS family); licence capped at 1,000
    active users.
  - **Spitch** (Nigerian speech API, outputs tone marks): hosted, pricing unknown. https://docs.spitch.app/

**N-ATLaS** (`NCAIR1/N-ATLaS`, Llama-3-8B fine-tune for English/Hausa/Igbo/Yoruba): +4 to +11 points over its base model,
but still well below the big API models. Licence: max 1,000 active users, "Powered by Awarri" naming. Good as a *demo
extra* on Brev (e.g. replies in Yoruba), not as the main extraction model.

**What to say in the pitch:** "English and Pidgin voice today; photos in Yoruba, Hausa and Igbo tested with [score];
local-language speech next, using Meta omniASR / N-ATLaS models on our Brev GPU." Honest and it scores Responsible AI points.

## Voice replies (text-to-speech) for traders who can't read, researched 25 Sep 2026
Many traders speak Yoruba/Hausa/Igbo/Pidgin fluently but can't read, so TradeVoice reads confirmations back aloud
(`tts.py`: "I hear say…" before saving, "I don write am…" after, with the customer's new total).

| Option | Languages | Use | Licence / cost |
|---|---|---|---|
| **Spitch** (Nigerian), **primary** | English, **Pidgin** (by voice e.g. `ufoma`), Yoruba (`sade`), Hausa (`amina`), Igbo (`ngozi`) | Hosted API, `pip install spitch`; outputs wav/mp3/**ogg_opus** (WhatsApp voice notes); also STT, translation, Yoruba tone-marking | Commercial ToS; **$1 free credit** for new devs |
| YarnGPT2 (Nigerian, open source) | Nigerian English, Yoruba, Igbo, Hausa | Self-host on Brev (small LM + WavTokenizer) or free API (80 req/day, async) | Apache/MIT (⚠️ UNVERIFIED) |
| Meta MMS-TTS | Yoruba, Hausa, English (no Igbo found) | Offline on CPU/GPU (`requirements-tts.txt`, `TTS_BACKEND=mms`) | **CC-BY-NC: demo only** |
| Intron Sahara v2.5 | Igbo, Hausa (+ more) | No self-serve signup found | n/a for Sunday |
| Google / Azure / NVIDIA Magpie / ElevenLabs | No Yoruba/Igbo voices (Azure: Nigerian English only) | | |

**Numbers:** no engine is proven to read digits in Yoruba/Hausa/Igbo, and `num2words` has no yo/ha/ig. So amounts
are spoken as **English words** ("forty-five thousand naira"), which traders commonly use anyway. Our own
`tts.number_words()` handles this (no extra library).
⚠️ Spitch voice names and Pidgin handling came from their SDK source and GitHub projects (their docs were blocked for
our research tool). Check them in the Spitch dashboard. Yoruba/Hausa/Igbo sentences in `tts.py` need a native-speaker
check: run `python eval/tts_check.py` and do a listening test.
Sources: pypi.org/project/spitch · github.com/spi-tch/spitch-python · github.com/saheedniyi02/yarngpt ·
huggingface.co/facebook/mms-tts-yor · intron.io
