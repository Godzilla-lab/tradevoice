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
           "savings_group": "chama", "mobile_money": "M-Pesa"},
    "SN": {"name": "Senegal", "currency": "XOF", "symbol": " FCFA", "before": False, "sep": " ", "decimals": 0,
           "word": ("CFA franc", "CFA francs"), "languages": ["French", "Wolof"],
           "savings_group": "tontine", "mobile_money": "Wave, Orange Money"},
    "CI": {"name": "Côte d'Ivoire", "currency": "XOF", "symbol": " FCFA", "before": False, "sep": " ",
           "decimals": 0, "word": ("CFA franc", "CFA francs"), "languages": ["French", "Dioula"],
           "savings_group": "tontine", "mobile_money": "Orange Money, MTN MoMo, Wave, Moov"},
    "MA": {"name": "Morocco", "currency": "MAD", "symbol": " DH", "before": False, "sep": " ", "decimals": 2,
           "word": ("dirham", "dirhams"), "languages": ["Darija", "French", "Arabic"],
           "savings_group": "dart", "mobile_money": "cash, CIH / Barid Cash"},
    "DZ": {"name": "Algeria", "currency": "DZD", "symbol": " DA", "before": False, "sep": " ", "decimals": 2,
           "word": ("dinar", "dinars"), "languages": ["Darija", "French", "Arabic"],
           "savings_group": "tontine / jam'iya", "mobile_money": "BaridiMob (CCP)"},
    "TN": {"name": "Tunisia", "currency": "TND", "symbol": " DT", "before": False, "sep": " ", "decimals": 3,
           "word": ("dinar", "dinars"), "languages": ["Derja", "French", "Arabic"],
           "savings_group": "jam'iya", "mobile_money": "D17, Flouci"},
    "SA": {"name": "Saudi Arabia", "currency": "SAR", "symbol": " SAR", "before": False, "sep": ",", "decimals": 2,
           "word": ("riyal", "riyals"), "languages": ["Arabic", "English"],
           "savings_group": "jam'iya", "mobile_money": "STC Pay, mada"},
}


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
