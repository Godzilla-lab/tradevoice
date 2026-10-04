"""One conversation, any of our languages, one book.

    Trader: "Mama Tunde dey owe me forty-five thousand."   -> draft record, "say yes to save"
    Trader: "Yes"                                           -> saved, new balance
    Trader: "Ṣé mo ní gbèsè lọ́wọ́ Alhaji?"                  -> answered in Yoruba from the same book
    Trader: "Remind her tomorrow"                           -> "her" = Mama Tunde; reminder set, message ready

Each message is routed (yes/no to a draft, reminder, question, new record) by simple rules; the AI only reads the
record or the question (extract.py / askbook.py); every number comes from the book. The language can change on
every message: each reply follows the language of the message it answers. `reply()` does not depend on the web
page, so the WhatsApp bot can use it as it is.
Yoruba / Hausa / Igbo sentences need a native-speaker check.
"""
import datetime as dt
import os
import re
import time
import urllib.parse

import askbook
import clock
import insights
import ledger
import tts
from extract import extract, fold, is_list, parse_amount, parse_due, read_list, rule_extract, type_is_explicit
from extract import parse_customer as extract_customer

LANGS = askbook.LANGS

# spoken answers come with a little more ("yes please, save it", "no, leave it"): the extra words may only be these
_YES_MORE = r"(?:[\s,.!]+(?:please|save( it| am| them| dem)?|all|both|everything|all of (them|dem)|go ahead|do it|write it|" \
            r"correct|that'?s (right|correct)|na so|e correct|" \
            r"o|sir|ma|abeg|thank you|thanks|o to|o dara|kosi wahala|haka ne|rubuta|o di mma|dee ya))*"
YES = re.compile(r"^\s*(yes|yeah|yep|ok|okay|save|save am|save it|save them|save all|save both|save everything|go ahead|"
                 r"do it|correct|na so|e correct|sure|ehn|ee+h?|eh|"
                 r"beeni|o to|o dara|to|haka ne|eh to|i|ee|o di mma|ozi|confirm)" + _YES_MORE + r"\W*$")
NO = re.compile(r"^\s*(no|nope|cancel|no be so|leave am|forget am|rara|ko to|a'?a|ba haka ba|mba|o bughi ya)"
                r"(?:[\s,.!]+(?:thanks?|thank you|leave (it|am)|forget (it|am)|don'?t save( it)?|cancel( it)?|o|sir|ma|abeg))*\W*$")
# words of a trader's book in our 5 languages (folded): a free AI answer is only ever given to a message about the shop
ON_TOPIC = re.compile(r"\b(sell|sold|sale|sales|selling|buy|bought|buying|price|prices|cost|costs|customer|customers|"
                      r"owe|owes|owing|debt|debts|credit|pay|paid|payment|money|naira|kobo|cash|profit|loss|gain|"
                      r"spend|spent|spending|expense|expenses|stock|goods|item|items|product|shop|store|market|"
                      r"business|book|record|records|trade|trader|supplier|suppliers|loan|lender|save|saved|balance|"
                      r"remind|reminder|week|month|today|yesterday|year|bag|bags|carton|crate|best|most|least|"
                      r"wetin i|how much|how many|"
                      r"ta|ra|owo|gbese|onibaara|oja|ere|ise|"                     # yo
                      r"sayar|saya|kudi|bashi|kasuwa|riba|kaya|ciniki|"            # ha
                      r"rere|zuru|ego|ugwo|ahia|uru|ngwa|ole)\b")


def on_topic(text, vocab=None):
    """About the trader's shop: a shop word (5 languages), a number, or the name of someone in their book."""
    t = fold(text or "")
    if ON_TOPIC.search(t) or re.search(r"\d", t):
        return True
    names = (vocab or ledger.known_words(200)).get("names") or []
    return bool(askbook.find_name(text, names))


EVENT_MONEY = re.compile(r"\b(spent|spend|sold|sell|paid|pay|owe|owes|bought|buy|collect|took|carry)\b")
ONLY = re.compile(r"^\s*(?:yes\W+)?(?:save|keep)\b.*\bonly\b|^\s*only\b")   # "save Dino only" / "only Mike"
AND_MORE = re.compile(r"^\s*(and|also|plus|then|another one|another|again|&|\+)\b")    # "and Mike owes me 300k"
# "profit" said outright (Igbo "ere m" = I sold and "uru" are not used: they clash with sales words)
PROFIT_SAID = re.compile(r"\b(profit|profits|riba)\b|\b(i|we)( don)? (gain|gained)\b")
PROFIT_ASKED = re.compile(r"\bhow much\b|\bwhat\b|\bwetin\b|\?|\bmelo\b|\belo\b|\bnawa\b|\bole\b")
CANT_SEE = re.compile(r"\bi (just |don |have |'ve )?(share|shared|send|sent|upload|uploaded|forward|forwarded|attach|attached)"
                      r"\b.{0,30}\b(list|file|excel|sheet|picture|pic|photo|screenshot|document|message|it|am)\b"
                      r"|\b(check|see|look at|read) (my|the) (whatsapp|messages?|list|file|excel|sheet|email|status|picture|pic|photo|"
                      r"screenshot|image|document)\b")
REMIND = re.compile(r"\bremind\b|\bran .{0,40}\bleti\b|\bleti\b|\btunatar\b|\btuna wa\b|\bcheta(ra)?\b|\bchetara\b")
QUESTION = re.compile(r"\?|\bhow (much|many)\b|\bwho\b|\bwhat\b|\bwetin\b|\babi\b|\bdo i\b|\bdid\b|\bse\b|\bmelo\b|"
                      r"\belo\b|\bnawa\b|\bshin\b|\bole\b|\bkedu\b|\bani\b|\bna who\b")
TAX = re.compile(r"\b(tax|taxes|owo ori|haraji|utu isi|nrs|firs|lirs|tax id|presumptive)\b")
THANKS = re.compile(r"^\s*(thanks?( you)?|thank u|tnx|ese( gan)?|o ?se|na gode|daalu|good job|well done|ok thanks?)\W*$")
HELP = re.compile(r"\b(what can you do|how (do|does) (this|it|you) work|help me|who are you|what are you)\b")
SAY_THANKS = {"English": "You're welcome. Tell me anything you sell, spend or lend.",
              "Pidgin": "No wahala. Tell me anything wey you sell, spend or give for credit.",
              "Yoruba": "Kò tọ́pẹ́. Sọ ohunkóhun tí o tà, tí o ná, tàbí tí o fi ṣe àwìn fún mi.",
              "Hausa": "Ba komai. Faɗa min duk abin da ka sayar, ka kashe, ko ka bayar bashi.",
              "Igbo": "Ọ dị mma. Gwa m ihe ọ bụla i rere, i mefuru, ma ọ bụ i nyere n'ụgwọ."}
GREET = re.compile(r"^\s*(hi+|hello|hey|good (morning|afternoon|evening)|how far|bawo( ni)?|pele|e ?ka ?a?ro|e ?ka ?a?san|"
                   r"e ?ka ?a?le|sannu|ina kwana|ina wuni|ndewo|kedu|nnoo)\W*$")
PRONOUN = re.compile(r"\b(she|he|her|him|am|them|dem|that person|ita|shi|ya)\b")
TOMORROW_LOCAL = re.compile(r"\b(ola|lola|ni ola)\b")
# something happened (a record), in English/Pidgin, Yoruba, Hausa, Igbo
EVENT = re.compile(r"\b(sell|sold|owe|owes|pay|paid|buy|bought|spend|spent|collect|took|carry|give|gave|mo ta|ti san|"
                   r"sayar|biya|saya|rere|kwuru|zutara|ji m)\b")

