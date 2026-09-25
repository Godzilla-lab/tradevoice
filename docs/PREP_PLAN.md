# ✅ Team prep plan: 4 people, before Sunday 27 Sep

Idea **not final**: send opinions + alternatives by **Fri 9pm**; we pick ONE idea on the **Saturday call**.
Roster by **10:00 Sunday**, submit by **17:15** (deadline 17:30).

## Everyone (all 4)
- [ ] Read: `TEAM_GUIDE.md` → `README.md` → `docs/WHATSAPP.md` → `docs/RULES_CHECKLIST.md` → `docs/RESEARCH.md` → `docs/PITCH.md`
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
- [ ] Sign up at **spitch.app**, get the API key → `.env` `SPITCH_API_KEY=...` → `pip install spitch`
- [ ] `python eval/tts_check.py` → play the samples to **native speakers** of Yoruba, Hausa, Igbo, Pidgin; score 1–5
- [ ] Any language scoring < 3 → don't demo its voice; fix wording in `tts.py` TEMPLATES if they suggest better phrasing

## 2️⃣ AI + NVIDIA Brev: ______
- [ ] Brev account; read Brev notes in `docs/RESEARCH.md`
- [ ] `python check_models.py` → post results
- [ ] `python eval/lang_check.py` → post language scoreboard
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

## Sunday timeline
8:30 check-in · 9:45 roster · 10:15 Brev voucher · 11:15–13:00 build · 11:30 mentor · 13:00 lunch (stop idle GPU) ·
14:00–15:30 build + phone tests · 15:30 checkpoint · 15:45–16:45 video · 16:45–17:15 submission · **17:15 SUBMIT**

## Rules
Max 5 per team, one team each · must use Brev credits and explain how · prototype + 90s video + project card + AI/tools
disclosure · disclose everything (incl. Claude, demo data) · fake names only · never share keys/tokens
