# ✅ Team prep plan: 4 people, before Sunday 27 Sep

Idea **not final**: send opinions + alternatives by **Fri 9pm**; we pick ONE idea on the **Saturday call**.
Roster by **10:00 Sunday**, submit by **17:15** (deadline 17:30).

## Everyone (all 4)
- [ ] Read: `TEAM_GUIDE.md` → `README.md` → `docs/TESTING.md` → `docs/WHATSAPP.md` → `docs/RULES_CHECKLIST.md` → `docs/RESEARCH.md` → `docs/PITCH.md`
- [ ] Run the app (README → Quick start), try: *I sell 2 crates of eggs give Oga Emeka, 10,800, he go pay Monday*
- [ ] NVIDIA API key from build.nvidia.com (**never share it**)
- [ ] 5 voice notes in your language (fake names) → send to Person 4 with the text
- [ ] 1 handwritten trader-style notebook page, photographed → send to Person 4 with what it says
- [ ] **Fri 9pm:** honest opinion + 1 alternative idea + role choice
- [ ] Saturday call (time: ____) · Sunday at 8:30am, laptop + charger + phone data backup

## 1️⃣ Lead + pitch: ______
- [ ] Ask organisers: prep code allowed if disclosed? Who owns the project?
- [ ] Saturday: interview **5 traders** at a market (how they track debts, would they use a WhatsApp bot, what stops them, loans)
- [ ] Team name + roster details; draft video script + project card (`docs/PITCH.md`)
- [ ] **Sunday:** roster 9:45 (primary prize: Kredete), timekeeping, record video 15:45–16:45, **submit 17:15**

## 🔊 Voice replies (Person 2 or 4)
- [x] Sign up at **spitch.app**, get the API key → `.env` `SPITCH_API_KEY=...` → `pip install spitch` ✅ 25 samples made
- [ ] `python eval/tts_check.py` → play the samples to **native speakers** of Yoruba, Hausa, Igbo, Pidgin; score 1–5
- [ ] Any language scoring < 3 → don't demo its voice; fix wording in `tts.py` TEMPLATES if they suggest better phrasing

## 2️⃣ AI + NVIDIA Brev: ______
- [ ] Brev account; read Brev notes in `docs/RESEARCH.md`
- [x] `python check_models.py` → post results
- [x] `python eval/lang_check.py` → post language scoreboard (`docs/RESULTS.md`)
- [ ] `python eval/run_eval.py --cases eval/cases_hard.jsonl --sleep 1.5` → post summary (`docs/TESTING.md`)
- [ ] One real notebook photo through the app → post screenshot
- [ ] **Sunday:** voucher 10:15 → GPU (L4) → start omniASR download first → public app link → Brev screenshots → stop GPU when idle

## 3️⃣ WhatsApp: ______
- [ ] Meta developer app + **test number** + add 4 phones + 1 spare (`docs/WHATSAPP.md` §2)
- [ ] ✅ test number sends `hello_world` · ✅ permanent token · save IDs + App Secret privately
- [ ] Backup: 360dialog sandbox ("START" to +55 11 4673-3492)
- [ ] Saturday: ✅ webhook + tunnel test on laptop
- [ ] **Sunday:** build `whatsapp.py` (`docs/WHATSAPP.md` §5), commands, "See more" links, test from all phones by 15:30

## 4️⃣ Testing + responsible AI: ______
- [ ] 15 new test phrases in `eval/cases_team.jsonl` **without reading the code**
- [ ] Collect voice notes → `eval/audio/` (named by test id); photos → `eval/photos/` (+ .txt)
- [ ] Native speakers check `eval/cases_lang.jsonl` + Yoruba reminder
- [ ] Competitor research (Kippa, Bumpa, debt-book apps): what's different about us
- [ ] **Sunday:** run evals on Brev, fill results + Responsible AI in `docs/SUBMISSION.md`, film the phone for the video

## Checkpoints (post ✅/❌ in the group)
**Friday night:** app runs for everyone · WhatsApp hello works · model check posted · organiser answers · opinions in
**Saturday night (GO / NO-GO):** idea + roles locked · webhook works · language scores · trader interviews · test data collected
- WhatsApp works → WhatsApp + web · Meta fails, 360dialog works → 360dialog · both fail → web only, WhatsApp as "next step"
- A language scores badly → don't demo it, say so honestly

## Moved to Sunday (decided 25 Sep)
- [ ] **Voice audition** (15 min, lunch 13:00): `python eval/tts_check.py --audition` → 2–3 people pick blind
  (without seeing voice names) the voice they'd "trust with their money" per language + speed → put in `.env`
  (`TTS_VOICE_PIDGIN=…`, `TTS_SPEED=…`). Until then the defaults are used (ufoma, lucy, sade, amina, ngozi, speed 1.0).