SAY = {
    "heard": {"English": "I heard: {s} Should I save it? Say *yes*, or tell me what to change.",
              "Pidgin": "I hear say: {s} Make I save am? Talk *yes*, or tell me wetin to change.",
              "Yoruba": "Ohun tí mo gbọ́: {s} Sọ *bẹ́ẹ̀ni* kí n kọ ọ́ sílẹ̀, tàbí sọ ohun tí kò tọ̀nà.",
              "Hausa": "Abin da na ji: {s} Ka ce *eh* in adana, ko ka faɗi abin da za a gyara.",
              "Igbo": "Ihe m nụrụ: {s} Kwuo *ee* ka m chekwaa ya, ma ọ bụ gwa m ihe m ga-agbanwe."},
    "over_limit": {"English": "{who} already owes {bal}. This sale takes it to {after}, above the limit of {lim}. Sell anyway?",
                   "Pidgin": "{who} don already owe {bal}. This sale go make am {after}, e pass the limit wey be {lim}. You still wan sell?",
                   "Yoruba": "{who} ti jẹ ọ́ {bal} tẹ́lẹ̀. Ọjà yìí yóò mú un dé {after}, ó ju òpin {lim} lọ. Ṣé o ṣì fẹ́ tà?",
                   "Hausa": "{who} yana da bashinka {bal} tun da farko. Wannan sayarwar za ta kai {after}, ta wuce iyakar {lim}. Har yanzu ka sayar?",
                   "Igbo": "{who} ji gị {bal} ugbu a. Ahịa a ga-eme ya {after}, karịa oke {lim}. Ị ka ga-ere?"},
    "limit_set": {"English": "OK: {who} can owe you up to {lim}. I'll warn you before a sale goes over it.",
                  "Pidgin": "OK: {who} fit owe you reach {lim}. I go warn you before any sale pass am.",
                  "Yoruba": "Ó dáa: {who} lè jẹ ọ́ tó {lim}. Màá kìlọ̀ fún ọ kí ọjà tó kọjá rẹ̀.",
                  "Hausa": "To: {who} zai iya ɗaukar bashinka har {lim}. Zan faɗakar da kai kafin sayarwa ta wuce.",
                  "Igbo": "Ọ dị mma: {who} nwere ike iji gị ruo {lim}. M ga-adọ gị aka ná ntị tupu ahịa agafee ya."},
    "limit_off": {"English": "OK, no limit for {who} now.", "Pidgin": "OK, {who} no get limit again.",
                  "Yoruba": "Ó dáa, kò sí òpin fún {who} mọ́.", "Hausa": "To, babu iyaka ga {who} yanzu.",
                  "Igbo": "Ọ dị mma, {who} enweghị oke ugbu a."},
    "limit_who": {"English": "Whose limit? Say it like: Iya Bisi limit 30k.", "Pidgin": "Limit for who? Talk am like: Iya Bisi limit 30k.",
                  "Yoruba": "Òpin ta ni? Sọ ọ́ báyìí: Iya Bisi limit 30k.", "Hausa": "Iyakar wa? Faɗa kamar haka: Iya Bisi limit 30k.",
                  "Igbo": "Oke onye? Kwuo ya dị ka: Iya Bisi limit 30k."},
    "statement_ready": {"English": "Here is {who}'s statement. Check it, then forward it.",
                        "Pidgin": "See {who} statement. Check am, then forward am.",
                        "Yoruba": "Àkọsílẹ̀ {who} nìyí. Ṣàyẹ̀wò rẹ̀, kí o sì fi ránṣẹ́.",
                        "Hausa": "Ga bayanin asusun {who}. Ka duba, sannan ka tura.",
                        "Igbo": "Nke a bụ nkọwa akaụntụ {who}. Lelee ya, wee zipu ya."},
    "repeat": {"English": "{who} usually buys {what} on {day}.", "Pidgin": "{who} dey usually buy {what} every {day}.",
               "Yoruba": "{who} máa ń ra {what} ní ọjọ́ {day}.", "Hausa": "{who} yakan sayi {what} a ranar {day}.",
               "Igbo": "{who} na-azụkarị {what} n'ụbọchị {day}."},
    "repeat_none": {"English": "I don't see a usual order for {who} yet.", "Pidgin": "I never see usual order for {who}.",
                    "Yoruba": "Mi ò tíì rí ọjà tí {who} máa ń rà déédéé.", "Hausa": "Ban ga odar da {who} ya saba ba tukuna.",
                    "Igbo": "Ahụbeghị m ihe {who} na-azụkarị."},
    "updated": {"English": "OK, I changed it.", "Pidgin": "OK, I don change am.", "Yoruba": "Ó dáa, mo ti yí i padà.",
                "Hausa": "To, na canza shi.", "Igbo": "Ọ dị mma, agbanweela m ya."},
    "dropped": {"English": "(The one before was not saved.)", "Pidgin": "(The one wey dey before, I no save am.)",
                "Yoruba": "(Èyí tó ṣáájú, mi ò kọ ọ́ sílẹ̀.)", "Hausa": "(Na baya, ban adana shi ba.)",
                "Igbo": "(Nke gara aga, echekwaghị m ya.)"},
    # several drafts waiting (a list said one after the other): one "yes" saves them all
    "waiting": {"English": "{n} waiting to save: {list}. Say *yes* to save all.",
                "Pidgin": "{n} dey wait make I save: {list}. Talk *yes* make I save all.",
                "Yoruba": "{n} ló ń dúró: {list}. Sọ *bẹ́ẹ̀ni* kí n kọ gbogbo wọn sílẹ̀.",
                "Hausa": "{n} suna jira: {list}. Ka ce *eh* in adana duka.",
                "Igbo": "{n} na-eche: {list}. Kwuo *ee* ka m chekwaa ha niile."},
    "saved_n": {"English": "Saved {n}.", "Pidgin": "I don save {n}.", "Yoruba": "Mo ti kọ {n} sílẹ̀.",
                "Hausa": "An adana {n}.", "Igbo": "Echekwala m {n}."},
    "cancelled_n": {"English": "OK, I didn't save any of them.", "Pidgin": "No wahala, I no save any of dem.",
                    "Yoruba": "Ó dáa, mi ò kọ ìkankan sílẹ̀.", "Hausa": "To, ban adana ko ɗaya ba.",
                    "Igbo": "Ọ dị mma, echekwaghị m nke ọ bụla."},
    "still_waiting": {"English": "Still waiting: {list}. Say *yes* to save, or *no* to drop.",
                      "Pidgin": "E still dey wait: {list}. Talk *yes* make I save, or *no* make I leave am.",
                      "Yoruba": "Ó ṣì ń dúró: {list}. Sọ *bẹ́ẹ̀ni* tàbí *rárá*.",
                      "Hausa": "Har yanzu suna jira: {list}. Ka ce *eh* ko *a'a*.",
                      "Igbo": "Ka na-eche: {list}. Kwuo *ee* ma ọ bụ *mba*."},
    # a very big amount: read back in words, once, before it can be saved
    "big": {"English": "That is {w}. Is that right?", "Pidgin": "Na {w} be that. E correct?",
            "Yoruba": "Ìyẹn ni {w}. Ṣé bẹ́ẹ̀ ni?", "Hausa": "Wato {w}. Haka ne?", "Igbo": "Nke ahụ bụ {w}. Ọ bụ eziokwu?"},
    # profit is worked out by the book, never written in as a line
    "profit_info": {"English": "I work out your profit from what you sold and spent, so I don't save it as a line. Today your "
                               "book says: sales {s}, spending {e}, so {p}. Tell me what you sold and spent, and I will add them.",
                    "Pidgin": "Na me dey calculate your profit from wetin you sell and spend, so I no go save am as one line. "
                              "Today your book talk: sales {s}, spending {e}, so {p}. Tell me wetin you sell and spend, I go add am.",
                    "Yoruba": "Èmi ni mo ń ṣírò èrè rẹ láti inú ohun tí o tà àti ohun tí o ná, nítorí náà mi ò kọ ọ́ sílẹ̀ "
                              "bí ìlà kan. Lónìí ìwé rẹ sọ pé: títà {s}, ìnáwó {e}, èrè {p}. Sọ ohun tí o tà àti ohun tí o ná.",
                    "Hausa": "Ni nake lissafa ribarka daga abin da ka sayar da abin da ka kashe, don haka ban adana ta a "
                             "matsayin layi ba. Yau littafinka ya ce: ciniki {s}, kashewa {e}, saura {p}. Faɗa min abin da ka "
                             "sayar da abin da ka kashe.",
                    "Igbo": "Ana m agbakọ uru gị site n'ihe i rere na ihe i mefuru, ya mere anaghị m echekwa ya dị ka otu "
                            "ahịrị. Taa akwụkwọ gị na-ekwu: ahịa {s}, mmefu {e}, ya bụ {p}. Gwa m ihe i rere na ihe i mefuru."},
    # things TradeVoice can't see from here
    "cant_see": {"English": "I can't see that here. Send a photo of it with the + button, paste the list here, or tell me each one, like: "
                            "Mama Ngozi owes ₦5,000.",
                 "Pidgin": "I no fit see am for here. Send photo of am with the + button, paste the list here, or tell me one by one, like: "
                           "Mama Ngozi dey owe ₦5,000.",
                 "Yoruba": "Mi ò lè rí i níbí. Fi fọ́tò rẹ̀ ránṣẹ́ pẹ̀lú bọ́tìnnì +, lẹ àkọsílẹ̀ náà síbí, tàbí sọ wọ́n lọ́kọ̀ọ̀kan, bíi: "
                           "Mama Ngozi jẹ mí ₦5,000.",
                 "Hausa": "Ba zan iya ganin sa a nan ba. Aiko hotonsa da maɓallin +, liƙa jerin a nan, ko ka faɗa min ɗaya bayan ɗaya, kamar: "
                          "Mama Ngozi tana bina ₦5,000.",
                 "Igbo": "Enweghị m ike ịhụ ya ebe a. Ziga foto ya site na bọtịnụ +, mado ndepụta ahụ ebe a, ma ọ bụ gwa m otu otu, dị ka: "
                         "Mama Ngozi ji m ₦5,000."},
    "left_out": {"English": "I left out the other amount ({a} or {b}?). Say it on its own if you want it saved.",
                 "Pidgin": "I no use the other money ({a} or {b}?). Talk am alone if you wan make I save am.",
                 "Yoruba": "Mi ò lo owó kejì ({a} tàbí {b}?). Sọ ọ́ lọ́tọ̀ tí o bá fẹ́ kí n kọ ọ́ sílẹ̀.",
                 "Hausa": "Ban yi amfani da ɗayan kuɗin ba ({a} ko {b}?). Faɗe shi shi kaɗai idan kana so in adana.",
                 "Igbo": "Ejighị m ego nke ọzọ ({a} ma ọ bụ {b}?). Kwuo ya naanị ya ma ị chọrọ ka m chekwaa ya."},
    "check_amount": {"English": "Please check the amount.", "Pidgin": "Abeg check the money well.",
                     "Yoruba": "Jọ̀wọ́ ṣàyẹ̀wò iye owó náà.", "Hausa": "Da fatan ka duba adadin kuɗin.",
                     "Igbo": "Biko lelee ego ole ahụ."},
    "check_it": {"English": "Please check it before saving.", "Pidgin": "Abeg check am before you save.",
                 "Yoruba": "Jọ̀wọ́ ṣàyẹ̀wò rẹ̀ kí o tó kọ ọ́.", "Hausa": "Da fatan ka duba kafin ka adana.",
                 "Igbo": "Biko lelee ya tupu i chekwaa."},
    # asking again for just the unclear part (hearing.py): two hearing models disagreed, or one wasn't sure
    "amount_again": {"English": "I heard {a} or {b}. Say the amount again.",
                     "Pidgin": "I hear {a} or {b}. Talk the money again.",
                     "Yoruba": "Mo gbọ́ {a} tàbí {b}. Ẹ sọ iye owó náà lẹ́ẹ̀kan sí i.",
                     "Hausa": "Na ji {a} ko {b}. Sake faɗin kuɗin.",
                     "Igbo": "Anụrụ m {a} ma ọ bụ {b}. Kwuo ego ahụ ọzọ."},
    "amount_unclear": {"English": "I heard {a}, but not clearly. Say the amount again.",
                       "Pidgin": "I hear {a}, but e no clear. Talk the money again.",
                       "Yoruba": "Mo gbọ́ {a}, ṣùgbọ́n kò yé mi dáadáa. Ẹ sọ iye owó náà lẹ́ẹ̀kan sí i.",
                       "Hausa": "Na ji {a}, amma bai fito sosai ba. Sake faɗin kuɗin.",
                       "Igbo": "Anụrụ m {a}, mana o doghị anya. Kwuo ego ahụ ọzọ."},
    "name_again": {"English": "I didn't hear the name well. Say the customer's name again.",
                   "Pidgin": "I no hear the name well. Talk the customer name again.",
                   "Yoruba": "Mi ò gbọ́ orúkọ náà dáadáa. Ẹ sọ orúkọ oníbàárà náà lẹ́ẹ̀kan sí i.",
                   "Hausa": "Ban ji sunan sosai ba. Sake faɗin sunan mai siyan.",
                   "Igbo": "Anụghị m aha ahụ nke ọma. Kwuo aha onye ahịa ahụ ọzọ."},
    "how_much": {"English": "How much was it?", "Pidgin": "Na how much?", "Yoruba": "Èló ni?",
                 "Hausa": "Nawa ne?", "Igbo": "Ego ole?"},
    "saved": {"English": "Saved. {s}", "Pidgin": "I don save am. {s}", "Yoruba": "Mo ti kọ ọ́ sílẹ̀. {s}",
              "Hausa": "An adana. {s}", "Igbo": "Echekwala m ya. {s}"},
    "balance": {"English": " Now {who} owes you {m} in total.", "Pidgin": " Now {who} dey owe you {m} total.",
                "Yoruba": " Lápapọ̀, {who} jẹ ọ́ ní {m} báyìí.", "Hausa": " Yanzu jimlar bashin {who}: {m}.",
                "Igbo": " Ugbu a {who} ji gị {m} n'ozuzu."},
    "i_owe": {"English": " You now owe {who} {m} in total.", "Pidgin": " Now you dey owe {who} {m} total.",
              "Yoruba": " Lápapọ̀, o jẹ {who} ní {m} báyìí.", "Hausa": " Yanzu jimlar bashin {who} a kanka: {m}.",
              "Igbo": " Ugbu a i ji {who} {m} n'ozuzu."},
    "cancelled": {"English": "OK, I didn't save it.", "Pidgin": "No wahala, I no save am.",
                  "Yoruba": "Ó dáa, mi ò kọ ọ́ sílẹ̀.", "Hausa": "To, ban adana ba.", "Igbo": "Ọ dị mma, echekwaghị m ya."},
    "undone": {"English": "Removed: {s}", "Pidgin": "I don remove am: {s}", "Yoruba": "Mo ti yọ ọ́ kúrò: {s}",
               "Hausa": "Na cire: {s}", "Igbo": "Ewepụla m ya: {s}"},
    "nothing_to_undo": {"English": "There is nothing to undo. I can only remove what I saved in the last 10 minutes.",
                        "Pidgin": "Nothing dey to remove. Na only wetin I save for the last 10 minutes I fit remove.",
                        "Yoruba": "Kò sí nǹkan láti yọ kúrò. Ohun tí mo kọ sílẹ̀ ní ìṣẹ́jú 10 sẹ́yìn nìkan ni mo lè yọ.",
                        "Hausa": "Babu abin da zan cire. Abin da na ajiye a cikin minti 10 da suka wuce kawai zan iya cirewa.",
                        "Igbo": "Ọ dịghị ihe m ga-ewepụ. Naanị ihe m debere n'ime nkeji 10 gara aga ka m nwere ike iwepụ."},
    "after_save": {"English": "Sorry. I saved: {s} Say *undo* to remove it, or tell me what it should be.",
                   "Pidgin": "Sorry. I don save: {s} Talk *undo* make I remove am, or tell me how e suppose be.",
                   "Yoruba": "Ẹ má bínú. Mo ti kọ ọ́ sílẹ̀: {s} Sọ *undo* kí n yọ ọ́ kúrò, tàbí sọ bí ó ṣe yẹ kó rí.",
                   "Hausa": "Yi haƙuri. Na ajiye: {s} Ka ce *undo* in cire shi, ko ka faɗi yadda ya kamata.",
                   "Igbo": "Ndo. Edebere m: {s} Kwuo *undo* ka m wepụ ya, ma ọ bụ gwa m otu o kwesịrị ịdị."},
    "off_topic": {"English": "I can only help with your shop: what you sold or spent, who owes you, and your customers. "
                             "Try: How much did I sell today?",
                  "Pidgin": "Na only your shop matter I fit help: wetin you sell or spend, who dey owe you, and your "
                            "customers. Try: How much I sell today?",
                  "Yoruba": "Ọ̀rọ̀ ṣọ́ọ̀bù rẹ nìkan ni mo lè ràn ọ́ lọ́wọ́ lé lórí: ohun tí o tà tàbí ná, ẹni tó jẹ ọ́, àti "
                            "àwọn oníbàárà rẹ. Gbìyànjú: Èló ni mo tà lónìí?",
                  "Hausa": "Harkokin shagonka kawai zan iya taimaka maka da su: abin da ka sayar ko ka kashe, wanda ke "
                           "bin ka bashi, da abokan cinikinka. Gwada: Nawa na sayar yau?",
                  "Igbo": "Naanị ihe gbasara ụlọ ahịa gị ka m nwere ike inyere gị aka: ihe i rere ma ọ bụ i mefuru, "
                          "onye ji gị ụgwọ, na ndị ahịa gị. Nwaa: Ole ka m rere taa?"},
    "nothing_pending": {"English": "There is nothing waiting to be saved.", "Pidgin": "Nothing dey wait to save.",
                        "Yoruba": "Kò sí nǹkan tó ń dúró de ìkọsílẹ̀.", "Hausa": "Babu abin da ke jiran adanawa.",
                        "Igbo": "Ọ dịghị ihe na-eche ka e chekwaa ya."},
    "remind_set": {"English": "OK. {when} I'll remind you to collect {m} from {who}.",
                   "Pidgin": "No wahala. {when} I go remind you to collect {m} from {who}.",
                   "Yoruba": "Ó dáa. {when} màá rán ọ létí láti gba {m} lọ́wọ́ {who}.",
                   "Hausa": "To. {when} zan tunatar da kai ka karɓi {m} daga {who}.",
                   "Igbo": "Ọ dị mma. {when} m ga-echetara gị ịnata {m} n'aka {who}."},
    "remind_none": {"English": "{who} doesn't owe you anything now.", "Pidgin": "{who} no dey owe you anything now.",
                    "Yoruba": "{who} kò jẹ ọ́ ní nǹkankan báyìí.", "Hausa": "{who} ba shi da bashinka yanzu.",
                    "Igbo": "{who} ejighị gị ụgwọ ugbu a."},
    "remind_who": {"English": "Who should I remind you about?", "Pidgin": "Na who I go remind you about?",
                   "Yoruba": "Ta ni kí n rán ọ létí nípa rẹ̀?", "Hausa": "Wa zan tunatar da kai game da shi?",
                   "Igbo": "Onye ka m ga-echetara gị maka ya?"},
    "due": {"English": "Today: collect {m} from {who}.", "Pidgin": "Today: collect {m} from {who}.",
            "Yoruba": "Lónìí: gba {m} lọ́wọ́ {who}.", "Hausa": "Yau: karɓi {m} daga {who}.",
            "Igbo": "Taa: nata {m} n'aka {who}."},
    "not_sure": {"English": "Sorry, I didn't catch that. Try: Mama Tunde took 2 bags of rice, ₦45,000, she will pay Friday.",
                 "Pidgin": "Abeg, I no catch am. Try: Mama Tunde carry 2 bags of rice, ₦45,000, she go pay Friday.",
                 "Yoruba": "Má bínú, kò yé mi. Sọ ọjà tí o tà, gbèsè, tàbí béèrè nípa ìwé rẹ.",
                 "Hausa": "Yi haƙuri, ban gane ba. Faɗi abin da ka sayar, bashi, ko ka tambayi littafinka.",
                 "Igbo": "Ndo, aghọtaghị m. Gwa m ihe i rere, ụgwọ, ma ọ bụ jụọ maka akwụkwọ gị."},
}
SAY["which"] = {"English": "Which {n}? You have more than one.", "Pidgin": "Which {n}? You get pass one.",
                "Yoruba": "{n} wo? O ní ju ẹyọ kan lọ.", "Hausa": "Wanne {n}? Kana da fiye da ɗaya.",
                "Igbo": "{n} ole? I nwere karịa otu."}
