# 👋 Team Guide: read this first

**Event:** Come Build with AI · Sunday 27 Sep 2026 · 9:00 AM – 8:00 PM (Nigeria time = Tunis time, UTC+1)
**Project:** TradeVoice: voice and photo bookkeeping for Nigerian market traders
**Our goal:** top 3 in Nigeria + Kredete Financial Inclusion Award ($500) + tick any other award we fit.

---

## 1. The idea in 30 seconds
A trader at Balogun or Mile 12 sells rice on credit to Mama Tunde and just **says it**, or **snaps a photo of their
notebook**. TradeVoice turns that into clean records, shows **who owes them and who is late**, writes a **polite
WhatsApp reminder in Pidgin/English/Yoruba**, **forecasts next week's cash**, and builds a **record score + statement**
they can take to a lender. The speech AI runs on our own **NVIDIA Brev GPU**, so traders' voices aren't sent to a third-party speech service.

Try it: `python seed_demo.py --wipe && python app.py` (see README Quick start).

## 2. Roles (fill in names)
| Role | Person | Owns |
|---|---|---|
| 🧑‍✈️ **Lead / submitter** | ______ | Roster (by 10:00), timekeeping, final submission (by 17:30), prize dropdown/checkboxes |
| ⚙️ **Brev + AI engineer** | ______ | Brev instance, Whisper on GPU, NVIDIA API keys, public demo link, Brev screenshots + cost |
| 🧪 **Testing + data** | ______ | Voice-note recordings, new test phrases, `run_eval.py` results, failure-mode list |
| 🎨 **Product + demo** | ______ | App polish, demo script, 90-second video, project card |
| 🗣️ **Voice + responsible AI** | ______ | Yoruba/Pidgin wording check, privacy/consent/bias section, the talking in the video |

(Fewer than 5 people? Merge roles: Lead + Product, Engineer + Testing.)

## 3. BEFORE the event (Thu–Sat)
- [ ] Everyone: clone the repo and run it (README → Quick start). Tell the group if anything breaks.
- [ ] Everyone: make an account at **build.nvidia.com** → generate an API key (`nvapi-...`). Test it: put it in `.env`
      and run `python check_models.py`. It shows which NVIDIA models work (one is being deprecated); then
      `python eval/run_eval.py`. The engine line should say `llm:<model>`, not `rules`.
- [ ] Engineer: make a **Brev** account and read the Brev getting-started guide + `docs/RESEARCH.md` (Brev section). Do NOT start paid GPUs yet;
      the event vouchers come at 10:15.
- [ ] Testing: **write 15 NEW test phrases** (without looking at `extract.py`) in `eval/cases_team.jsonl`, same format
      as `eval/cases.jsonl` but with ids `t01`, `t02`…. Run: `python eval/run_eval.py --cases eval/cases_team.jsonl`. Mix English, Pidgin, big and small amounts, "45k", "N12,500", names, dates.
- [ ] Testing: **record all 35 phrases as voice notes** (WhatsApp voice notes are fine, export as .m4a/.ogg) named
      by case id (`01.m4a`… and `t01.m4a`…) into `eval/audio/`. Run with `--audio eval/audio`. Use at least 3 different voices; record 5 with market noise.
- [ ] Testing: write **3 fake notebook pages** by hand (like a real trader: shorthand, "bal", "cr", crossed-out
      lines) and photograph them. Keep them for the photo test and the video.
- [ ] Voice: have a Yoruba speaker check the Yoruba reminder in `insights.py` (`TEMPLATES`). Fix the wording if needed.
- [ ] Product: rehearse the demo flow (Section 6) until it takes under 60 seconds.
- [ ] Lead: pick the **team name**. Fill in `docs/SUBMISSION.md` team section.

⚠️ **Rule:** the judges score what we build *on the day*. Prep = setup, tests, data, rehearsal. Save real feature work
(Brev deployment, tuning, test results, video) for Sunday and **commit often on Sunday** so the history shows it.

