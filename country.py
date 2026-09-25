"""Country pack: currency, languages and local terms, chosen with COUNTRY in .env (default NG).

Only safe, factual settings live here. Tax/finance facts per country are in docs/COUNTRIES.md and are NOT shown in
the app until a local expert checks them (same rule as Nigeria, docs/FINANCE_RESEARCH.md).
⚠️ Terms (honorifics, savings groups) are from research, not native speakers: check them.
"""
import os

PACKS = {
    "NG": {"name": "Nigeria", "currency": "NGN", "symbol": "₦", "before": True, "sep": ",", "decimals": 0,
           "word": ("naira", "naira"), "languages": ["Pidgin", "English", "Yoruba", "Hausa", "Igbo"],
           "savings_group": "ajo / esusu", "mobile_money": "OPay, Moniepoint, PalmPay"},
    "KE": {"name": "Kenya", "currency": "KES", "symbol": "KSh ", "before": True, "sep": ",", "decimals": 0,
           "word": ("shilling", "shillings"), "languages": ["English", "Swahili"],
           "savings_group": "chama", "mobile_money": "M-Pesa (~90%), Airtel Money",
           "units": "Sheng money slang: bob = shillings, mbao = 20, soo = 100, punch = 500, thao / ngiri = 1,000."},
    "SN": {"name": "Senegal", "currency": "XOF", "symbol": " FCFA", "before": False, "sep": " ", "decimals": 0,
           "word": ("CFA franc", "CFA francs"), "languages": ["French", "Wolof"],
           "savings_group": "tontine", "mobile_money": "Wave (>50%), Orange Money",
           "units": "In Wolof, prices are often counted in dërëm: 1 dërëm = 5 FCFA, and the unit is often left out (\"100\" may mean 100 dërëm = 500 FCFA). If unsure which is meant, give FCFA and say so in \"note\"."},
    "CI": {"name": "Côte d'Ivoire", "currency": "XOF", "symbol": " FCFA", "before": False, "sep": " ",
           "decimals": 0, "word": ("CFA franc", "CFA francs"), "languages": ["French", "Dioula"],
           "savings_group": "tontine", "mobile_money": "Orange Money, MTN MoMo, Wave, Moov",
           "units": "Nouchi money slang: barre / krika = 1,000 FCFA, gbon = 5,000, gbessê = 500, togo = 100."},
    "MA": {"name": "Morocco", "currency": "MAD", "symbol": " DH", "before": False, "sep": " ", "decimals": 2,
           "word": ("dirham", "dirhams"), "languages": ["Darija", "French", "Arabic"],
           "savings_group": "daret", "mobile_money": "mostly cash (mobile money ~12%)", "weekend": "Sat-Sun",
           "units": "Traders often count in ryal: 20 ryal = 1 dirham (\"alf ryal\" = 1,000 ryal = 50 DH). \"franc\" / \"million\" can mean centimes (1 million = 10,000 DH). Always give the amount in DIRHAM; if unsure which unit was meant, say so in \"note\"."},
    "DZ": {"name": "Algeria", "currency": "DZD", "symbol": " DA", "before": False, "sep": " ", "decimals": 2,
           "word": ("dinar", "dinars"), "languages": ["Darija", "French", "Arabic"],
           "savings_group": "jam'iya", "mobile_money": "BaridiMob / CCP, Edahabia", "weekend": "Fri-Sat",
           "units": "People often count in centimes (sontim): 1 million = 10,000 DA, and \"milliard\" is also in centimes. Always give the amount in DINAR; if unsure which unit was meant, say so in \"note\"."},
    "TN": {"name": "Tunisia", "currency": "TND", "symbol": " DT", "before": False, "sep": " ", "decimals": 3,
           "word": ("dinar", "dinars"), "languages": ["Derja", "French", "Arabic"],
           "savings_group": "jam'iya", "mobile_money": "D17, Flouci",
           "units": "1 dinar = 1,000 millimes; prices have 3 decimals (2.990 DT). \"three thousand\" may mean 3 DT (3,000 millimes). Always give the amount in DINAR; if unsure, say so in \"note\"."},
    "SA": {"name": "Saudi Arabia", "currency": "SAR", "symbol": " SAR", "before": False, "sep": ",", "decimals": 2,
           "word": ("riyal", "riyals"), "languages": ["Arabic", "English"],
           "savings_group": "jam'iya", "mobile_money": "mada cards (85% of retail payments e-pay), STC Bank",
           "weekend": "Fri-Sat", "no_interest": True,
           "units": "1 riyal = 100 halala. Never add or mention interest (riba): use \"amount due\"."},
}


def ai_hint(code=None):
    """Country line added to the AI prompt: currency + the local counting traps (ryal, centimes, millimes, dërëm)."""
    p = pack(code)
    return (f"\nThe trader is in {p['name']}; amounts are in {p['word'][1]} ({p['currency']}) unless said otherwise. "
            + p.get("units", ""))


def pack(code=None):
    return PACKS.get((code or os.getenv("COUNTRY", "NG")).upper(), PACKS["NG"])


def money(x, code=None):
    """45000 -> '₦45,000' (NG), '45 000 FCFA' (SN/CI), 'KSh 45,000' (KE), '12.5 DT' (TN)."""
    p = pack(code)
    x = float(x or 0)
    sign, x = ("-" if x < 0 else ""), abs(x)
    whole = f"{x:,.0f}" if x == int(x) or not p["decimals"] else f"{x:,.{p['decimals']}f}".rstrip("0").rstrip(".")
    whole = whole.replace(",", p["sep"])
    return f"{sign}{p['symbol']}{whole}" if p["before"] else f"{sign}{whole}{p['symbol']}"


def money_words(x, code=None):
    """Amount in English words + currency name, for voice replies: 'forty-five thousand CFA francs'."""
    from tts import number_words

    one, many = pack(code)["word"]
    return f"{number_words(x)} {one if round(float(x or 0)) == 1 else many}"
