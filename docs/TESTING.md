# 🧪 How we test TradeVoice

Goal: numbers we can defend to judges. Easy tests that pass 100% prove little, so we test the **traps** that put a
wrong number in a trader's book, and every score comes with a 95% range.

## The test sets
| File | What | Who wrote it |
|---|---|---|
| `eval/cases.jsonl` | 20 easy English/Pidgin phrases | Claude |
| `eval/cases_lang.jsonl` | 16 phrases: Pidgin, Yoruba, Hausa, Igbo (4 each) | Claude ⚠️ native check |
| `eval/cases_hard.jsonl` | **211 trap phrases**, 5 languages, 13 trap types (`python eval/make_hard_cases.py`) | generated from templates ⚠️ native check |
| `eval/cases_fresh.jsonl` | 210 phrases, same templates, **new random draw** (seed 7): checks fixes weren't tuned to `cases_hard` | generated ⚠️ native check |
| `eval/test_guards.py` | real AI mistakes replayed offline: our guards must catch them (no key needed) | from our AI runs |
| `eval/cases_team.jsonl` | the team's own phrases, written **without reading the code** (most honest score) | team |
| `eval/photos/` | real notebook photos + `.txt` of what is written | team |
| `eval/audio/` | real voice notes named by case id | team (native speakers) |

### Trap types in `cases_hard.jsonl`
| Trap | Example | Right answer |
|---|---|---|
| amount_format | 45k · ₦45,000 · N45,000 · "45 thousand" · 1.2m | 45,000 / 1,200,000 |
| words | "sixty thousand naira" (how speech-to-text writes it) | 60,000 |
| local_numbers | Hausa "naira dubu biyar", Igbo "puku ise", Yoruba "ẹgbẹ̀rún márùn-ún" | 5,000 |
| unit_price | "5 bags at 15k each" | **75,000** (total, not 15k) |
| negation | "she has **not** paid me yet" | credit, **not** payment |
| part_payment | "paid 20k out of the 60k she owes, 40k remaining" | payment of **20,000** |
| no_amount | "Mama Tunde took 2 bags, she will pay Friday" | amount empty, **never invented** |
| distractor | "…her number na 08034567812" · "pay on the 15th" | ignore the phone / date |
| self_correct | "11k, sorry no, 12,000" | 12,000 |
| code_switch | "Mo sell àpò ẹ̀wà 2 fún Iya Bisi 60000, she go pay…" | credit |
| asr_noise | no tone marks, no punctuation, lower case, "ehn/abeg/um" | same as clean |
| flag | two entries in one note; "four five" | AI should **ask** (low confidence / note) |

## Commands
```
python eval/run_eval.py --cases eval/cases_hard.jsonl --sleep 1.5      # AI + guards (~10 min, free tier)
python eval/run_eval.py --cases eval/cases_hard.jsonl --rules-only     # offline rules = the baseline to beat
python eval/run_eval.py --cases eval/cases_hard.jsonl --lang yoruba --category negation,part_payment
python eval/run_eval.py --compare eval/results/A.json eval/results/B.json   # is B really better, or luck?
python eval/test_guards.py                     # offline: do our guards catch the AI's known mistakes?
python eval/lang_check.py                      # which model is best per language (text + photos)
python eval/tts_check.py                       # voice-reply samples + scores.txt form for native speakers
```
The report shows: accuracy per field **with 95% range (Wilson)**, all-fields score, type macro-F1,
🚨 **wrong amount written** (the worst mistake: a wrong number is worse than an empty one), invented amounts,
score per language and per trap, a type confusion table, latency (median / 90% / max), and how often the AI failed
and the offline rules were used. Each run is saved in `eval/results/` (not committed) for `--compare`.

## Rules for honest numbers
- **Small tests prove little.** 16/16 = "somewhere between 81% and 100%". Quote the range, not just the %.
- **Same cases for both sides** when comparing models or prompts; use `--compare` (McNemar test). p ≥ 0.05 = could be luck.
- **Never tune on the test you report.** Fix bugs found by `cases_hard`, then report on `cases_team` + real audio/photos.
- **No AI judging AI** for things we can score exactly (type, amount, name). Anything judged by a person gets a name + date.
- **Say who wrote the test data.** Template/Claude phrases ≠ real traders. Native-speaker checks are marked `"check": "native"`.
- Speech-to-text and understanding are tested **separately** (text cases) and **together** (`--audio`), so we know which part fails.

## Public data we can use (research, 25 Sep 2026)
| Dataset | Use for | Licence |
|---|---|---|
| Google **FLEURS** (ha / ig / yo, ~350 test sentences each) | speech-to-text error rate, Whisper vs omniASR | CC-BY-4.0 |
| **Nigerian Pidgin ASR 1.0** (~4,300 clips, 10 speakers) | Pidgin speech-to-text | free with citation |
| **AfriSpeech-200** (67% Nigerian accents) | Nigerian-accented English speech | CC BY-NC-SA 4.0 |
| **NaijaVoices** (~1,800 h ig/ha/yo, casual speech) | harder, less studio-like speech | CC BY-NC-SA 4.0 (may be gated) |
| **NaijaSenti** tweets (ha/ig/yo/pcm) | real code-switched text → mine money/credit phrases | see repo |
| Yoruba handwritten character DB (12,600 tonal characters) | tone-mark reading spot check | see repo |

**Gaps (nobody has published these):** Nigerian market-talk data, Hausa/Igbo handwriting, African ledger/receipt photos.
→ Our own 20–30 notebook photos + trader voice notes (with consent, fake names) are the most valuable test data we have.

Known risks from research: Whisper collapses on Hausa (106.9% word error for whisper-tiny on FLEURS); omniASR mixes
old and standard Yoruba spelling; Yoruba counting is base-20 (ẹgbẹ̀rún, ẹgbàá), so spoken Yoruba amounts are a real risk.
Method: CheckList (Ribeiro et al., ACL 2020) for trap/invariance tests; Wilson intervals over ± normal ranges.