SAY["did_you_mean"] = {"English": "Did you mean {who}? Say yes, or no if {n} is a new customer.",
                       "Pidgin": "Na {who} you mean? Talk yes, or no if {n} na new customer.",
                       "Yoruba": "Ṣé {who} lo ní lọ́kàn? Sọ bẹ́ẹ̀ni, tàbí rárá tí {n} bá jẹ́ oníbàárà tuntun.",
                       "Hausa": "{who} kake nufi? Ka ce eh, ko a'a idan {n} sabon abokin ciniki ne.",
                       "Igbo": "Ọ bụ {who} ka ị na-ekwu? Sị ee, ma ọ bụ mba ma ọ bụrụ na {n} bụ onye ahịa ọhụrụ."}
# usual price (code works it out from the trader's own sales): a missed or extra zero is caught before saving
SAY["price_check"] = {
    "English": "You said {said} for {what}, but you usually sell {item} at {usual}{per}. Did you mean {guess}? "
               "Say the right amount, or say yes to keep {said}.",
    "Pidgin": "You talk {said} for {what}, but you dey usually sell {item} {usual}{per}. You mean {guess}? "
              "Talk the correct amount, or talk yes make I keep {said}.",
    "Yoruba": "O sọ {said} fún {what}, ṣùgbọ́n o máa ń ta {item} ní {usual}{per}. Ṣé {guess} lo fẹ́ sọ? "
              "Sọ iye tó tọ́, tàbí sọ bẹ́ẹ̀ni láti fi {said} sílẹ̀.",
    "Hausa": "Ka ce {said} na {what}, amma kana sayar da {item} {usual}{per}. {guess} kake nufi? "
             "Faɗi adadin da ya dace, ko ka ce eh don a bar {said}.",
    "Igbo": "I kwuru {said} maka {what}, mana ị na-ere {item} {usual}{per}. Ọ bụ {guess} ka ị chọrọ ịsị? "
            "Kwuo ego ziri ezi, ma ọ bụ sị ee ka m debe {said}."}
