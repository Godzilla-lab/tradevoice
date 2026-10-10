# TradeVoice: NAIC form answers (copy and paste)

Every answer is under the form's 1,500-character limit. **Fill in each [bracket] before submitting.** The pilot numbers
come from the validation report (`sudo bash /opt/tradevoice/app/deploy/server/validation_report.sh`).

## Describe exactly how your artefact integrates with N-ATLAS
```
TradeVoice (PS2 Voice-First Access) runs the official N-ATLaS open weights (Hugging Face NCAIR1) on our own Modal servers, called from our FastAPI server on AWS (tradevoice.duckdns.org).

1. ASR: each voice note goes to the N-ATLaS speech model for the trader's language: Yoruba-ASR, Hausa-ASR, Igbo-ASR, or NigerianAccentedEnglish for English and Pidgin. Audio is 16 kHz mono, and the trader's customer names are passed as hints. Traders mix languages, so Yoruba, Hausa and Igbo notes are also heard by NigerianAccentedEnglish.

2. Model: NCAIR1/N-ATLaS (Llama-3 8B) on vLLM, one L4 GPU, OpenAI-compatible API, with the card's settings (temperature 0.1, repetition penalty 1.12, Llama-3.1 template with today's date). It merges the two hearings and turns the words into a bookkeeping record as JSON (guided decoding against our schema, 6 worked examples). It also answers Yoruba, Hausa and Igbo questions first. In live talk, Intron's streaming speech hears for speed, and N-ATLaS still writes every record.

3. Code, never the AI, does every sum and checks each record (the amount must have been said, names kept as in the book). The trader confirms on a check card before anything is saved.

N-ATLaS is first for every record. NVIDIA models and Intron step in only if it is down. Every answer is logged with the model that gave it, so the N-ATLaS share is measured.
Code: src/llm.py, extract.py, asr.py, hearing.py; deploy/modal_natlas.py, modal_asr.py.
```

## N-ATLAS API key / access reference (if issued)
```
No API key was issued to us. We use the open N-ATLaS weights (NCAIR1/N-ATLaS, Yoruba-ASR, Hausa-ASR, Igbo-ASR, NigerianAccentedEnglish) from Hugging Face, under the N-ATLaS Terms of Use v1.0 accepted on our team's Hugging Face account, and serve them ourselves on Modal. Live app: https://tradevoice.duckdns.org/app. For the integration check, we can give evaluators private access to our team dashboard (N-ATLaS share of answers, step times) on request.
```

## Evidence artefacts demonstrating integration (file)
Upload `TradeVoice-NATLAS-evidence.pdf`. It holds:
- the exact API requests;
- the benchmark scripts and results;
- the test log;
- the live run, once the evidence command has been run on the server and its output added.

## How was the artefact tested with real users, real data, or live benchmarks?
```
1. Live benchmark on the real stack: 1,000 bookkeeping sentences, 200 each in English, Pidgin, Yoruba, Hausa and Igbo. They ran through N-ATLaS on our Modal GPU and through Meta-Llama-3-8B-Instruct, the model N-ATLaS was built from, with the same prompt, examples and GPU and no backups. A sentence counts as right only if the record's type, amount and customer are all right. We also ran 100 newer sentences written from research on how traders talk (never used for tuning) and 203 tool-call sentences.

2. Automated tests: 1,030 server checks and 80 real-browser checks (sign-up, voice notes, live talk, check card, save, reminders, Telegram, and what happens when N-ATLaS is down), run before every release.

3. Real users: a pilot on the live app (web and Telegram) from [dates], with [N] traders in [markets, cities] speaking [languages], plus [N] external testers outside the team. Traders agreed to the terms in the app. Voice notes are kept only for those who said yes. The live app logs each conversation's channel, language, which model answered and step times, never words, names or amounts. The validation report is built from that log.
```

## Validation evidence (file)
Upload the validation report PDF. On the server, run `validation_report.sh`. Copy `validation.html` to your Mac and
open it in Chrome. Then choose Print and Save as PDF.

