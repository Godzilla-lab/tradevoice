"""Tax and your records: plain facts about Nigeria's 2026 tax laws, next to the trader's own year from the book.

Facts only, each with its source (docs/FINANCE_RESEARCH.md). We never say how much tax someone owes: that is for the
state revenue service or a tax adviser. The rules are under review (Sep 2026), so every screen says "check first".
⚠️ A Nigerian tax professional should check the facts, and native speakers the Yoruba / Hausa / Igbo / Pidgin.
"""
import ui_text

LANGS = ui_text.LANGS

# (key, [English, Pidgin, Yoruba, Hausa, Igbo], source)
FACTS = [
    ("new",
     ["New tax laws started on 1 January 2026. FIRS is now called NRS.",
      "New tax law start for 1 January 2026. FIRS don change name to NRS.",
      "Òfin owó-orí tuntun bẹ̀rẹ̀ ní 1 January 2026. Orúkọ FIRS ti di NRS.",
      "Sababbin dokokin haraji sun fara a 1 ga Janairu 2026. Yanzu ana kiran FIRS da NRS.",
      "Iwu ụtụ isi ọhụrụ malitere na 1 January 2026. A na-akpọ FIRS NRS ugbu a."],
     "https://www.pwc.com/ng/en/publications/the-nigerian-tax-reform-acts.html"),
    ("state",
     ["If you trade on your own, your income tax goes to your state revenue service (for example LIRS in Lagos).",
      "If na you alone dey trade, your income tax go your state revenue service (like LIRS for Lagos).",
      "Tí o bá ń ṣòwò fúnra rẹ, owó-orí rẹ ń lọ sí ilé-iṣẹ́ owó-orí ìpínlẹ̀ rẹ (bíi LIRS ní Èkó).",
      "Idan kana kasuwanci kai kaɗai, harajin kuɗin shigarka yana zuwa hukumar haraji ta jiharka (kamar LIRS a Legas).",
      "Ọ bụrụ na ị na-azụ ahịa naanị gị, ụtụ isi gị na-aga n'ụlọ ọrụ ụtụ isi steeti gị (dịka LIRS na Lagos)."],
     "https://taxsummaries.pwc.com/nigeria/individual/taxes-on-personal-income"),
    ("profit",
     ["Income tax is on profit, not on everything you sell. Your records show your real profit.",
      "Income tax na on top profit, no be on everything wey you sell. Your records dey show your real profit.",
      "Owó-orí wà lórí èrè, kì í ṣe lórí gbogbo ohun tí o tà. Àkọsílẹ̀ rẹ ń fi èrè gidi rẹ hàn.",
      "Harajin kuɗin shiga yana kan riba ne, ba kan duk abin da ka sayar ba. Bayananka suna nuna ainihin ribarka.",
      "Ụtụ isi dị n'uru, ọ bụghị n'ihe niile ị rere. Ndekọ gị na-egosi ezigbo uru gị."],
     "https://www.mondaq.com/nigeria/capital-gains-tax/1726922/understanding-personal-income-tax-under-the-nigerian-tax-act-2025"),
    ("free",
     ["The first ₦800,000 of taxable profit in a year is taxed at 0%.",
      "The first ₦800,000 of taxable profit for one year, dem no dey tax am (0%).",
      "₦800,000 àkọ́kọ́ nínú èrè tí a lè gba owó-orí lé lórí lọ́dún kò ní owó-orí (0%).",
      "₦800,000 na farko na ribar da ake biyan haraji a kai a shekara, harajinta 0% ne.",
      "₦800,000 mbụ nke uru a na-atụ ụtụ n'afọ, ụtụ ya bụ 0%."],
     "https://businessday.ng/news/article/individuals-earning-up-to-n100000-monthly-wont-pay-personal-income-tax-from-2026-oyedele/"),
    ("records",
     ["Traders without records can be charged a tax guessed from their sales. With records, you can show your real "
      "profit instead.",
      "Trader wey no get record, dem fit guess tax from wetin e sell. If you get record, you fit show your real profit.",
      "Oníṣòwò tí kò ní àkọsílẹ̀ lè san owó-orí tí wọ́n fojú díwọ̀n láti inú ọjà tó tà. Pẹ̀lú àkọsílẹ̀, o lè fi èrè gidi "
      "rẹ hàn.",
      "Ɗan kasuwa da ba shi da bayanai ana iya kimanta masa haraji daga abin da yake sayarwa. Da bayanai, za ka iya "
      "nuna ainihin ribarka.",
      "Onye ahịa na-enweghị ndekọ nwere ike ịkwụ ụtụ e chere site n'ihe ọ rere. Site na ndekọ, ị nwere ike igosi ezigbo "
      "uru gị."],
     "https://businessday.ng/business-economy/article/explainer-presumptive-tax-how-nigeria-is-taxing-its-informal-economy/"),
    ("nin",
     ["Your NIN is your Tax ID. It is free: don't pay anyone for it.",
      "Your NIN na your Tax ID. E free: no pay anybody for am.",
      "NIN rẹ ni Tax ID rẹ. Ọ̀fẹ́ ni: má ṣe san owó fún ẹnikẹ́ni fún un.",
      "NIN ɗinka shi ne Tax ID ɗinka. Kyauta ne: kada ka biya kowa kuɗi a kai.",
      "NIN gị bụ Tax ID gị. Ọ bụ n'efu: akwụla onye ọ bụla ego maka ya."],
     "https://www.channelstv.com/2025/12/23/nin-now-automatic-tax-id-firs/"),
    ("bank",
     ["Nobody can take tax from your bank account because of transfers. The ₦50 charge on transfers of ₦10,000 or "
      "more is paid by the sender.",
      "Nobody fit comot tax from your bank account because of transfer. The ₦50 charge for transfer of ₦10,000 or "
      "more, na the person wey send am dey pay.",
      "Kò sí ẹni tó lè gba owó-orí láti inú àkántì rẹ nítorí owó tí wọ́n fi ránṣẹ́ sí ọ. Ẹni tó fi owó ránṣẹ́ ló ń san "
      "₦50 lórí ₦10,000 tàbí jù bẹ́ẹ̀ lọ.",
      "Babu wanda zai iya cire haraji daga asusun bankinka saboda tura kuɗi. Mai turawa ne ke biyan ₦50 a kan "
      "₦10,000 ko fiye.",
      "Ọ dịghị onye nwere ike iwepụ ụtụ isi n'akaụntụ gị n'ihi ego e zitere gị. Onye zitere ego na-akwụ ₦50 maka "
      "₦10,000 ma ọ bụ karịa."],
     "https://www.channelstv.com/2025/12/30/tax-laws-govt-wont-debit-your-account-oyedele-assures-nigerians/"),
    ("receipt",
     ["Collecting tax in cash or at roadblocks is banned. Ask for an official receipt. Think a levy is illegal? "
      "Complain for free to the Tax Ombud (taxombud.gov.ng).",
      "To collect tax for cash or for roadblock don ban. Ask for official receipt. If you think say levy no legal, "
      "complain free to Tax Ombud (taxombud.gov.ng).",
      "Wọ́n ti fòfin de gbígba owó-orí ní owó ọwọ́ tàbí lójú ọ̀nà. Béèrè ìwé-ẹ̀rí owó (receipt) gidi. Tí o bá rò pé owó "
      "kan kò bófin mu, fi ẹ̀sùn sùn Tax Ombud lọ́fẹ̀ẹ́ (taxombud.gov.ng).",
      "An hana karɓar haraji da tsabar kuɗi ko a kan hanya. Nemi rasit na hukuma. Kana ganin wani kuɗi ba bisa doka "
      "ba? Kai ƙara kyauta ga Tax Ombud (taxombud.gov.ng).",
      "A machiri ịnakọta ụtụ isi n'ego aka ma ọ bụ n'okporo ụzọ. Rịọ maka akwụkwọ nnata gọọmentị. Ọ bụrụ na i chere "
      "na ụtụ adịghị n'iwu, mee mkpesa n'efu na Tax Ombud (taxombud.gov.ng)."],
     "https://taxombud.gov.ng/"),
    ("keep",
     ["Keep your records for 6 years, and keep your rent receipts: rent can lower your tax.",
      "Keep your records for 6 years, and keep your rent receipt: rent fit reduce your tax.",
      "Tọ́jú àkọsílẹ̀ rẹ fún ọdún mẹ́fà, kí o sì tọ́jú ìwé-ẹ̀rí owó ilé: owó ilé lè dín owó-orí rẹ kù.",
      "Ajiye bayananka na shekaru 6, kuma ka ajiye rasit na kuɗin haya: haya na iya rage harajinka.",
      "Chekwaa ndekọ gị afọ 6, chekwaakwa akwụkwọ nnata ụgwọ ụlọ: ụgwọ ụlọ nwere ike ibelata ụtụ isi gị."],
     "https://kpmg.com/xx/en/our-insights/gms-flash-alert/flash-alert-2025-168.html"),
]