SAY["per_unit"] = {"English": " a {u}", "Pidgin": " for one {u}", "Yoruba": " fún {u} kan", "Hausa": " kowane {u}",
                   "Igbo": " otu {u}"}
SAY["per_each"] = {"English": " each", "Pidgin": " each", "Yoruba": " ọ̀kọ̀ọ̀kan", "Hausa": " kowanne",
                   "Igbo": " otu ọ bụla"}
SAY["new_customer"] = {"English": "New customer", "Pidgin": "New customer", "Yoruba": "Oníbàárà tuntun",
                       "Hausa": "Sabon abokin ciniki", "Igbo": "Onye ahịa ọhụrụ"}
SAY["owes"] = {"English": "owes {m}", "Pidgin": "dey owe {m}", "Yoruba": "jẹ {m}", "Hausa": "bashi {m}",
               "Igbo": "ji {m}"}
SAY["last"] = {"English": "last {d}", "Pidgin": "last {d}", "Yoruba": "{d}", "Hausa": "{d}", "Igbo": "{d}"}

WHEN = {"today": {"English": "Today,", "Pidgin": "Today,", "Yoruba": "Lónìí,", "Hausa": "Yau,", "Igbo": "Taa,"},
        "tomorrow": {"English": "Tomorrow,", "Pidgin": "Tomorrow,", "Yoruba": "Lọ́la,", "Hausa": "Gobe,",
                     "Igbo": "Echi,"},
        "day": {"English": "On {d},", "Pidgin": "On {d},", "Yoruba": "Ní {d},", "Hausa": "Ran {d},", "Igbo": "N'{d},"}}


def new_state():
    return {"pending": None, "pending_text": "", "last_customer": None, "people": [], "lang": "English"}


def _mention(state, name):
    """Remember who we talked about, newest first (for "her", "him", "am")."""
    if name:
        state["last_customer"] = name
        people = [p for p in state.setdefault("people", []) if ledger.customer_key(p) != ledger.customer_key(name)]
        state["people"] = [name] + people[:9]


def _pronoun_person(text, state, owes_me=False, today=None):
    """"her" = the last woman we talked about, "him" = the last man, "am/them" = the last person.
    owes_me: only people who owe the trader (for reminders)."""
    t = fold(text)
    if not PRONOUN.search(t):
        return None
    people = state.get("people") or ([state["last_customer"]] if state.get("last_customer") else [])
    if re.search(r"\b(she|her|ita)\b", t):
        people = [p for p in people if tts._female(p)]
    elif re.search(r"\b(he|him|shi)\b", t):
        people = [p for p in people if not tts._female(p)]
    if owes_me:
        owing = {ledger.customer_key(d["customer"]) for d in ledger.debtors(today)}
        people = [p for p in people if ledger.customer_key(p) in owing]
    return people[0] if people else None


def _money(x):
    return f"₦{x:,.0f}"


def _lang(text, state):
    lang = askbook.guess_language(text)
    prefer = state.get("prefer")
    # nothing in the words says which language (e.g. "hi", Yoruba heard without tone marks): use the one the
    # trader chose, so picking Yoruba really means Yoruba replies
    if lang == "English" and prefer and prefer != "English":
        return prefer
    # a bare "yes"/"ok"/"45k" says nothing about language: keep the one we were talking in
    if len(fold(text).split()) <= 2 and lang in ("English", "Pidgin"):
        return state.get("lang") or lang
    return lang


def _known_name(text, state, vocab, owes_me=False, today=None):
    """Who the message is about: a name from the book (full or part), else "her/him/am" = the last person."""
    nick = _nick_in(text)
    if nick:
        return nick
    name = askbook.find_name(text, vocab.get("names"))
    if name:
        return name
    return _pronoun_person(text, state, owes_me=owes_me, today=today)


def _nick_in(text):
    """A name the trader taught it, said in this message ("Mama T" = Mama Tunde): the customer's book name."""
    t = fold(text)
    for nick, cid in sorted(ledger.recall("nick").items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?<![\w]){re.escape(nick)}(?![\w])", t) and (c := ledger.get_customer(int(cid))):
            return c["name"]
    return None


def _full_name(asked, people):
    """"Alhaji" -> "Alhaji Sani" when only one person in `people` fits."""
    fits = [p["customer"] for p in people if askbook.same_person(asked, p["customer"])]
    return fits[0] if len(fits) == 1 else asked


def _named(text):
    """Greetings and thanks use the trader's name: "Hello. I'm your book…" -> "Hello, Ada. I'm your book…"."""
    import accounts
    name = accounts.trader().get("name")
    if not name or "." not in text:
        return text
    head, rest = text.split(".", 1)
    return f"{head}, {name}.{rest}"


def _out(text, lang, spoken=None, english=None):
    return {"text": text, "spoken": spoken or text, "lang": lang,
            "english": english if lang != "English" else None}


# ---------------------------------------------------------------- the four kinds of message

def _choices(matches, name, lang, today):
    """Buttons to tell same-name customers apart by what matters: balance and last activity."""
    out = []
    for m in matches[:4]:
        s = ledger.customer_summary(m["id"], today) or {}
        bits = [m["name"], SAY["owes"][lang].format(m=_money(s.get("owes_me", 0)))]
        if s.get("last_at"):
            bits.append(SAY["last"][lang].format(d=dt.date.fromisoformat(s["last_at"][:10]).strftime("%d %b").lstrip("0")))
        if s.get("phone"):
            bits.append(s["phone"])
        out.append((f"cust:{m['id']}", " · ".join(bits)))
    out.append(("cust:new", f"+ {SAY['new_customer'][lang]}: {name}"))
    return out


def _ask_which(state, name, matches, lang, today, purpose, text="", how="name"):
    """"Which Feranmi?" (several fit), or "Did you mean Hajiya Amina?" (a name close to one in the book)."""
    state["choose"] = {"ids": [m["id"] for m in matches], "name": name, "for": purpose, "text": text, "how": how}
    if how == "sounds":
        who = matches[0]["name"]
        out = _out(SAY["did_you_mean"][lang].format(who=who, n=name), lang,
                   english=SAY["did_you_mean"]["English"].format(who=who, n=name))
    else:
        out = _out(SAY["which"][lang].format(n=name), lang, english=SAY["which"]["English"].format(n=name))
    out["choices"] = _choices(matches, name, lang, today)
    return out


def _chosen(t, state):
    """'cust:12' / 'cust:new' / '1' / '2' / 'new' -> customer id, 'new', or None."""
    ids = state["choose"]["ids"]
    if YES.match(t) and len(ids) == 1:          # "Did you mean Hajiya Amina?" "Yes"
        return ids[0]
    if NO.match(t) and state["choose"].get("how") == "sounds":
        return "new"                            # "No": a new customer with the name they said
    said = [i for i in ids if (c := ledger.get_customer(i)) and fold(c["name"]) in t]
    if len(said) == 1:                          # they said the name: "Mama Titi"
        return said[0]
    m = re.match(r"^cust:(\d+|new)$", t) or re.match(r"^(\d)$", t) or re.match(r"^(new|\+.*)$", t)
    if not m:
        return None
    v = m.group(1)
    if v == "new" or v.startswith("+"):
        return "new"
    if t.startswith("cust:"):
        return int(v) if int(v) in ids else None
    return ids[int(v) - 1] if 1 <= int(v) <= len(ids) else None


def _pick_customer(rec, state, lang, today, text):
    """Link a draft to ONE customer: same name twice -> ask; one -> that one; none -> new customer on save."""
    name = rec.get("customer")
    if not name or rec.get("customer_id"):
        return None
    matches, how = ledger.match_customers(name)
    if how == "sounds":   # close to someone in the book: ask before making a second customer
        return _ask_which(state, name, matches[:1], lang, today, "record", text, how="sounds")
    exact = [m for m in matches if ledger.customer_key(m["name"]) == ledger.customer_key(name)]
    pool = exact or matches
    if len(pool) > 1:
        return _ask_which(state, name, pool, lang, today, "record", text, how=how)
    if len(pool) == 1:
        rec["customer_id"], rec["customer"] = pool[0]["id"], pool[0]["name"]
    return None


def price_check(rec):
    """A missed or extra zero, caught from the trader's own usual price for the item (all maths here, in code)."""
    if rec.get("type") not in ("sale", "credit_sale") or not rec.get("item") or rec.get("amount") in (None, ""):
        return None
    u = ledger.usual_price(rec["item"])
    if not u:
        return None
    qty = float(rec.get("quantity") or 1)
    expected, said = u["price"] * qty, float(rec["amount"])
    if expected <= 0 or 0.2 < said / expected < 5:
        return None
    guess = next((said * f for f in (10, 0.1, 100, 0.01) if 0.7 <= said * f / expected <= 1.4), expected)
    return {"said": said, "guess": round(guess), "usual": u["price"], "unit": u["unit"]}


