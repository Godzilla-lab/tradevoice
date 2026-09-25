"""The main words on screen in 5 languages (tab names, main buttons, consent). Picked with "🌍 App language".

Short, everyday words on purpose. ⚠️ Pidgin/Yoruba/Hausa/Igbo written by a non-native speaker: have native speakers
check and fix this file (one place for all of it). Anything not listed here stays in English.
"""
LANGS = ["English", "Pidgin", "Yoruba", "Hausa", "Igbo"]

UI = {
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