CHECK = ["The rules are being reviewed now (September 2026). Check with your state revenue service or a tax adviser "
         "before you pay. This is not tax advice.",
         "Government dey review the rules now (September 2026). Check with your state revenue office or tax adviser "
         "before you pay. This no be tax advice.",
         "Ìjọba ń ṣàtúnyẹ̀wò àwọn òfin yìí báyìí (September 2026). Bá ilé-iṣẹ́ owó-orí ìpínlẹ̀ rẹ tàbí olùdámọ̀ràn "
         "owó-orí sọ̀rọ̀ kí o tó sanwó. Èyí kì í ṣe ìmọ̀ràn owó-orí.",
         "Ana sake duba dokokin yanzu (Satumba 2026). Tuntuɓi hukumar haraji ta jiharka ko mai ba da shawara kan "
         "haraji kafin ka biya. Wannan ba shawarar haraji ba ce.",
         "A na-enyocha iwu ndị a ugbu a (September 2026). Jụọ ụlọ ọrụ ụtụ isi steeti gị ma ọ bụ onye ndụmọdụ ụtụ isi "
         "tupu ị kwụọ ụgwọ. Nke a abụghị ndụmọdụ ụtụ isi."]


def _pick(values, lang):
    return values[ui_text.TABLE_LANGS.index(ui_text.choose(lang))]


def facts(lang="English"):
    return [{"key": k, "text": _pick(v, lang), "source": src} for k, v, src in FACTS]


def check(lang="English"):
    return _pick(CHECK, lang)


def chat_answer(lang="English", year=None):
    """A short tax answer for the chat / WhatsApp / voice: the trader's year + the 4 facts that matter most."""
    words = {k: _pick(v, lang) for k, v, _ in FACTS}
    lines = []
    if year and year.get("entries"):
        lines.append(ui_text.t("tax_you", lang).replace("{s}", _naira(year["sales"]))
                     .replace("{e}", _naira(year["expenses"])))
    lines += [words["profit"], words["free"], words["records"], words["nin"], check(lang)]
    return "\n\n".join(lines)


def _naira(x):
    return ("-" if x < 0 else "") + f"₦{abs(x):,.0f}"