def _price_text(rec, chk, lang):
    per = (SAY["per_unit"][lang].format(u=chk["unit"]) if chk["unit"] else SAY["per_each"][lang])
    what = _what({"quantity": rec.get("quantity"), "unit": rec.get("unit"), "item": rec["item"]})
    return SAY["price_check"][lang].format(said=_money(chk["said"]), what=what, item=rec["item"],
                                           usual=_money(chk["usual"]), per=per, guess=_money(chk["guess"]))


def _confirm(state, today):
    rec = state["pending"]
    if rec.pop("_create", False) or (rec.get("customer") and not rec.get("customer_id")):
        rec["customer_id"] = (ledger.create_customer(rec["customer"]) if rec.get("_new_forced")
                              else ledger.resolve_customer(rec["customer"]))
    rec.pop("_new_forced", None)
    said = rec.pop("_said", None)
    rid = ledger.add_entry(rec, raw_text=said if said is not None else state.get("pending_text", ""),
                           engine=rec.pop("_engine", "chat"))
    state["pending"], lang = None, state["lang"]
    theirs = mine = None
    if rec.get("customer"):
        theirs, mine = ledger.balance_with(today=today, customer_id=rec.get("customer_id"))
        _mention(state, rec["customer"])
    sentence = tts.entry_sentence(rec, lang, money=_money)
    extra = extra_en = ""
    if rec["type"] in ("credit_sale", "payment_received") and theirs and theirs != rec["amount"]:
        extra = SAY["balance"][lang].format(who=rec["customer"], m=_money(theirs))
        extra_en = SAY["balance"]["English"].format(who=rec["customer"], m=_money(theirs))
    if rec["type"] in ("credit_purchase", "payment_made") and mine and mine != rec["amount"]:
        extra = SAY["i_owe"][lang].format(who=rec["customer"], m=_money(mine))
        extra_en = SAY["i_owe"]["English"].format(who=rec["customer"], m=_money(mine))
    bal = theirs if rec["type"] in ("credit_sale", "payment_received") else mine
    out = _out(SAY["saved"][lang].format(s=sentence) + extra, lang,
               spoken=tts.confirmation_text(rec, lang, balance=bal, saved=True),
               english=SAY["saved"]["English"].format(s=tts.entry_sentence(rec, "English", money=_money)) + extra_en)
    out["saved"] = True   # the page shows "Saved" with Undo (it never guesses from the words)
    # "undo" / "no, that's wrong" later in the chat: what this message saved (all of a "save it all")
    state["last_saved"] = [s for s in state.get("last_saved") or [] if s["turn"] == state.get("turn")][-9:] + [
        {"id": rid, "turn": state.get("turn"), "at": time.time(), "line": sentence, "rec": dict(rec)}]
    return out


# ---------------------------------------------------------------- after a save: undo, "no, that's wrong"
UNDO = re.compile(r"^\s*(?:please\s+|abeg\s+)?(undo|undo (it|that|am|the last one)|delete (it|that|am|the last one|last one|"
                  r"that one)|remove (it|that|am|the last one|the last|last one|that one)|cancel (that one|the last one|"
                  r"last one|the last)|take (it|am) (back|out)|comot am|comot (that|the last) one|pa a re|yo o kuro|"
                  r"cire shi|soke shi|wepu ya|hapu ya)\W*$")
WRONG_AFTER = re.compile(r"^\s*(no|nope|wrong|not correct|not right|mistake|that'?s (wrong|not right|not correct|a mistake)|"
                         r"you (made a mistake|got it wrong|saved it wrong)|no be so|no be am|rara|ko ri bee|a'?a|"
                         r"ba haka ba|mba|o bughi ya)\b")
UNDO_MINUTES = 10


def _last_saved(state):
    ls = [s for s in state.get("last_saved") or [] if time.time() - s["at"] < UNDO_MINUTES * 60]
    return ls


def _after_save(text, t, lang, state, today):
    """Right after a save: "undo" removes it; "no, it's 3 million" takes it back to change it; "no, that's wrong" says
    what was saved and how to fix it (never a sales summary)."""
    last = _last_saved(state)
    if UNDO.match(t):
        if not last:
            return _out(SAY["nothing_to_undo"][lang], lang, english=SAY["nothing_to_undo"]["English"])
        for s in last:
            ledger.delete_entry(s["id"])
        state["last_saved"] = []
        s_ = " ".join(x["line"] for x in last)
        return _out(SAY["undone"][lang].format(s=s_), lang)
    if not last or not WRONG_AFTER.match(t):
        return None
    if parse_amount(text) is not None and len(last) == 1:   # "no, 3 million": the saved line comes back to change
        ledger.delete_entry(last[0]["id"])
        rec = {k: v for k, v in last[0]["rec"].items() if not k.startswith("_")}
        state["last_saved"], state["pending"], state["pending_text"] = [], rec, ""
        return _correct(text, lang, state, today)
    s_ = " ".join(x["line"] for x in last)
    return _out(SAY["after_save"][lang].format(s=s_), lang, english=SAY["after_save"]["English"].format(s=s_))


# a message that fixes the draft waiting for "yes" (not a new record): "2000 no be 20000", "I mean 25k", "make am rice"
CORRECT = re.compile(r"\b(no be|not|i mean|i talk say|i said|correct(ion)?|change (it|am)|make (it|am)|mistake|sorry|"
                     r"abeg|rara|ko se|kii se|a'?a|ba haka|mba|o bughi|instead)\b")


def _correct(text, lang, state, today):
    """Change only what the trader said again; keep the rest of the draft."""
    rec, new = state["pending"], rule_extract(text, today)
    amount = parse_amount(text)
    if amount is not None:
        rec["amount"] = amount
        if rec.get("_reask") == "amount":
            rec.pop("_reask")
    nc = new.get("customer")
    if nc and not (rec.get("customer") and _same(nc, rec["customer"])):
        rec["customer"], rec["customer_id"] = nc, None
    for k in ("item", "quantity", "unit", "due_date"):
        if new.get(k):
            rec[k] = new[k]
    if type_is_explicit(text):
        rec["type"] = new["type"]
    rec["note"], rec["confidence"] = None, max(rec.get("confidence") or 0, 0.8)
    state["pending_text"] = (state.get("pending_text", "") + " / " + text).strip(" /")
    if rec.get("amount") in (None, ""):
        return _out(SAY["how_much"][lang], lang, english=SAY["how_much"]["English"])
    return _heard(rec, lang, updated=True)


_NUM_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "twenty", "fifty", "hundred",
              "thousand", "million", "millions", "k", "naira", "too", "also", "sef", "own", "for", "of"}


def _next_person(text, rec):
    """'Tayo 3 million' / 'tayo 3m' (a known customer) while someone else's draft waits: the name of a new person,
    not a fix. Lower-case words that aren't a customer yet stay a fix ("rice 3000" changes the item)."""
    m = re.match(r"\s*([^\W\d_][^\W\d_']*(?:\s+[^\W\d_][^\W\d_']*)?)\s+(?:too\s+|also\s+)?[₦n]?\s?\d", text or "", re.I)
    if not m or not rec.get("customer") or CORRECT.search(fold(m.group(1))) or fold(m.group(1)).split()[0] in _NUM_WORDS:
        return False
    who = m.group(1)
    if _same(who, rec["customer"]):
        return False
    known = {fold(n) for n in ledger.known_words(200)["names"]}
    return who[:1].isupper() or fold(who) in known


def _like_before(rec, old, said):
    """A short "and …" with no verb copies the kind of record before it: the words before the amount are the next
    person (when the one before had a person) or the next item ("sold rice 15k" … "and beans 3k")."""
    rec["type"] = old["type"]
    words = []
    for w in said.split():
        if re.match(r"[₦n]?\d", w, re.I) or fold(w) in _NUM_WORDS:
            break
        words.append(w.strip(",.;:"))
    words = [w for w in words if w][:3]
    if not words:
        return
    if old.get("customer") and not rec.get("customer"):
        rec["customer"] = " ".join(w if w[:1].isupper() else w.title() for w in words)
        rec["customer_id"] = None
        for k in ("item", "quantity", "unit"):    # "tayo" is the person, not what was sold
            if rec.get(k) and fold(str(rec[k])) in {fold(w) for w in words}:
                rec[k] = None
    elif not old.get("customer") and not rec.get("item"):
        rec["item"] = " ".join(words).lower()


def _many(text, lang, today):
    """Many records in one message: N-ATLaS reads every one, code checks them, the trader ticks and saves them in
    the line check (nothing is saved here, no draft). With no AI, it says so instead of guessing one number."""
    import photo

    recs, meta = read_list(text, today)
    if not recs:
        out = _out(photo.LIST_SAY["cant"][lang], lang, english=photo.LIST_SAY["cant"]["English"])
        return out
    rows = photo.list_rows(recs)
    out = _out(photo.list_summary(rows, meta["missed"], lang), lang,
               english=photo.list_summary(rows, meta["missed"]) if lang != "English" else None)
    out["rows"], out["act"] = photo.plain_checks(rows, lang), "scan"
    return out


def _same(a, b):
    return bool(askbook.same_person(a, b) or askbook.same_person(b, a))


def _is_correction(text, t, state):
    rec = state.get("pending")
    if not rec:
        return False
    if AND_MORE.search(t) and not CORRECT.search(t):
        return False     # "and Tayo 3 million": one more record, not a fix of the one waiting
    if _next_person(text, rec):
        return False     # "Tayo 3 million" while Mike's draft waits: Tayo is someone else
    new_customer = rule_extract(text).get("customer")
    other_person = bool(new_customer and rec.get("customer") and not _same(new_customer, rec["customer"]))
    # "Mama Tunde has not paid 20k" while Iya Bisi's draft waits = a new record, not a fix
    if CORRECT.search(t) and (not other_person or parse_amount(text) is None):
        return True
    # just a number (or "make am 25k") while a draft waits = the right amount
    return parse_amount(text) is not None and len(t.split()) <= 4 and not new_customer


