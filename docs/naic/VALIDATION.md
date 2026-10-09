# TradeVoice: real-world validation

NAIC 2026, Innovation and Enterprise track, PS2 Voice-First Access. Live build: https://tradevoice.duckdns.org

This document has two parts. The **numbers** come from the live app's own log, as one page with charts. The **people part** (who tested it, what they said) comes from the team. Together they make the "Real-world validation" PDF.

## 1. The numbers: make the report (5 minutes)

On the server (after `ssh`):
```
sudo bash /opt/tradevoice/app/deploy/server/validation_report.sh
```
It saves `validation.html` in your home folder. For another window of days, add `--start 2026-10-06 --end 2026-10-17`.

On your Mac:
```
scp -i ~/Downloads/tradevoice-key.pem ubuntu@54.170.27.207:validation.html ~/Desktop/
```
Then open it in Chrome and choose Print, then Save as PDF.

**What the report shows** (counts only; the log never holds names, phone numbers, amounts or words; the team's own phones in `TEAM_PHONES` are left out):
- traders who used it and new sign-ups;
- conversations per day, where they happened (live talk, Ask chat, voice question, Telegram) and in which language;
- records saved, customers added, voice notes heard and notebook photos read;
- which AI understood them: the share answered by N-ATLaS, and how often a backup answered;
- which model heard their voice;
- the funnel: opened the app, signed up, saved a record, came back another day;
- how long each step took;
- what went wrong, and what we changed during the pilot.

## 2. How the pilot ran

[Fill in: dates, where (markets, cities), how traders were found, how many, which languages they used.]

**Consent:**
- Each trader agreed to the terms in the app before anything was processed.
- A separate question asked whether TradeVoice may keep their voice notes, photos and chats to improve it. Only traders who said yes had anything kept.
- [Fill in: how consent was explained in person, and in which language.]

**Channels:**
- **The web app** (on any phone browser) was the main way in.
- **Telegram** was offered to traders who use it.
- **WhatsApp:** the bot is built and tested, but was not live, because the team could not get WhatsApp Business API access in time.

## 3. External beta testers (at least 2, outside the team)

| Name | Role | Date | What they tested | Confirmation |
|---|---|---|---|---|
| [name] | [e.g. shop owner, Ikeja] | [date] | [e.g. recorded sales by voice in Yorùbá, asked who owes them] | [signed note / voice note / message, kept privately] |
| [name] | [role] | [date] | [what] | [how] |

Keep the confirmations themselves out of GitHub. They contain personal details.

## 4. What traders said

[3 to 5 short quotes, with permission, first name or role only. For example: "Market trader, Hausa: ..."]

## 5. What went wrong and what we fixed

From the report's last two sections, plus anything traders told you. Be plain about what still doesn't work well.

[Fill in.]

## 6. Honest limits of this evidence

- **Size and selection:** the pilot was small and short, and the traders were found through the team's contacts.
- **Language check:** the Yorùbá, Hausa and Igbo test sentences in `eval/` were written by the team, not checked by native speakers.
- **Voice in noise:** the before-and-after test on real market notes is not done yet. The script is ready (`deploy/server/speech_ab.sh`).

N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, and powered by Awarri Technologies.