## Key results or feedback from validation
```
Benchmark, 1,000 sentences: N-ATLaS alone got 69% right; Llama-3-8B, the model it was built from, got 51%. The biggest gains were Hausa (67% vs 27%) and amounts said in Nigerian number words (62% vs 12%). N-ATLaS wrote a wrong amount 68 times; Llama did 170 times. With our code checks, the full app wrote 0 wrong amounts. Median time on a warm GPU: about 5 s.

Honest limit: the full app scored 100% on those sentences, but our rules were built on similar ones. On 100 newer research-written sentences it scored 69% before fixes. That showed what to guard against: copied example prices, balances taken as payments, re-spelled customer names. Each now has a guard and a test.

Pilot (live log): [N] traders, [N] conversations, [N] records saved. N-ATLaS answered [X]% of AI requests and heard [X]% of voice notes. [One trader quote, with permission.]

What we changed from testing: live talk shows words while you speak and replies sooner; simpler sign-up; Telegram login; asking again when an amount is unclear.

Still to do: native speakers have not yet checked the test sentences, and real noisy-market voice notes are not yet measured. Yoruba is N-ATLaS's weakest language on its own card, so spoken Yoruba replies use reviewed templates.
```

## Who benefits from this build, and how many people could it reach?
```
Market traders, many of them women, who sell on credit and keep their book in a notebook or in their head. Many read little or prefer to speak Yoruba, Hausa, Igbo or Pidgin. With TradeVoice they say a sale the way they would tell a friend, and get a book they can trust: who owes them, how much, and when.

How it helps them:
- fewer forgotten debts;
- polite reminders they send themselves;
- a 30-day lender report they choose to share, built by code from their own book. Lenders ask for proof of trade, and most traders have none.

Their customers get clear, fair reminders. Cooperatives, microfinance banks and market associations get members with real records.

Reach: Nigeria has about 39.6 million MSMEs (SMEDAN/NBS 2021), giving 87.9% of jobs, and the IFC puts the MSME finance gap at $32.2 billion. TradeVoice works on any phone browser and on Telegram, with no app to install; WhatsApp is built and ready.

Today the N-ATLaS licence allows up to 1,000 active users a month. Beyond that we will get the commercial licence from Awarri and the Ministry. A realistic first goal is 10,000 traders in Lagos, Kano and Onitsha markets within a year, through market associations and cooperatives.
```
The 10,000-trader goal is a suggestion. Change it to your team's own target.

## What is your plan to sustain or scale the build beyond the challenge?
```
Product: free for traders to record sales and debts by voice. We will add small paid extras (lender reports, payment links, multi-device), and charge cooperatives and microfinance banks for consented, code-built trading summaries that help them lend. Before charging anyone, we will agree commercial terms with Awarri and the Ministry, as the N-ATLaS licence requires.

Distribution: market associations (iyaloja, union leaders), cooperatives and microfinance partners onboard traders in person. Telegram now, and WhatsApp as soon as Meta API access is approved (the bot is built and tested).

Cost: the N-ATLaS models scale to zero on Modal and stay awake only in market hours. One small AWS server runs the app. If Modal is down, NVIDIA models and Intron keep traders served while N-ATLaS recovers.

Quality: native speakers will review Yoruba, Hausa and Igbo replies. We will fine-tune the N-ATLaS speech models on voice notes from traders who opted in, and release any derivative under the same N-ATLaS terms. We will measure accuracy per language in public.

Team: the build stays open in our repository, with 1,000+ automated checks and a live dashboard of N-ATLaS use.
```

## Are you seeking support for this build?
```
Yes. We are seeking:
1. Compute credits for N-ATLaS (GPU for the language model, CPU/GPU for the four speech models) through the pilot and the first 10,000 traders.
2. Commercial-use terms for N-ATLaS with Awarri and the Ministry, so we can serve more than 1,000 active users and charge for extras.
3. Introductions to microfinance banks, cooperatives and market associations (Lagos, Kano, Onitsha) for pilots and the consented lender report.
4. Native-speaker reviewers for Yoruba, Hausa and Igbo.
5. Help with WhatsApp Business API access.
We have no funding and no institutional partner today. [Edit if this has changed.]
```

## What support would help your team most during the acceleration phase?
Tick:
- Compute credits
- Technical mentorship
- Sector/domain expert mentorship
- Investor or partner introductions

## The rest
"How did you hear about the NAIC" is your choice. Tick Yes on the four confirmations.

N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, and powered by Awarri Technologies.