def _record(text, lang, state, vocab, today, heard=None):
    old = state.get("pending") if state.get("pending") and state["pending"].get("amount") not in (None, "") else None
    # a list said one after the other waits together ("Dino owes me 5m" … "and Mike owes me 300k" … "save it all");
    # on the card screen (one card at a time) a new note still replaces a card nobody answered
    keep = bool(old) and (state.get("queue_ok") or AND_MORE.search(fold(text)))
    had_draft = bool(old) and not keep
    if keep:
        old["_said"] = state.get("pending_text", "")    # each record keeps the words it was said in
        state["queue"] = ((state.get("queue") or []) + [old])[-5:]
    said = re.sub(r"^\s*(and|also|plus|then|another one|another|again|&|\+)\b[\s,]*", "", text, flags=re.I) or text
    cands = amount_doubt(said)   # "50,0000" / "20000k": two readings, ask instead of guessing
    if cands and _other_amount(said, cands):
        # "No 500,000k and spent 130,000": the clear part is the record; the garbled number is said to be left out
        said = _without_doubt(said)
    rec, meta = extract(said, today=today, vocab=vocab)
    if keep and (AND_MORE.search(fold(text)) or _next_person(text, old)) and not EVENT.search(fold(said)):
        _like_before(rec, old, said)   # "and Tayo 3 million" after "Mike owes me 2m": the same kind, for Tayo
    if cands:
        if rec.get("amount") in (None, "") or float(rec["amount"]) in cands:
            rec["amount"] = rec.get("amount") or cands[0]
            heard = dict(heard or {}, amounts=sorted(set(cands) | set((heard or {}).get("amounts") or [])))
        else:
            rec["_left_out"] = cands      # the record used another number: say the doubtful one was left out
    if not rec.get("customer"):
        rec["customer"] = _pronoun_person(text, state, today=today)  # "she don pay 10k" = who we talked about
    rec["_engine"] = meta.get("engine", "chat")
    state["pending"], state["pending_text"] = rec, text
    _mention(state, rec.get("customer"))
    ask = _pick_customer(rec, state, lang, today, text)
    if ask:
        return _with_waiting(ask, state, lang)
    if rec.get("amount") in (None, ""):
        return _with_waiting(_out(SAY["how_much"][lang], lang, english=SAY["how_much"]["English"]), state, lang)
    again = _ask_again(rec, heard, lang)
    if again:
        return _with_waiting(again, state, lang)
    out = _heard(rec, lang, note=rec.get("note"), dropped=had_draft)
    left = rec.pop("_left_out", None)
    if left:
        kw = {"a": _money(left[0]), "b": _money(left[-1])}
        out["text"] += "\n" + SAY["left_out"][lang].format(**kw)
        out["english"] = (out.get("english") or "") + "\n" + SAY["left_out"]["English"].format(**kw) if out.get("english") else None
    return _with_waiting(out, state, lang)


# ---------------------------------------------------------------- several drafts, profit, garbled and big amounts

def _drafts(state):
    """Everything waiting for "yes", oldest first (the queue, then the draft being worked on)."""
    q = [d for d in state.get("queue") or [] if d.get("amount") not in (None, "")]
    p = state.get("pending")
    return q + ([p] if p and p.get("amount") not in (None, "") else [])


def _label(rec):
    return f"{rec.get('customer') or rec.get('item') or ''} {_money(rec['amount'])}".strip()


def _with_waiting(out, state, lang):
    """When earlier drafts wait too, the reply ends with the whole list: '2 waiting to save: Dino ₦5,000,000, …'."""
    if not state.get("queue"):
        return out
    ds = _drafts(state)
    kw = {"n": len(ds), "list": ", ".join(_label(d) for d in ds)}
    out["text"] += "\n" + SAY["waiting"][lang].format(**kw)
    if out.get("english"):
        out["english"] += "\n" + SAY["waiting"]["English"].format(**kw)
    out["spoken"] = (out.get("spoken") or "") + " " + _say_amounts(SAY["waiting"][lang].format(**kw).replace("*", ""))
    return out


def _combine(outs, lang):
    if len(outs) == 1:
        return outs[0]
    head = SAY["saved"][lang].split("{s}")[0]
    head_en = SAY["saved"]["English"].split("{s}")[0]
    lines = [o["text"][len(head):] if o["text"].startswith(head) else o["text"] for o in outs]
    lines_en = [(o.get("english") or o["text"]) for o in outs]
    lines_en = [x[len(head_en):] if x.startswith(head_en) else x for x in lines_en]
    out = _out(SAY["saved_n"][lang].format(n=len(outs)) + "\n" + "\n".join(lines), lang,
               spoken=" ".join(o.get("spoken") or "" for o in outs),
               english=SAY["saved_n"]["English"].format(n=len(outs)) + "\n" + "\n".join(lines_en))
    out["saved"] = True
    return out


def _save_all(state, today):
    """'yes' / 'save it all': every waiting draft is saved, in the order it was said."""
    lang = state["lang"]
    p = state.get("pending")
    unfinished = p if p and p.get("amount") in (None, "") else None   # still needs "How much?": keeps waiting
    ds, outs = _drafts(state), []
    state["queue"] = []
    for d in ds:
        state["pending"] = d
        outs.append(_confirm(state, today))
    state["pending"] = unfinished
    return _combine(outs, lang)


def _save_only(t, state, today):
    lang, ds = state["lang"], _drafts(state)
    hit = [d for d in ds if d.get("customer") and fold(d["customer"]) in t] or \
          [d for d in ds if d.get("item") and fold(d["item"]) in t]
    if not hit:
        return None
    rest = [d for d in ds if all(d is not h for h in hit)]
    outs = []
    for d in hit:
        state["pending"] = d
        outs.append(_confirm(state, today))
    state["queue"], state["pending"] = rest[:-1], (rest[-1] if rest else None)
    out = _combine(outs, lang)
    if rest:
        kw = {"list": ", ".join(_label(d) for d in rest)}
        out["text"] += "\n" + SAY["still_waiting"][lang].format(**kw)
        if out.get("english"):
            out["english"] += "\n" + SAY["still_waiting"]["English"].format(**kw)
    return out


def _profit_info(lang, today):
    d = ledger.day_summary(today)
    kw = {"s": _money(d["sales"]), "e": _money(d["expenses"]), "p": _money(d["profit"])}
    return _out(SAY["profit_info"][lang].format(**kw), lang, spoken=_say_amounts(SAY["profit_info"][lang].format(**kw)),
                english=SAY["profit_info"]["English"].format(**kw))


def amount_doubt(text):
    """Two honest readings of a garbled amount, or None: '50,0000' -> ₦500,000 or ₦50,000 (one zero too many?);
    '20000k' / '500,000k' -> the number or a thousand times it (k after a full number)."""
    m = re.search(r"(?<![\d,.])(\d{1,3}),(\d{4,})(?![\d,])", text or "")
    if m:
        whole = float(m.group(1) + m.group(2))
        cut = float(m.group(1) + m.group(2)[:3])
        return sorted({whole, cut}, reverse=True)
    m = re.search(r"(?<![\d,.])(\d{1,3}(?:,\d{3})+|\d{4,})\s*k\b", text or "", re.I)
    if m:
        n = float(m.group(1).replace(",", ""))
        return sorted({n, n * 1000}, reverse=True)
    return None


_DOUBT = r"(?<![\d,.])(?:\d{1,3},\d{4,}(?![\d,])|(?:\d{1,3}(?:,\d{3})+|\d{4,})\s*k\b)"


def _without_doubt(text):
    return re.sub(r"\s+", " ", re.sub(_DOUBT, " ", text, count=1, flags=re.I)).strip()


def _other_amount(text, cands):
    """Is there another, clear amount in the message besides the garbled one?"""
    from extract import _amount_values
    return bool(_amount_values(_without_doubt(text)) - set(cands))


def _big(rec):
    """Above ₦1,000,000 and more than 10 times the biggest line in the book: read it back in words first."""
    try:
        a = float(rec.get("amount") or 0)
    except (TypeError, ValueError):
        return False
    return a >= 1_000_000 and a > 10 * ledger.biggest_amount()


def _ask_again(rec, heard, lang):
    """Two hearing models heard different amounts, or one wasn't sure of the amount or of a new name: ask for just
    that part. The draft waits (the card marks the part); a bare amount or name in reply fixes it."""
    if not heard:
        return None
    amount = float(rec["amount"])
    others = [a for a in heard.get("amounts") or [] if a != amount]
    if others or heard.get("unsure_amount"):
        rec["_reask"] = "amount"
        key, v = ("amount_again", {"a": _money(amount), "b": _money(others[0])}) if others else \
            ("amount_unclear", {"a": _money(amount)})
        said = SAY[key][lang].format(**v)
        return _out(said, lang, spoken=_say_amounts(said), english=SAY[key]["English"].format(**v))
    name = rec.get("customer")
    if name and not rec.get("customer_id") and set(heard.get("unsure_words") or []) & set(fold(name).split()):
        rec["_reask"] = "customer"     # a new name the model wasn't sure of (names in the book are hints already)
        return _out(SAY["name_again"][lang], lang, english=SAY["name_again"]["English"])
    return None


def _name_again(text, lang, state, today):
    rec = state["pending"]
    name = extract_customer(text) or " ".join(w.capitalize() for w in re.sub(r"[^\w\s'-]", " ", text).split()[:4])
    rec.pop("_reask", None)
    rec["customer"], rec["customer_id"] = name, None
    state["pending_text"] = (state.get("pending_text", "") + " / " + text).strip(" /")
    _mention(state, name)
    ask = _pick_customer(rec, state, lang, today, state["pending_text"])
    return ask or _heard(rec, lang, updated=True)


def _say_amounts(text):
    import assistant

    return assistant.spoken(text)


