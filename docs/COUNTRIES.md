# 🌍 Country packs: money, tax and culture (researched 25 Sep 2026)

For the other 7 event countries. ⚠️ Researched by Claude from web search summaries (official tax offices, Deloitte,
Bowmans, KRA, ZATCA, SAMA, CBK, BCEAO…); **not checked by local experts**. Tax rules change with every finance law.
**Rule (same as Nigeria): no tax figures in the app until a local expert checks them.** What is already in the app:
currency, languages, local titles and counting traps (`country.py`, `COUNTRY=` in `.env`).

## ⚠️ The money-reading traps (built into the AI hint)
| Country | Trap | Example |
|---|---|---|
| Morocco | prices counted in **ryal**: 20 ryal = 1 DH; "million" in centimes | "alf ryal" = **50 DH**; "1 million" = 10,000 DH |
| Algeria | counted in **centimes** | "1 million" = **10,000 DA** |
| Tunisia | 1 DT = **1,000 millimes**, 3 decimals | "three thousand" may mean 3 DT |
| Senegal | Wolof counts in **dërëm** (×5), unit often implied | "100" may mean 500 FCFA |
| Kenya | Sheng slang | bob = shillings, soo = 100, punch = 500, thao = 1,000 |
| Côte d'Ivoire | Nouchi slang | barre / krika = 1,000 FCFA, gbon = 5,000 |
The AI is told each country's rule and to say so in its note when unsure → the trader confirms.
Sources: [Moroccan rial](https://en.wikipedia.org/wiki/Moroccan_rial), [Algerian dinar](https://en.wikipedia.org/wiki/Algerian_dinar),
[Tunisian dinar](https://en.wikipedia.org/wiki/Tunisian_dinar), [Janga Wolof](https://jangawolof.org/2008/08/28/all-about-senegalese-money/),
[Sheng](https://en.wikipedia.org/wiki/Sheng_slang), [Nouchi](https://fr.wikiversity.org/wiki/Argots_%C3%A0_base_fran%C3%A7aise/Nouchi).

## Summary table
| Country | Currency | Languages | Small-trader tax regime (verify!) | Mobile money | Savings group | Week |
|---|---|---|---|---|---|---|
| Morocco | MAD "DH" | Darija, Amazigh, French | **CPU**: ≤2M DH goods / ≤500k services; deemed profit × 10% + AMO health cover | low (~12%), cash-heavy | daret | Sat–Sun [unverified] |
| Algeria | DZD "DA" | Darja, Tamazight, French | **IFU**: ceiling 8M DA (2025 Finance Law; one source says 15M), 5% goods / 12% other, min 30k DA; auto-entrepreneur 0.5% | BaridiMob/CCP, Edahabia | jam'iya [unverified] | **Fri–Sat** |
| Tunisia | TND "DT" | Derja, French | **In flux**: 2026 optional forfait ≤100k DT, fixed 4–5k DT/yr; e-invoicing (El Fatoora) widening | D17, Flouci | [unverified] | Sat–Sun [unverified] |
| Senegal | XOF "FCFA" | Wolof, French | **CGU**: ≤50M goods / 25M services; 2% trade / 5% services; min 25,000 F | **Wave >50%**, Orange Money | tontine (~60% of urban households) | Sat–Sun [unverified] |
| Côte d'Ivoire | XOF "FCFA" | French, Dioula, Nouchi | **Entreprenant**: ≤5M communal tax; 5–50M TEE 4% trade / 5% services, monthly; **FNE e-invoice** mandatory | Orange, MTN, Moov, Wave | tontine | Sat–Sun [unverified] |
| Kenya | KES "KSh" | Swahili, English, Sheng | **Turnover Tax 1.5%** (KES 1–25M), monthly by the 20th; **eTIMS** e-invoices (from 2026, costs without eTIMS invoice not deductible) | **M-Pesa ~90%** | chama | Sat–Sun |
| Saudi Arabia | SAR | Arabic (+ expat languages) | **VAT 15%** (register above SAR 375k); **zakat 2.5%**; **Fatoora** e-invoicing (≥187.5k by 1 Feb 2027) | mada (85% of retail payments electronic), STC Bank | jam'iya [unverified] | **Fri–Sat** |

## Rules the app must respect
- **No interest / riba framing** in Saudi Arabia (and by default in North Africa): "amount due", never add interest.
  West Africa (UMOA): usury cap 24% (microfinance), 14% (banks) from 1 Jun 2026.
- **No debt-shaming**: Kenya criminalises contacting a borrower's contacts (CBK digital credit rules); SAMA caps
  collection calls. Our reminders: private, polite, sent by the trader to their own customer only.
- **An app record is NOT an official invoice** (eTIMS, FNE, El Fatoora, Fatoora). Say so.
- **Data protection** law in each country (declare/register before real users): Morocco CNDP (Law 09-08), Algeria ANPDP
  (Law 18-07), Tunisia INPDP, Senegal CDP, Côte d'Ivoire ARTCI, Kenya ODPC (DPA 2019), Saudi SDAIA (PDPL).
- Saudi **anti-concealment (tasattur)**: never help run a business under someone else's name.

## The app MAY say (with source + "as of" date)
The regime's name and who runs it ("Kenya: businesses with KES 1–25M turnover generally fall under Turnover Tax:
check with KRA"); published deadlines; neutral totals from the book; "your records help with your CPU / CGU / TEE
declaration and with lenders"; a confirmation when an amount could be in ryal/centimes/millimes/dërëm.
## The app must NOT say
"You owe X tax" / "you are exempt"; that a record replaces an official e-invoice; anything with interest in SA;
anything enabling debt-shaming; lending or credit scores in its own name without a licence.

## Key sources
[DGI Morocco CPU guide](https://ecoactu.ma/contribution-professionnelle-unique-cpu-dgi-guide/) ·
[Algeria IFU 2025](https://www.tsa-algerie.com/vehicules-de-moins-de-3-ans-ifu-la-loi-de-finances-2025-promulguee/) ·
[Tunisia forfait 2026](https://finco.tn/blog/regime-forfaitaire-optionnel-2026-tunisie) ·
[Senegal CGU (DGID)](http://www.impotsetdomaines.gouv.sn/fr/faire-une-declaration-pour-la-contribution-globale-unique) ·
[Côte d'Ivoire entreprenant](https://blog.ivoire-juriste.com/2025/12/tout-savoir-sur-le-regime-de-lentreprenant-en-cote-divoire-taxe-communale-et-taxe-detat.html) ·
[Kenya TOT (KRA)](https://www.kra.go.ke/individual/filing-paying/types-of-taxes/turnover-tax-tot) ·
[Kenya 2026 outlook (CDH)](https://www.cliffedekkerhofmeyr.com/en/news/publications/2026/Kenya/Tax-Exchange-Control/tax-and-exchange-control-alert-27-january-Tax-outlook-2026-Navigating-Kenyas-evolving-tax-landscape) ·
[ZATCA zakat](https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Zakat%20General%20Simplified%20Guideline.pdf) ·
[ZATCA Fatoora wave 25](https://www.vatupdate.com/2026/07/27/zatca-announces-wave-25-of-e-invoicing-threshold-halved-to-sar-187500-integration-deadline-1-february-2027/) ·
[UMOA usury cap](https://www.agenceecofin.com/actualites-finance/3004-138022-umoa-le-taux-de-l-usure-pour-les-institutions-de-microfinance-passe-a-24-en-juin) ·
[SAMA debt collection](https://rulebook.sama.gov.sa/en/debt-collection-regulations-and-procedures-individual-customers-0).
**Verify first:** Tunisia's final 2026 forfait, Algeria's IFU ceiling, any Senegal CGU change, Saudi micro-trader zakat,
local titles (Côte d'Ivoire, Kenya, Algeria, Saudi), Ramadan trading hours.