- [ ] **Native-speaker scores** (5 min per language): play `eval/tts_samples/` to a Yoruba, Hausa, Igbo, Pidgin speaker
  (another team or a volunteer) → `scores.txt`. Any language < 3 → no voice for it in the demo video.

## Before Sunday (must, ~20 min)
- [ ] `.env` model order: `LLM_MODELS=nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3-super-120b-a12b,google/gemma-4-31b-it`
  and `VISION_MODELS=meta/llama-3.2-11b-vision-instruct,google/gemma-4-31b-it` (gemma times out; see `docs/RESULTS.md`)
- [ ] WhatsApp: 5 phones registered on the Meta test number (team + 1 spare for a judge)
- [ ] Organisers: is pre-event code allowed if disclosed? Who owns the project? Is using NVIDIA's cloud models
  (build.nvidia.com) alongside Brev OK, or must all AI run on Brev?

## Sunday checks (in the build sprints)
- [ ] `python eval/test_guards.py` · `python eval/test_askbook.py` · `run_eval.py --cases eval/cases_team.jsonl` (team phrases)
- [ ] Real handwritten notebook page through Snap your book → `eval/photos/hand1_mixed.jpg` + `.txt`
- [ ] Try in the app: "I collect 5 carton indomie from Oga Emeka on credit, 60k, I go pay am Monday" · Who I owe ·
  Ask my book by voice (English + one local language) · 📒 My year so far
- [ ] `python check_models.py` on Brev (is gemma back?)
- [ ] **Speech: Spitch vs our GPU (Whisper + omniASR)?** Same team voice notes (`eval/audio/<id>.m4a`), three runs:
  `python eval/run_eval.py --cases eval/cases_lang.jsonl --audio eval/audio --asr local` · `--asr spitch` ·
  `--asr spitch-local`. Compare "heard vs really said" per language + ALL FIELDS (+ `--compare`). Pick per language.
  Trade-offs if Spitch wins: voice leaves our server (to a Nigerian company, say so in Responsible AI); Brev then
  does less speech work → Brev as the main brain (below) matters more for the Brev requirement.
- [ ] **Default (decided 25 Sep): everything on Brev.** `.env` on the Brev box:
  `LOCAL_LLM_URL=http://localhost:8001/v1` and
  `LLM_MODELS=local,nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3-super-120b-a12b` (our GPU first, cloud = backup).
  Note: running the APP on Brev is not enough; without `local` first the understanding still goes to NVIDIA's cloud.
- [ ] **Check the default is good enough:** Start the Brev model (README → "Backup AI brain"), run
  `LLM_MODELS=local python eval/run_eval.py --cases eval/cases_hard.jsonl`, then `--compare` with
  `eval/results/cases_hard-ai-0925-0736.json` (cloud run). Same score → keep the default. Clearly worse (esp. Yoruba/Hausa/Igbo) → put the cloud first, Brev second,
  and say why in the submission.

## How we use the Brev credits (decided 25 Sep)
One GPU instance for the day (L4 24 GB; an L40S 48 GB if credits allow the backup AI brain too):
1. **Speech-to-text (must):** Whisper (English/Pidgin) + Meta omniASR (Yoruba/Hausa/Igbo) on our GPU. omniASR needs
   ~10 GB GPU memory, so a laptop can't run it. Pitch: voice notes never go to an outside speech service.
2. **Host the demo:** web app + WhatsApp webhook on the same instance; public link via Gradio share (Brev links need login).
3. **Backup AI brain (recommended):** a small open model (~8B) served on the GPU (vLLM, OpenAI-compatible) as the LAST
   fallback after nemotron-3-ultra/super. Reason: the cloud models timed out 53/211 times on 25 Sep. Chain = cloud →
   our GPU → offline rules, so the demo never stalls. ✅ built 25 Sep: `LOCAL_LLM_URL` (README → "Backup AI brain"); tested with fake servers, not yet on Brev.
4. **Run the evals on Brev:** hard test set + real voice notes → timing numbers for the submission.
5. **Proof for judges (required):** Brev console screenshots (GPU, hours, cost); stretch: a **Brev Launchable**
   (one-click template to rerun our demo).
- Save credits: start the omniASR download first; **stop the instance at lunch and whenever idle.**

## Sunday timeline
8:30 check-in · 9:45 roster · 10:15 Brev voucher · 11:15–13:00 build · 11:30 mentor · 13:00 lunch + voice audition (stop idle GPU) ·
14:00–15:30 build + phone tests · 15:30 checkpoint · 15:45–16:45 video · 16:45–17:15 submission · **17:15 SUBMIT**

## Rules
Max 5 per team, one team each · must use Brev credits and explain how · prototype + 90s video + project card + AI/tools
disclosure · disclose everything (incl. Claude, demo data) · fake names only · never share keys/tokens