def over_limit_text(lim, lang):
    return SAY["over_limit"].get(lang, SAY["over_limit"]["English"]).format(
        who=lim["name"], bal=_money(lim["balance"]), after=_money(lim["after"]), lim=_money(lim["limit"]))


def draft_limit(rec):
    """Limit check for a draft credit sale (by id, or by the exact name already in the book)."""
    if rec.get("type") != "credit_sale" or rec.get("amount") in (None, "") or not rec.get("customer"):
        return None
    cid = rec.get("customer_id")
    if not cid:
        same = [c for c in ledger.find_customers(rec["customer"])
                if ledger.customer_key(c["name"]) == ledger.customer_key(rec["customer"])]
        cid = same[0]["id"] if len(same) == 1 else None
    return ledger.limit_check(cid, rec["amount"]) if cid else None


LIMIT = re.compile(r"\blimit\b|\bno give .{1,40}? pass\b|\bowe (?:me )?more than\b|\bnot (?:owe )?more than\b")


def _set_limit(text, lang, state, vocab):
    who = _known_name(text, state, vocab) or extract_customer(text)
    if not who:
        return _out(SAY["limit_who"][lang], lang, english=SAY["limit_who"]["English"])
    same = [c for c in ledger.find_customers(who) if ledger.customer_key(c["name"]) == ledger.customer_key(who)]
    cid = same[0]["id"] if same else ledger.create_customer(who)
    amount = parse_amount(text)
    off = amount is None and re.search(r"\b(no limit|remove|comot|off)\b", fold(text))
    if amount is None and not off:
        return _out(SAY["how_much"][lang], lang, english=SAY["how_much"]["English"])
    ledger.update_customer(cid, credit_limit=None if off else float(amount))
    _mention(state, who)
    if off:
        return _out(SAY["limit_off"][lang].format(who=who), lang, english=SAY["limit_off"]["English"].format(who=who))
    said = SAY["limit_set"][lang].format(who=who, lim=_money(amount))
    return _out(said, lang, spoken=_say_amounts(said), english=SAY["limit_set"]["English"].format(who=who, lim=_money(amount)))


STATEMENT_RX = re.compile(r"\bstatement\b|\bsend .{1,30} (?:account|record)\b|\bakosile\b|\bbayanin asusu\b")


def _statement(text, lang, state, vocab, shop):
    """"Send Mama Tunde her statement": the statement to forward (also drafted in her conversation)."""
    import extras

    who = _known_name(text, state, vocab) or state.get("last_customer")
    same = [c for c in ledger.find_customers(who or "") if ledger.customer_key(c["name"]) == ledger.customer_key(who or "")]
    if not same:
        return _out(SAY["remind_who"][lang], lang, english=SAY["remind_who"]["English"])
    cust = same[0]
    book = os.path.basename(ledger.book_path())[:-3] if ledger.book_path().endswith(".db") else ""
    trader = state.get("phone") or (book if book.isdigit() else None)   # books/<trader number>.db
    msg = extras.customer_statement(cust["id"], shop, lang, os.getenv("PUBLIC_URL", ""), trader)
    ledger.add_message(cust["id"], msg, sender="tradevoice", kind="statement", status="draft")
    phone = "".join(ch for ch in (cust.get("phone") or "") if ch.isdigit())
    if phone.startswith("0") and len(phone) == 11:
        phone = "234" + phone[1:]
    _mention(state, cust["name"])
    out = _out(SAY["statement_ready"][lang].format(who=cust["name"]), lang,
               english=SAY["statement_ready"]["English"].format(who=cust["name"]))
    out["message"], out["link"] = msg, f"https://wa.me/{phone}?text=" + urllib.parse.quote(msg)
    return out


def friendly_note(note, lang):
    """The guards' technical reason goes to the log; the trader gets one short line in their language, and only
    when something really needs a second look (an amount the rules fixed for sure needs none)."""
    if not note:
        return None
    print(f"draft note: {note}")
    if not re.search(r"check|not said|no amount|unreadable|two things|unclear|not sure", note, re.I):
        return None
    return SAY["check_amount" if "amount" in note.lower() else "check_it"][lang]


def _heard(rec, lang, note=None, updated=False, dropped=False):
    written = SAY["heard"][lang].format(s=tts.entry_sentence(rec, lang, money=_money))
    if updated:
        written = SAY["updated"][lang] + " " + written
    friendly = friendly_note(note, lang)
    if friendly:
        written += "\n" + friendly
    if dropped:
        written += "\n" + SAY["dropped"][lang]
    spoken = tts.confirmation_text(rec, lang, saved=False)
    lim = draft_limit(rec)
    if lim and lim["over"]:  # stop over-lending: said before anything is saved, in writing and out loud
        warn = over_limit_text(lim, lang)
        written += "\n" + warn
        spoken = _say_amounts(warn) + " " + spoken
    big = not price_check(rec) and _big(rec)
    rec["_big"] = big
    if big:   # "That is five million naira. Is that right?" (yes keeps it; the card marks the amount)
        w = tts.naira_words(float(rec["amount"])) if lang in ("English", "Pidgin") else _money(rec["amount"])
        written += "\n" + SAY["big"][lang].format(w=w)
        spoken = spoken + " " + SAY["big"][lang].format(w=w if lang in ("English", "Pidgin") else _say_amounts(w))
    chk = price_check(rec)
    rec["_price"] = chk
    if chk:   # "You said ₦4,500 … Did you mean ₦45,000?": the trader says the right amount, or yes to keep it
        warn = _price_text(rec, chk, lang)
        written += "\n" + warn
        spoken = _say_amounts(warn)
    english = SAY["heard"]["English"].format(s=tts.entry_sentence(rec, "English", money=_money))
    if updated:
        english = SAY["updated"]["English"] + " " + english
    if dropped:
        english += "\n" + SAY["dropped"]["English"]
    if lim and lim["over"]:
        english += "\n" + over_limit_text(lim, "English")
    if chk:
        english += "\n" + _price_text(rec, chk, "English")
    if big:
        english += "\n" + SAY["big"]["English"].format(w=tts.naira_words(float(rec["amount"])))
    return _out(written, lang, spoken=spoken, english=english)


def _when(text, today):
    if TOMORROW_LOCAL.search(fold(text)):
        return today + dt.timedelta(days=1)
    due = parse_due(text, today)
    return dt.date.fromisoformat(due) if due else today


def _when_say(day, today, lang):
    if day == today:
        return WHEN["today"][lang]
    if day == today + dt.timedelta(days=1):
        return WHEN["tomorrow"][lang]
    return WHEN["day"][lang].format(d=day.strftime("%A %d %b").replace(" 0", " "))


def _remind(text, lang, state, vocab, today, shop, forced_id=None):
    who = _known_name(text, state, vocab, owes_me=True, today=today) or state.get("last_customer")
    if not who:
        return _out(SAY["remind_who"][lang], lang, english=SAY["remind_who"]["English"])
    debtors = ledger.debtors(today)
    if forced_id:
        d = next((x for x in debtors if x["customer_id"] == forced_id), None)
        who = d["customer"] if d else who
    else:
        who = _full_name(who, debtors)
        same = [x for x in debtors if askbook.same_person(who, x["customer"])]
        if len({x["customer_id"] for x in same}) > 1:
            return _ask_which(state, who, [ledger.get_customer(x["customer_id"]) for x in same], lang, today,
                              "remind", text)
        d = same[0] if same else None
    _mention(state, who)
    if not d:
        return _out(SAY["remind_none"][lang].format(who=who), lang,
                    english=SAY["remind_none"]["English"].format(who=who))
    day = _when(text, today)
    their_lang = next((l for l in insights.TEMPLATES if re.search(rf"\bin {l.lower()}\b", fold(text))),
                      lang if lang in insights.TEMPLATES and lang != "Pidgin" else "English")
    ledger.add_reminder(d["customer"], day.isoformat(), their_lang, customer_id=d["customer_id"])
    msg, link = insights.reminder(d["customer"], their_lang, shop, today=today, customer_id=d["customer_id"])
    if d.get("customer_id"):  # the draft also shows in this customer's conversation
        ledger.add_message(d["customer_id"], msg, sender="tradevoice", kind="reminder", status="draft")
    said = SAY["remind_set"][lang].format(when=_when_say(day, today, lang), m=_money(d["balance"]), who=d["customer"])
    en = SAY["remind_set"]["English"].format(when=_when_say(day, today, "English"), m=_money(d["balance"]),
                                             who=d["customer"])
    spoken = SAY["remind_set"][lang].format(when=_when_say(day, today, lang), m=tts.naira_words(d["balance"]),
                                            who=d["customer"])
    out = _out(said, lang, spoken=spoken, english=en)
    out["message"], out["link"] = msg, link
    return out


def _question(text, lang, state, vocab, today):
    q, engine = askbook.parse(text, vocab)
    if q["kind"] != "query":
        return None
    if not q.get("customer"):
        q["customer"] = _pronoun_person(text, state, today=today)  # "how much she owe now?"
    q["customer"] = _nick_in(text) or q.get("customer")   # a name they taught it ("Mama T" = Mama Tunde)
    if q.get("customer") and q["what"] in ("owed_to_me", "i_owe"):
        people = ledger.debtors(today) if q["what"] == "owed_to_me" else ledger.creditors(today)
        q["customer"] = _full_name(q["customer"], people)
    _mention(state, q.get("customer"))
    q["language"] = lang
    res = askbook.run(q, today)
    en = dict(q, language="English")
    out = _out(askbook.answer(q, res), lang, spoken=askbook.answer(q, res, spoken=True),
               english=askbook.answer(en, res))
    out["engine"] = engine
    return out


# ---------------------------------------------------------------- entry point

