"""The main words on screen in 5 languages (tab names, main buttons, consent). Picked with "🌍 App language".

Short, everyday words on purpose. ⚠️ Pidgin/Yoruba/Hausa/Igbo written by a non-native speaker: have native speakers
check and fix this file (one place for all of it). Anything not listed here stays in English.
"""
LANGS = ["English", "Pidgin", "Yoruba", "Hausa", "Igbo"]

UI = {
    "tab_talk": ["💬 Talk to TradeVoice", "💬 Yarn with TradeVoice", "💬 Bá TradeVoice sọ̀rọ̀", "💬 Yi hira da TradeVoice",
                 "💬 Gwa TradeVoice okwu"],
    "tab_speak": ["🎙️ Speak", "🎙️ Talk am", "🎙️ Sọ̀rọ̀", "🎙️ Yi magana", "🎙️ Kwuo okwu"],
    "tab_snap": ["📸 Snap your book", "📸 Snap your book", "📸 Ya fọ́tò ìwé rẹ", "📸 Ɗauki hoton littafinka",
                 "📸 See foto akwụkwọ gị"],
    "tab_today": ["📊 Today", "📊 Today", "📊 Òní", "📊 Yau", "📊 Taa"],
    "tab_owes": ["📒 Who owes me / who I owe", "📒 Who dey owe me / who I owe", "📒 Gbèsè", "📒 Bashi", "📒 Ụgwọ"],
    "tab_insights": ["🔮 Insights", "🔮 Wetin dey come", "🔮 Ìmọ̀ràn", "🔮 Shawarwari", "🔮 Ndụmọdụ"],
    "tab_ask": ["💬 Ask my book", "💬 Ask your book", "💬 Béèrè lọ́wọ́ ìwé rẹ", "💬 Tambayi littafinka",
                "💬 Jụọ akwụkwọ gị"],
    "tab_credit": ["🏦 Credit profile", "🏦 Your record for loan", "🏦 Àkọsílẹ̀ fún owó yíyá", "🏦 Bayanan rance",
                   "🏦 Ndekọ maka mbinye ego"],
    "tab_data": ["🔒 My data", "🔒 My data", "🔒 Àkọsílẹ̀ mi", "🔒 Bayanaina", "🔒 Data m"],
    "process": ["Process", "Check am", "Ṣàyẹ̀wò", "Duba", "Lelee"],
    "confirm": ["✅ Confirm & save", "✅ Correct, save am", "✅ Ó tọ̀nà, kọ ọ́ sílẹ̀", "✅ Daidai ne, adana",
                "✅ Ọ dị mma, chekwaa"],
    "read": ["🔊 Read it to me", "🔊 Read am for me", "🔊 Kà á fún mi", "🔊 Karanta min", "🔊 Gụọrọ m ya"],
    "ask": ["Ask", "Ask", "Béèrè", "Tambaya", "Jụọ"],
    "refresh": ["🔄 Refresh", "🔄 Refresh", "🔄 Tún un wò", "🔄 Sabunta", "🔄 Megharịa"],
    "voice_note": ["Voice note", "Voice note", "Ohùn", "Saƙon murya", "Ozi olu"],
    "type_it": ["…or type it", "…or type am", "…tàbí kọ ọ́", "…ko rubuta", "…ma ọ bụ dee ya"],
    # ---- web app (web/): words on the WhatsApp-style screens
    "nav_talk": ["Chat", "Chat", "Ìjíròrò", "Hira", "Nkata"],
    "nav_book": ["Book", "Book", "Ìwé", "Littafi", "Akwụkwọ"],
    "nav_debts": ["Debts", "Debts", "Gbèsè", "Bashi", "Ụgwọ"],
    "nav_insights": ["Insights", "Wetin dey come", "Ìmọ̀ràn", "Shawarwari", "Ndụmọdụ"],
    "nav_profile": ["Profile", "Profile", "Àkọsílẹ̀", "Bayanai", "Ndekọ"],
    "online": ["online · hears English, Pidgin, Yoruba, Hausa, Igbo", "online · e dey hear English, Pidgin, Yoruba, "
               "Hausa, Igbo", "wà lórí ayélujára", "yana kan layi", "nọ n'ịntanetị"],
    "message": ["Message", "Message", "Kọ ọ̀rọ̀", "Rubuta saƙo", "Dee ozi"],
    "hold": ["Hold 🎤 to talk", "Hold 🎤 make you talk", "Tẹ 🎤 mọ́lẹ̀ láti sọ̀rọ̀", "Riƙe 🎤 don yin magana",
             "Jide 🎤 ka i kwuo okwu"],
    "recording": ["Recording… let go to send", "I dey record… leave am make e send", "Ó ń gbà ohùn… fi sílẹ̀ láti fi ránṣẹ́",
                  "Ana nadi… saki don aika", "A na-edekọ… hapụ ka o ziga"],
    "tap_send": ["Tap 🎤 again to send · tap here to cancel", "Tap 🎤 again make e send · tap here to cancel",
                 "Tẹ 🎤 lẹ́ẹ̀kan sí i láti fi ránṣẹ́", "Sake taɓa 🎤 don aikawa", "Pịa 🎤 ọzọ ka o ziga"],
    "i_speak": ["I'm speaking", "I dey talk", "Mo ń sọ", "Ina magana da", "Ana m asụ"],
    "yes_save": ["✅ Yes, save", "✅ Yes, save am", "✅ Bẹ́ẹ̀ni, kọ ọ́", "✅ Eh, adana", "✅ Ee, chekwaa"],
    "no": ["❌ No", "❌ No", "❌ Rárá", "❌ A'a", "❌ Mba"],
    "hello": ["Hello 👋 I'm your book. Tell me what you sold, who owes you, or ask me anything. Hold 🎤 to talk, or 📎 "
              "to snap your notebook.",
              "Hello 👋 Na me be your book. Tell me wetin you sell, who dey owe you, or ask me anything. Hold 🎤 make "
              "you talk, or 📎 to snap your book.",
              "Ẹ n lẹ́ o 👋 Èmi ni ìwé rẹ. Sọ ọjà tí o tà, ẹni tó jẹ ọ́, tàbí béèrè ohunkóhun. Tẹ 🎤 mọ́lẹ̀ láti sọ̀rọ̀, "
              "tàbí 📎 láti ya fọ́tò ìwé rẹ.",
              "Sannu 👋 Ni ne littafinka. Faɗa min abin da ka sayar, wanda ke da bashinka, ko ka tambaye ni komai. "
              "Riƙe 🎤 don yin magana, ko 📎 don ɗaukar hoton littafinka.",
              "Ndewo 👋 Abụ m akwụkwọ gị. Gwa m ihe i rere, onye ji gị ụgwọ, ma ọ bụ jụọ m ihe ọ bụla. Jide 🎤 ka i "
              "kwuo okwu, ma ọ bụ 📎 iji see foto akwụkwọ gị."],
    "reading_photo": ["Reading your photo…", "I dey read your photo…", "Mo ń ka fọ́tò rẹ…", "Ina karanta hotonka…",
                      "A na m agụ foto gị…"],
    "save_ticked": ["✅ Save ticked", "✅ Save the ones wey I tick", "✅ Kọ àwọn tí mo yàn", "✅ Adana waɗanda aka zaɓa",
                    "✅ Chekwaa ndị a họrọ"],
    "sold": ["Sold", "Sell", "Ọjà tí o tà", "An sayar", "Ire"],
    "spent": ["Spent", "Spend", "Owó tí o ná", "An kashe", "Mmefu"],
    "came_in": ["Came in", "Enter hand", "Owó tó wọlé", "Ya shigo", "Batara"],
    "recent": ["Recent", "Wetin you write last", "Àkọsílẹ̀ tuntun", "Na baya-bayan nan", "Nke ọhụrụ"],
    "owe_me": ["Owe me", "Dey owe me", "Wọ́n jẹ mí", "Bashina", "Ji m ụgwọ"],
    "i_owe": ["I owe", "I dey owe", "Mo jẹ", "Ina da bashi", "Ana m ji ụgwọ"],
    "remind": ["Remind", "Remind am", "Rán létí", "Tunatar", "Chetara"],
    "days_late": ["{n} days late", "{n} days late", "Ọjọ́ {n} ti kọjá", "Kwanaki {n} a makare", "Ụbọchị {n} agafeela"],
    "on_time": ["on time", "e never reach", "kò tíì pẹ́", "a kan lokaci", "n'oge"],
    "next_week": ["Next 7 days", "Next 7 days", "Ọjọ́ méje tó ń bọ̀", "Kwanaki 7 masu zuwa", "Ụbọchị 7 na-abịa"],
    "busiest": ["Busiest day", "Day wey market dey move pass", "Ọjọ́ tí ọjà ń tà jù", "Ranar da aka fi sayarwa",
                "Ụbọchị ahịa kacha aga"],
    "best_sellers": ["Best sellers", "Wetin dey sell pass", "Ọjà tó ń tà jù", "Kayan da aka fi sayarwa",
                     "Ihe kacha ere"],
    "score": ["Record score", "Record score", "Àmì àkọsílẹ̀", "Makin bayanai", "Akara ndekọ"],
    "statement": ["⬇️ Statement for lender / cooperative", "⬇️ Statement for loan people / cooperative",
                  "⬇️ Ìwé fún ẹni tó ń yáni lówó", "⬇️ Takarda don mai ba da rance", "⬇️ Akwụkwọ maka ndị na-agbazinye ego"],
    "welcome": ["Welcome to TradeVoice", "Welcome to TradeVoice", "Ẹ káàbọ̀ sí TradeVoice", "Barka da zuwa TradeVoice",
                "Nnọọ na TradeVoice"],
    "agree": ["Agree and continue", "I gree, make we go", "Mo gbà, ẹ jẹ́ ká lọ", "Na yarda, mu ci gaba",
              "Ekwere m, ka anyị gaa"],
    "app_language": ["App language", "App language", "Èdè", "Harshe", "Asụsụ"],
    "shop_name": ["Shop name", "Shop name", "Orúkọ ṣọ́ọ̀bù", "Sunan shago", "Aha ụlọ ahịa"],
    "my_data": ["My data", "My data", "Àkọsílẹ̀ mi", "Bayanaina", "Data m"],
    "consent": [
        "I agree that my voice note / photo is processed by AI to create my records. "
        "The audio or photo is deleted right after it is read.",
        "I gree make AI read my voice note / photo to write my records. Dem go delete the voice or photo after.",
        "Mo gbà kí AI ka ohùn tàbí fọ́tò mi láti kọ àkọsílẹ̀ mi. Wọn yóò pa ohùn tàbí fọ́tò náà rẹ́ lẹ́yìn náà.",
        "Na yarda AI ta karanta muryata ko hotona don rubuta bayanaina. Za a goge muryar ko hoton bayan haka.",
        "Ekwere m ka AI gụọ olu m ma ọ bụ foto m iji dee ndekọ m. A ga-ehichapụ ha mgbe e mechara.",
    ],
}


def t(key, lang):
    """Word for `key` in `lang` (falls back to English)."""
    values = UI[key]
    return values[LANGS.index(lang)] if lang in LANGS else values[0]
