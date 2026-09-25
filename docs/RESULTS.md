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

### Hard trap set WITH the AI, 25 Sep (Mac, `--sleep 1.5`, before the fixes below)
Engine answered: nemotron-3-ultra (gemma-4 never answered in this run: to check). **AI failed on 38/211 → rules used.**
**All fields 171/208 = 82% (95%: 76–87%)**; type 96%, amount 92%, customer 96%, due day 88%; macro-F1 0.97;
🚨 wrong amount written 10/208; invented 0/14; asked on unclear notes 3/3. Latency median 8.2 s, 90% under 30 s.
Weakest: Yoruba 62%; local number words 42%; speech-to-text style 70%; negation 71%.
What went wrong (37 mistakes):
- **Our own guard broke right answers:** "she has not paid me" → forced to payment (4 cases).
- **Yoruba due dates:** the AI computed wrong dates for Ẹtì / Ọjọ́rú / Àbámẹ́ta (7 cases).
- **The AI multiplied:** "katan indomie 2 a 3500" → 7,000; "ẹgbàá" (2,000) with 2 cartons → 4,000.
- **Local number words:** ẹgbẹ̀rún mẹ́wàá (10,000) → 20,000; puku ise (5,000) → 500 / empty.
- **Rules fallback bugs:** phone number as amount, "N27" as a customer name, lower-case names, "Hajiya" unknown.

### Fixes (25 Sep), checked offline
- Rules now handle: "not paid yet" in 5 languages, part payments, "X each" (quantity × price), self-corrections,
  phone numbers, amounts in English/Hausa/Igbo/Yoruba words (⚠️ native check), lower-case names, Hajiya/Mallama/Dr.
- New AI checks (`_check_guard`): not-paid → credit; part payment → payment; **weekday dates always from the rules**;
  **the AI's amount must be a number actually said** (or quantity × price when "each" is said), else the rules amount
  is used and the trader is told why.
- Prompt: total vs per-unit, number words, not-paid words, Yoruba weekday names.
- `eval/test_guards.py`: the real AI mistakes above, replayed offline → **16/16 caught**.

| Offline rules only | Before | After |
|---|---|---|
| `cases_hard` (211, the set we tuned on) | 55% | 99% (206/208)* |
| `cases_fresh` (210, NEW draw, seed 7, not tuned on) | — | **99% (205/207, 95%: 97–100%)** |
| `cases.jsonl` / `cases_lang.jsonl` | 20/20, 16/16 | 20/20, 16/16 |
\* Tuned on this set, so it flatters us. `cases_fresh` uses the **same templates** with new names/amounts, so it
checks we didn't memorise cases, NOT that we handle new ways of speaking. The honest test is still
`cases_team.jsonl` (team phrases written without reading the code) + real voice notes.
Remaining: Hausa code-switch "za ta pay ranar …" → rules say sale (the AI should handle it).
➡️ Re-run with the AI on the Mac: `python3 eval/run_eval.py --cases eval/cases_hard.jsonl --sleep 1.5`, then
`--compare` old vs new result file; and find out why the AI failed 38 times (the report now lists the reasons).

### Model check + "I owe" with the AI (25 Sep, Mac)
`check_models.py`: **gemma-4-31b-it times out even on a one-line test** (text and photos); nemotron-3-ultra 1.2 s,
nemotron-3-super 2.9 s, llama-3.2-11b-vision 1.1 s. → new order (`.env`):
`LLM_MODELS=nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3-super-120b-a12b,google/gemma-4-31b-it`,
`VISION_MODELS=meta/llama-3.2-11b-vision-instruct,google/gemma-4-31b-it` (llama had slightly weaker tone marks:
94–95% vs 98–100%). Re-check gemma on Sunday.
`cases_owe` with AI (gemma still first): 11/13, 0 wrong amounts, 3 AI timeouts. Fixed after: Yoruba "Mo jẹ Alhaji…" (I owe)
filed as sale → guard now flips sale/credit → "I owe"; "Oga Emeka" shortened to "Emeka" by the AI → the full name
as said is kept (otherwise one customer becomes two). `test_guards.py` 19/19.

### Hard trap set WITH the AI, re-run after the fixes (25 Sep, Mac, `--sleep 1.5`)
**All fields 208/208 = 100% (95%: 98–100%)**, wrong amounts 0, invented 0, asked on unclear notes 3/3,
every language and every trap 100%. **AI answered 157/211 → 157/157 correct (95%: 98–100%).**
⚠️ Honest reading: the rules were tuned on this set, and the 53 AI failures were answered by those rules. Quote the
**157/157 AI-answered** figure, and use `cases_team.jsonl` + real voice notes as the real test.
**Problem: AI failed 53/211** (42 timeouts, 6 no JSON, 3 × 503, 2 connection errors); median 10.2 s, 90% under 30 s.
Engines that answered: nemotron-3-super + nemotron-3-ultra; **gemma-4 answered none**, probably timing out first
in the model list and eating the 30 s budget. → re-check `check_models.py`, reorder `LLM_MODELS`.

### Voice replies (Spitch), `eval/tts_check.py`, 25 Sep
✅ All 25 samples generated (5 languages × 5 messages; voices ufoma, lucy, sade, amina, ngozi).
✅ Re-generated with the fixes (25 Sep). Fixed before the listening test: Hausa used "ya/zai" (he) for women customers → now "ta/za ta"; trader now "An sayar"
(no gender guess); Yoruba sale "ní" added.
- 25 Sep team feedback: voices OK but **sound artificial / not Nigerian enough; too formal**. Changes: friendlier words
  (Pidgin "I don write am! … Now, she still dey owe you …", "E don clear!"), rotating openers so it doesn't repeat
  like a machine, "cleared debt" message, speed control (`TTS_SPEED`), per-language voice choice (`TTS_VOICE_<LANG>`),
  and `tts_check.py --audition` (every Spitch voice at 0.9 / 1.0 speed) to pick by ear.
- [ ] Audition picks: Pidgin __ · English __ · Yoruba __ · Hausa __ · Igbo __ · speed __
- [ ] Native-speaker listening scores (`eval/tts_samples/scores.txt`): Pidgin __ · Yoruba __ · Hausa __ · Igbo __
- [ ] Check: English numbers inside Yoruba/Hausa/Igbo voices; English day names vs Ẹtì / Juma'a / Fraịdee

### Still to do
- [x] Hard trap set with the AI (first run above)
- [ ] Re-run after fixes + `--compare`; fix the 38 AI failures
- [ ] Handwritten notebook photos (eval/photos/)
- [ ] Team-written phrases (eval/cases_team.jsonl) and native-speaker phrases
- [ ] Voice notes through Whisper / omniASR on Brev (speed + accuracy)