def reply(text, state=None, today=None, shop="your shop"):
    """One message in -> one reply out: {text, spoken, lang, english, [message, link]}. `state` is updated."""
    state = state if state is not None else new_state()
    state["turn"] = (state.get("turn") or 0) + 1   # one number per message: "undo" removes all of one "save it all"
    today = today or dt.date.today()
    text = (text or "").strip()
    lang = _lang(text, state)
    state["lang"] = lang
    t = fold(text)
    vocab = ledger.known_words()
    pending = state.get("pending")
    heard = state.pop("heard_check", None)   # what the hearing models weren't sure of (this message only)

    if state.get("choose"):  # answer to "Which Feranmi?"
        pick, ch = _chosen(t, state), state["choose"]
        state["choose"] = None  # answered, or they moved on to something else
        if pick is not None:
            if ch["for"] == "remind":
                return _remind(ch["text"], lang, state, vocab, today, shop,
                               forced_id=None if pick == "new" else pick)
            if pending:
                if pick == "new":
                    pending["_create"], pending["_new_forced"], pending["customer_id"] = True, True, None
                else:
                    cu = ledger.get_customer(pick)
                    pending["customer_id"], pending["customer"] = pick, cu["name"]
                    if ch.get("how") in ("initials", "sounds"):   # "Mama T" / a misheard name: next time, no question
                        ledger.remember("nick", ch["name"], pick)
                if pending.get("amount") in (None, ""):
                    return _out(SAY["how_much"][lang], lang, english=SAY["how_much"]["English"])
                return _heard(pending, lang)
    if UNDO.match(t) or (not _drafts(state) and WRONG_AFTER.match(t)):
        out = _after_save(text, t, lang, state, today)
        if out:
            return out
    if YES.match(t):
        if _drafts(state):
            return _save_all(state, today)    # one draft, or a list said one after the other: "save it all"
        return _out(SAY["nothing_pending"][lang], lang, english=SAY["nothing_pending"]["English"])
    if ONLY.search(t) and len(_drafts(state)) > 1:
        out = _save_only(t, state, today)    # "save Dino only": that one, the others keep waiting
        if out:
            return out
    if NO.match(t):
        n = len(_drafts(state))
        state["pending"], state["queue"] = None, []
        key = "cancelled_n" if n > 1 else "cancelled"
        return _out(SAY[key][lang], lang, english=SAY[key]["English"])
    if pending and pending.get("amount") in (None, "") and parse_amount(text) and len(t.split()) <= 4:
        pending["amount"] = parse_amount(text)  # answer to "How much?"
        return _heard(pending, lang)
    if pending and pending.get("_reask") == "customer" and parse_amount(text) is None and len(t.split()) <= 5:
        return _name_again(text, lang, state, today)   # answer to "Say the customer's name again"
    if pending and _is_correction(text, t, state):
        return _correct(text, lang, state, today)
    if REMIND.search(t):
        return _remind(text, lang, state, vocab, today, shop)
    if LIMIT.search(t):
        return _set_limit(text, lang, state, vocab)
    if USUAL.search(t):
        return _usual(text, lang, state, vocab, today)
    if STATEMENT_RX.search(t):
        return _statement(text, lang, state, vocab, shop)
    amount = parse_amount(text)
    if amount is not None and PROFIT_SAID.search(t) and not PROFIT_ASKED.search(t) and not EVENT_MONEY.search(t):
        return _profit_info(lang, today)   # "today we make 50k profit": profit is worked out, never written in
    asked = clock.asked(t)  # "what time is it?" / "what day is today?": Nigeria time, said by code
    if asked and amount is None:
        kind, said = asked
        if said not in ("English", "Pidgin") or lang == "English":   # "Karfe nawa?" is Hausa whatever was picked
            lang = state["lang"] = said
        return _out(clock.answer(kind, lang), lang, english=clock.answer(kind, "English"))
    import tools

    done = tools.answer(text, lang, today, vocab)  # sums, dates, measures, cash check, grouped questions: by code
    if done:
        return done
    if THANKS.match(t):
        return _out(_named(SAY_THANKS.get(lang, SAY_THANKS["English"])), lang, english=_named(SAY_THANKS["English"]))
    if HELP.search(t) or GREET.match(t):
        import ui_text

        said = next((l for l, w in (("Yoruba", r"bawo|pele|ka ?a?(ro|san|le)"), ("Hausa", r"sannu|ina (kwana|wuni)"),
                                    ("Igbo", r"ndewo|kedu|nnoo")) if re.search(w, t)), None)
        lang = state["lang"] = said or lang  # "Bawo ni" = Yoruba, whatever was picked

        return _out(_named(ui_text.t("hello", lang)), lang, english=_named(ui_text.t("hello", "English")))
    if CANT_SEE.search(t) and amount is None:   # "I just shared a list": say what to do instead of guessing
        return _out(SAY["cant_see"][lang], lang, english=SAY["cant_see"]["English"])
    if TAX.search(t) and amount is None:  # "do I pay tax?": the plain facts + their own year, never "you owe ₦X"
        import tax

        return _out(tax.chat_answer(lang, insights.year_record(today=today)[0]), lang,
                    english=tax.chat_answer("English") if lang != "English" else None)
    if is_list(text) and not QUESTION.search(t):
        return _many(text, lang, today)   # a list in one message ("Chinedu ₦15,000 Aisha ₦45,000 …"): every line
    if amount is None:
        import assistant

        fixed = assistant.book_answer(text, lang, today)  # "who owes me the most?" etc.: exact, from the book
        if fixed:
            return _out(fixed, lang)
    if amount is None and not EVENT.search(t) and not on_topic(text, vocab):
        # not about the shop (a mishearing, small talk, health, news…): no AI sees it, not even to search the book.
        # A misheard note once came back as advice on mental health; TradeVoice only knows this trader's book.
        tools.unanswered(lang)
        return _out(SAY["off_topic"][lang], lang, english=SAY["off_topic"]["English"])
    if QUESTION.search(t) or (amount is None and not EVENT.search(t)):
        out = _question(text, lang, state, vocab, today)
        if out:
            return out
    if amount is not None or EVENT.search(t):
        return _record(text, lang, state, vocab, today, heard)
    if not on_topic(text, vocab):   # (a record word with no amount, said off topic)
        tools.unanswered(lang)
        return _out(SAY["off_topic"][lang], lang, english=SAY["off_topic"]["English"])
    done = tools.ai_answer(text, lang, today)   # N-ATLaS picks a tool for what the rules didn't catch; code runs it
    if done:
        return done
    if lang not in ("English", "Pidgin"):  # the AI answers in Yoruba / Hausa / Igbo, numbers checked against the book
        import assistant

        said = assistant.free(text, lang, today)
        if said:
            return _out(said, lang, spoken=assistant.spoken(said))
    answer, engine = insights.ask(text)
    if engine == "rules" and not answer:
        tools.unanswered(lang)     # counted for the team (no words kept): the common ones become new tools
        return _out(SAY["not_sure"][lang], lang, english=SAY["not_sure"]["English"])
    return _out(answer, lang)


def due_today(lang="English", today=None):
    """"Today: collect ₦63,600 from Mama Tunde." for every reminder that is due, then today's usual orders."""
    lang = lang if lang in LANGS else "English"
    return [SAY["due"][lang].format(m=_money(r["balance"]), who=r["customer"])
            for r in ledger.reminders(today, due_only=True)] + [
            "" + repeat_line(p, lang) + " " + {"English": "Say \"{who} usual\" to record it.",
                                                  "Pidgin": "Talk \"{who} usual\" make I write am."}.get(lang, "").format(who=p["customer"])
            for p in insights.repeat_orders(today)]


def _what(p):
    unit = p.get("unit") or ""
    if p.get("quantity") and unit and p["quantity"] != 1 and not unit.endswith("s"):
        unit += "s"
    q = f"{p['quantity']:g} " if p.get("quantity") else ""
    return f"{q}{unit + ' of ' if unit else ''}{p['item']}".strip()


def repeat_line(p, lang):
    import ui_text

    day = ui_text.t("wd_" + str(insights.WEEKDAYS.index(p["weekday"])), lang) or p["weekday"]
    return SAY["repeat"][lang].format(who=p["customer"], what=_what(p), day=day)


def draft_repeat(state, p, lang):
    """Put the usual order in as a DRAFT: the trader still confirms (Save / Change / Cancel, or yes/no)."""
    state["pending"] = {"type": p["type"], "amount": p["amount"], "customer": p["customer"],
                        "customer_id": p["customer_id"], "item": p["item"], "quantity": p["quantity"],
                        "unit": p["unit"] or None, "due_date": None, "confidence": 0.9, "note": None, "_engine": "repeat"}
    state["pending_text"] = f"(usual order: {_what(p)})"
    _mention(state, p["customer"])
    out = _heard(state["pending"], lang)
    out["text"] = repeat_line(p, lang) + "\n" + out["text"]
    return out


USUAL = re.compile(r"\busual\b|same as last (week|time)|as (he|she|dem) (dey )?(always|usually)|the regular")


def _usual(text, lang, state, vocab, today):
    who = _known_name(text, state, vocab) or state.get("last_customer")
    pats = [p for p in insights.repeat_orders(today, only_today=False)
            if who and ledger.customer_key(p["customer"]) == ledger.customer_key(who)]
    if not pats:
        return _out(SAY["repeat_none"][lang].format(who=who or "…"), lang,
                    english=SAY["repeat_none"]["English"].format(who=who or "…"))
    today_first = sorted(pats, key=lambda p: (p["weekday"] != insights.WEEKDAYS[today.weekday()], -p["times"]))
    return draft_repeat(state, today_first[0], lang)


if __name__ == "__main__":
    s = new_state()
    for line in ("Mama Tunde dey owe me forty-five thousand", "yes", "Ṣé mo ní gbèsè lọ́wọ́ Alhaji?",
                 "Remind Mama Tunde tomorrow"):
        r = reply(line, s)
        print(f"> {line}\n  {r['text']}" + (f"\n  ({r['english']})" if r.get("english") else "")
              + (f"\n  {r['message']}" if r.get("message") else ""))
