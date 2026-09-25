# 📊 Test results log

Record every real run here (date, who, command, numbers). These numbers go into `docs/SUBMISSION.md` and the video.
⚠️ Test phrases in `eval/cases*.jsonl` were written by our team/Claude, not native speakers yet. Say so when quoting them.

## 25 Sep 2026: first real NVIDIA API runs (MacBook, build.nvidia.com free tier)

**Models available to our key** (`check_models.py --search`): text: gemma-4-31b-it, nemotron-3-ultra-550b-a55b,
nemotron-3-super-120b-a12b (+ slower: kimi-k3, glm-5.3); vision: gemma-4-31b-it, llama-3.2-11b-vision-instruct.
Removed by NVIDIA (410): llama-3.3-70b, llama-3.1-70b, nemotron-nano-12b-v2-vl, qwen3.5-397b.

**Chosen order** (`.env`):
```
LLM_MODELS=google/gemma-4-31b-it,nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3-super-120b-a12b
VISION_MODELS=google/gemma-4-31b-it,meta/llama-3.2-11b-vision-instruct
```

### Full app pipeline (AI + our guards), `eval/run_eval.py`
| Test set | Result | Median / worst latency |
|---|---|---|
| English + Pidgin (20 phrases) | **20/20** | 5.6–6.7 s / 34 s* |
| Pidgin + Yoruba + Hausa + Igbo (16 phrases) | **16/16** (15/16 before the "has paid" / "I sold" guards) | varies, see note |

\* Before the 30 s total deadline was added. Worst case now capped at 30 s, then offline rules.

### Raw model ability, no guards, `eval/lang_check.py --text-only`
| Model | Hausa | Igbo | Pidgin | Yoruba |
|---|---|---|---|---|
| gemma-4-31b-it | 4/4 | 4/4 | 4/4 | 4/4 |
| nemotron-3-ultra-550b-a55b | 4/4 | 4/4 | 4/4 | 4/4 |
| nemotron-3-super-120b-a12b | 2/4 | 3/3 (+1 no answer) | 4/4 | 4/4 |
Super's errors: Hausa payment → "expense"; "2 cartons … 18500" → ₦37,000 (multiplied).

### Photo reading (printed test images, not handwriting), `eval/lang_check.py --images-only`
| Model | Hausa | Igbo | Pidgin | Yoruba |
|---|---|---|---|---|
| gemma-4-31b-it (letters / tone marks / amounts) | 99% / 99% / 4/4 | 100% / 100% / 4/4 | 100% / 100% / 4/4 | 100% / 98% / 4/4 |
| llama-3.2-11b-vision | 99% / 99% / 4/4 | 98% / 94% / 4/4 | 99% / 99% / 4/4 | 99% / 95% / 4/4 |

### Hard trap set, offline rules only (baseline), `run_eval.py --cases eval/cases_hard.jsonl --rules-only`
211 phrases, 5 languages, 13 trap types (see `docs/TESTING.md`). **All fields 114/208 = 55% (95%: 48–61%)**;
wrong amount written 36/208; invented amounts 0/14.
Rules score 0% on unit price, part payment, amounts in words, local number words; 21% on negation.
**Bug found:** "she has not paid me" contains "paid me" → rules say *payment* → our "has paid" guard can flip a correct
AI answer to payment. Also: phone numbers read as the amount (Pidgin/Yoruba/Hausa/Igbo), "Hajiya" not known as a title.
➡️ Next run: the same set **with the AI** (Mac, `--sleep 1.5`), to see how much the AI fixes and where the guards hurt.

### Voice replies (Spitch), `eval/tts_check.py`, 25 Sep
✅ All 25 samples generated (5 languages × 5 messages; voices ufoma, lucy, sade, amina, ngozi).
Fixed before the listening test: Hausa used "ya/zai" (he) for women customers → now "ta/za ta"; trader now "An sayar"
(no gender guess); Yoruba sale "ní" added.
- [ ] Native-speaker listening scores (`eval/tts_samples/scores.txt`): Pidgin __ · Yoruba __ · Hausa __ · Igbo __
- [ ] Check: English numbers inside Yoruba/Hausa/Igbo voices; English day names vs Ẹtì / Juma'a / Fraịdee

### Still to do
- [ ] Hard trap set with the AI (and `--compare` against the rules run)
- [ ] Handwritten notebook photos (eval/photos/)
- [ ] Team-written phrases (eval/cases_team.jsonl) and native-speaker phrases
- [ ] Voice notes through Whisper / omniASR on Brev (speed + accuracy)
