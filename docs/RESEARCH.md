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

Best single line: *"Nearly every Nigerian small business has a bank account, but only 1 in 5 has a loan, and weak
records are a big reason why."*

## Winning the 90-second video (Devpost guidance)
- Hook in the first 5 seconds: the trader's problem, not a title slide.
- Show the **working product**, not slides. Clean audio. Captions for numbers.
- One quick architecture frame showing **Brev GPU + Whisper + NVIDIA models** (for the AI + Brev criterion).
- Upload early (uploads can take a long time) and test links in a private window. Keep a backup take.
- https://info.devpost.com/blog/6-tips-for-making-a-hackathon-demo-video · https://info.devpost.com/blog/hackathon-judging-tips
