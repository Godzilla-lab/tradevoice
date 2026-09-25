"""🔊 "Read it to me": each main screen as a short spoken summary in the trader's language.

For traders who can't read (in any language): the app talks. Numbers come from the book (ledger/insights), written
as words by tts.naira_words; the sentences are fixed templates, never AI-written.
⚠️ Yoruba / Hausa / Igbo sentences need a native-speaker check.
"""
import insights
import ledger
from askbook import OWED
from tts import naira_words, number_words

T = {
    "today": {
        "English": "Today you sold {s}. You spent {x}. Money that came into your hand: {c}.",
        "Pidgin": "Today you don sell {s}. You spend {x}. Money wey enter your hand na {c}.",
        "Yoruba": "Lónìí o ta ọjà ní {s}. O ná {x}. Owó tó wọ ọwọ́ rẹ jẹ́ {c}.",
        "Hausa": "Yau an sayar na {s}. An kashe {x}. Kuɗin da ya shigo hannu {c}.",
        "Igbo": "Taa i rere ahịa {s}. I mefuru {x}. Ego batara n'aka gị bụ {c}.",
    },
    "today_none": {"English": "Nothing is recorded today yet.", "Pidgin": "You never write anything today.",
                   "Yoruba": "Kò sí àkọsílẹ̀ kankan lónìí.", "Hausa": "Babu abin da aka rubuta yau.",
                   "Igbo": "Ọ dịghị ihe e dere taa."},
    "owes_intro": {"English": "{n} people owe you {t} in total.", "Pidgin": "{n} people dey owe you {t} total.",
                   "Yoruba": "Èèyàn {n} ló jẹ ọ́, gbogbo rẹ̀ jẹ́ {t}.",
                   "Hausa": "Mutane {n} ne ke da bashinka, jimla {t}.",
                   "Igbo": "Mmadụ {n} ji gị ụgwọ, ngụkọta bụ {t}."},
    "late": {"English": " {n} is late.", "Pidgin": " {n} don late.", "Yoruba": " {n} ti pẹ́ láti san.",
             "Hausa": " {n} ya makara.", "Igbo": " {n} agafeela ụbọchị ya."},
    "insights": {
        "English": "Next week you may sell about {s}. {d} is your busiest day. Your best seller is {i}.",
        "Pidgin": "Next week you fit sell like {s}. {d} na your busiest day. Wetin dey sell pass na {i}.",
        "Yoruba": "Ní ọ̀sẹ̀ tó ń bọ̀, o lè ta tó {s}. {d} ni ọjọ́ tí ọjà rẹ ń tà jù. Ọjà tó ń tà jù ni {i}.",
        "Hausa": "Makon gobe za a iya sayar kusan {s}. {d} ce ranar da aka fi sayarwa. Kayan da aka fi sayarwa shi ne {i}.",
        "Igbo": "N'izu na-abịa, i nwere ike ire ihe ruru {s}. {d} bụ ụbọchị ahịa gị kacha aga. Ihe kacha ere bụ {i}.",
    },
    "insights_none": {"English": "Record a few more days, then I can tell you about next week.",
                      "Pidgin": "Write for some more days, then I go fit tell you about next week.",
                      "Yoruba": "Kọ àkọsílẹ̀ fún ọjọ́ díẹ̀ sí i, lẹ́yìn náà mo lè sọ nípa ọ̀sẹ̀ tó ń bọ̀.",
                      "Hausa": "Ka rubuta na wasu kwanaki, sannan zan iya faɗa maka game da makon gobe.",
                      "Igbo": "Dee ihe ụbọchị ole na ole ọzọ, mgbe ahụ m ga-agwa gị maka izu na-abịa."},
    "profile": {
        "English": "Your record score is {s} out of 100. Sales in your book: {r}. Money people owe you: {o}.",
        "Pidgin": "Your record score na {s} over 100. Sales for your book: {r}. Money wey people owe you: {o}.",
        "Yoruba": "Àmì àkọsílẹ̀ rẹ jẹ́ {s} nínú 100. Ọjà tí o ti tà: {r}. Owó tí wọ́n jẹ ọ́: {o}.",
        "Hausa": "Makin bayananka {s} cikin 100. Kayan da aka sayar: {r}. Bashin da ake bi: {o}.",
        "Igbo": "Akara ndekọ gị bụ {s} n'ime 100. Ahịa i rere: {r}. Ego ndị mmadụ ji gị: {o}.",
    },
    "profile_none": {"English": "Your book is empty. Start by recording a sale.",
                     "Pidgin": "Your book still empty. Start by writing one sale.",
                     "Yoruba": "Ìwé rẹ ṣì ṣófo. Bẹ̀rẹ̀ nípa kíkọ ọjà kan tí o tà.",
                     "Hausa": "Littafinka babu komai. Fara da rubuta wani abin da aka sayar.",
                     "Igbo": "Akwụkwọ gị tọgbọrọ chakoo. Bido site n'ide otu ahịa i rere."},
}
LANGS = list(T["today"])


def _lang(lang):
    return lang if lang in LANGS else "Pidgin"


def today(lang):
    lang = _lang(lang)
    s = ledger.day_summary()
    if not s["count"]:
        return T["today_none"][lang]
    cash_in = s["cash_sales"] + s["payments_received"]
    return T["today"][lang].format(s=naira_words(s["sales"]), x=naira_words(s["expenses"]), c=naira_words(cash_in))


def owes(lang):
    lang = _lang(lang)
    ds, cs = ledger.debtors(), ledger.creditors()
    parts = []
    if ds:
        parts.append(T["owes_intro"][lang].format(n=number_words(len(ds)),
                                                  t=naira_words(sum(d["balance"] for d in ds))))
        for d in ds[:5]:
            parts.append(OWED["owed_to_me"][lang].format(who=d["customer"], m=naira_words(d["balance"])))
            if d["overdue"]:
                parts[-1] += T["late"][lang].format(n=d["customer"])
    else:
        parts.append(OWED["none"][lang])
    parts += [OWED["i_owe"][lang].format(who=c["customer"], m=naira_words(c["balance"])) for c in cs[:3]]
    return " ".join(parts)


def insights_text(lang):
    lang = _lang(lang)
    f = insights.forecast()
    if not f:
        return T["insights_none"][lang]
    top = insights.top_items()
    rounded = round(f["week_sales"], -4 if f["week_sales"] >= 100_000 else -3)  # "about ₦590,000" is easier to hear
    return T["insights"][lang].format(s=naira_words(rounded), d=f["busiest_day"],
                                      i=top[0]["item"] if top else "-")


def profile(lang):
    lang = _lang(lang)
    p = ledger.credit_profile()
    if not p:
        return T["profile_none"][lang]
    return T["profile"][lang].format(s=number_words(p["score"]), r=naira_words(p["revenue"]),
                                     o=naira_words(p["outstanding"]))


SCREENS = {"today": today, "owes": owes, "insights": insights_text, "profile": profile}


def text(screen, lang):
    return SCREENS[screen](lang)
