# 🌍 Languages beyond Nigeria (researched 25 Sep 2026)

The event runs in **8 countries**: Tunisia, Algeria, Morocco, Senegal, Côte d'Ivoire, Nigeria, Kenya, Saudi Arabia.
Juries rank **per country**, so our demo stays Nigerian first. But "same engine, more languages" is a strong
growth story (Kredete works in 30+ African countries).

## Which languages (not all of them: the most important)
| Language | Speakers in Africa | Countries in this event | Status |
|---|---|---|---|
| English, Pidgin, Yoruba, Hausa, Igbo | Hausa ~94M, Yoruba ~45M… | Nigeria (+ English: Kenya, Saudi) | ✅ built + tested |
| **French** | ~170M | Tunisia, Algeria, Morocco, Senegal, Côte d'Ivoire | 🧪 text test ready |
| **Arabic** (standard + North African Darija) | 300M+ (most native speakers) | Tunisia, Algeria, Morocco, Saudi Arabia | 🧪 text test ready |
| **Swahili** | 80M native, 150–200M total (most widely spoken African language) | Kenya (+ East Africa) | 🧪 text test ready |
With English, these cover **all 8 countries**. Sources: [Pangea](https://www.pangea.global/blog/10-most-popular-african-languages/),
[Mars Translation](https://www.marstranslation.com/blog/which-languages-are-the-most-widely-spoken-in-africa).
Not now: Wolof (Senegal), Dioula (Côte d'Ivoire), Tamazight, Oromo, Amharic… Add them later, one language pack at a time.

## What "supporting a language" means (4 layers)
| Layer | Nigeria today | French / Arabic / Swahili |
|---|---|---|
| **Understand** the note (AI) | ✅ | Prompt now says so; `eval/cases_africa.jsonl` (22 phrases: French, Swahili, standard Arabic, Moroccan + Tunisian Darija typed the WhatsApp way, e.g. "Bi3t … b 450 dirham") |
| **Hear** (speech-to-text) | Whisper / omniASR / Spitch | Whisper handles French/Arabic/Swahili; dialect Darija is harder. Intron covers 57 African languages [check which]. Needs real recordings. |
| **Speak** replies (voice) | Spitch | Spitch doesn't cover these; needs another voice engine (MMS-TTS has Swahili/Arabic [unverified]) |
| **Money** | ₦ | ✅ `COUNTRY=KE/SN/CI/MA/DZ/TN/SA` in `.env` switches currency everywhere (screens, statement, voice replies, Ask my book, AI hint): KSh, FCFA, DH, DA, DT, SAR (`country.py`) |

## Test it (Mac, with the AI)
```
python3 eval/run_eval.py --cases eval/cases_africa.jsonl --sleep 1.5
```
Offline rules score 23% (they only know Nigerian keywords): the AI does the real work here.
Our guards were checked not to spoil correct answers in these languages (22/22).
⚠️ Phrases written by Claude, not native speakers: have French/Arabic/Swahili speakers (other GOMYCODE countries on
the day?) check them and write their own.

## Pitch line
*"Built for Nigeria first. The same engine already understands French, Arabic and Swahili notes in our tests. Each new
country is a language pack: voice, words, currency. That's every country in this hackathon, and Kredete's 30+
markets."* (Only say "understands" after the AI test above passes.)

## Country packs (`country.py`)
Currency + format, spoken currency name, default languages, savings-group and mobile-money names, and customer titles
(Tantie/Tonton, Hajja, Lalla, Khalti, Mzee, Bibi…) per country. Tax/finance facts per country: `docs/COUNTRIES.md`
(research in progress), shown in the app only after a local expert checks them, the same rule as Nigeria.

## Is WhatsApp the right front door everywhere? (25 Sep)
| Country | WhatsApp | Note |
|---|---|---|
| Kenya | ✅ 97% of internet users | highest |
| Nigeria | ✅ ~95–98% of internet users (~51M) | |
| Morocco | ✅ ~19M users | one of Africa's largest bases |
| Saudi Arabia | ✅ ~75% of nationals (Gulf/MENA survey) | |
| Senegal, Côte d'Ivoire | ✅ likely high [no exact figure found] | West Africa ~90%+ (Ghana 92%) |
| **Algeria, Tunisia** | ⚠️ **Facebook Messenger leads** (Similarweb 2023) | add a Messenger front door later (same Meta platform, same engine) |
Sources: [Yazi: WhatsApp penetration in Africa](https://www.askyazi.com/articles/whatsapp-penetration-across-africa-statistics-by-country),
[Rasayel: WhatsApp statistics](https://learn.rasayel.io/en/blog/whatsapp-user-statistics/),
[Similarweb: messaging apps by country](https://www.similarweb.com/blog/research-ru/market-research-ru/worldwide-messaging-apps/).