## 4. ON the day: timeline
| Time | Everyone does | Owner |
|---|---|---|
| 08:30 | Check in, join the event channels | All |
| 09:45–10:00 | **Submit final roster form** (primary prize: *Kredete Financial Inclusion Award*) | Lead |
| 10:15 | Get the Brev voucher → activate | Engineer |
| 10:15–11:15 | Brev workshop. Create GPU instance, clone repo, install, run Whisper once, start `GRADIO_SHARE=1 python app.py` | Engineer |
| 11:15–11:30 | Sprint 1: team checks the public link works on phones | All |
| 11:30 | Mentor checkpoint: show the live link + ask about Brev usage expectations | Lead |
| 11:45–13:00 | Sprint 2: real voice notes through Brev; fix errors; tune prompts; photo reading working | Engineer, Testing |
| 13:00 | Lunch (**stop or keep Brev running? stop if idle > 30 min**) | Engineer |
| 13:45 | Submission briefing: note exactly what they want | Lead |
| 14:00–15:30 | Sprint 3: run `run_eval.py` on new phrases + audio; fill results table; polish UI; screenshot Brev | Testing, Product |
| 15:30 | Checkpoint: every link opens on a phone not on our Wi-Fi | Lead |
| 15:45–16:45 | **Record the 90-second video** (docs/PITCH.md). Write project card | Product, Voice |
| 16:45–17:15 | Fill disclosure + Brev explanation + test results (docs/SUBMISSION.md) | Lead, Engineer |
| **17:15** | **SUBMIT** (deadline 17:30; don't wait for the last minute) | Lead |
| 17:30 | Keep the confirmation. **Stop the Brev instance** only after the judges are done if they need the live link | Engineer |
| 19:15 | If we're top 3: live demo (Section 6) | Product |

## 5. How we score points (100)
| Criterion | Pts | How TradeVoice earns it | Owner |
|---|---|---|---|
| Problem + user value | 20 | Real, local pain: 94.8% of SMEs have bank accounts but only 20.2% have loans (weak records). One clear user: market trader. Stats in `docs/RESEARCH.md` | Voice |
| Functional execution | 20 | Live public link; voice → entry → debtors works end to end; photo → table works | Engineer |
| AI quality + NVIDIA Brev | 20 | Whisper **self-hosted on Brev GPU** (privacy + cost reason), NVIDIA Nemotron text + vision models, automatic model fallback; explain *why* each. Bonus: Brev Launchable | Engineer |
| Testing + reliability | 15 | Accuracy on new phrases + voice notes + photos; latency; fallback to offline rules; amount cross-check; confirm step | Testing |
| Experience + demo | 15 | 90-second video, Pidgin voice note, red "overdue" flag, WhatsApp reminder moment | Product |
| Responsible AI + data | 10 | Consent, audio/photo deleted, human confirms, AI never does the maths, score is transparent and "not a loan decision", bias note on accents/languages | Voice |

## 6. The demo flow (≤ 60 seconds of screen time)
1. **Speak** tab: play a Pidgin voice note → fields fill in → **credit check warning** for Oga Emeka → Confirm.
2. **Snap your book**: photo of the handwritten page → table of 5 entries → Save all.
3. **Who owes me**: red "18 days late" → Pidgin reminder → **Open in WhatsApp**.
4. **Insights**: "Next 7 days ≈ ₦620k, Saturday busiest, restock rice".
5. **Ask my book**: "How much Mama Tunde owe me?"
6. **Credit profile**: score 82/100 → download statement.

## 7. Rules we must not break
See [`docs/RULES_CHECKLIST.md`](docs/RULES_CHECKLIST.md). The big ones:
- Team of up to 5. Everyone on **one team only**. Roster by **10:00**.
- **Use our Brev credits in the project** and **explain how** in the submission.
- Submit **prototype + 90-second video + project card + AI/tools disclosure** by **17:30**.
- **Disclose everything:** models, APIs, open-source code, Claude as coding assistant, synthetic demo data.
- **Don't** present pre-built work as built on the day. **Don't** use real people's financial data without consent.

## 8. If something breaks
| Problem | Do this |
|---|---|
| NVIDIA API down / slow | The app falls back to offline rules automatically. Say so in the video: that's a reliability feature |
| Whisper won't start on GPU | cuDNN fix in README step 3. Still stuck: `ASR_MODEL=small` or ask the Brev mentor. Last resort: type entries |
| Photo reading fails | Check the key; try a smaller/clearer photo; you can paste lines into the box by hand |
| Brev credits running low | Stop the instance; use a smaller GPU; keep only Whisper on Brev |
| Gradio share link dies | Restart `app.py`, update the link in the submission |
| Git conflict | Don't panic: the Engineer merges; everyone else works on docs/data |
