"""Nigeria time for the whole app, and plain answers to "what day is today?" / "what time is it?".

The server's clock is UTC (London); Nigeria is UTC+1 all year (no daylight saving). Importing this module switches
the process to Nigeria time, so dt.date.today(), dt.datetime.now() and time.strftime() all mean Lagos: a sale at
00:30 is filed under today, not yesterday. "WAT-1" is the POSIX form of UTC+1 and needs no timezone files.
TV_TZ overrides it (e.g. for a test). The answers are made by code, never by the AI.
Yoruba / Hausa / Igbo wording needs a native-speaker check.
"""
import datetime as dt
import os
import re
import time

os.environ["TZ"] = os.getenv("TV_TZ") or "WAT-1"
if hasattr(time, "tzset"):
    time.tzset()

MONTHS = {
    "English": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                "November", "December"],
    "Yoruba": ["Jánúárì", "Fẹ́búárì", "Máàṣì", "Épírìlì", "Méè", "Júùnù", "Júláì", "Ọ́gọ́sìtì", "Sẹ́tẹ́ńbà", "Ọkútóbà",
               "Nòfẹ́ńbà", "Dìsẹ́ńbà"],
    "Hausa": ["Janairu", "Fabrairu", "Maris", "Afrilu", "Mayu", "Yuni", "Yuli", "Agusta", "Satumba", "Oktoba",
              "Nuwamba", "Disamba"],
    "Igbo": ["Jenụwarị", "Febụwarị", "Maachị", "Eprel", "Mee", "Juun", "Julaị", "Ọgọọst", "Septemba", "Ọktoba",
             "Novemba", "Disemba"],
}
MONTHS["Pidgin"] = MONTHS["English"]

# morning 5-11, afternoon 12-15, evening 16-19, night 20-4
PART = {"English": ["in the morning", "in the afternoon", "in the evening", "at night"],
        "Pidgin": ["for morning", "for afternoon", "for evening", "for night"],
        "Yoruba": ["òwúrọ̀", "ọ̀sán", "ìrọ̀lẹ́", "alẹ́"],
        "Hausa": ["na safe", "na rana", "na yamma", "na dare"],
        "Igbo": ["n'ụtụtụ", "n'ehihie", "na mgbede", "n'abalị"]}

SAY = {"date": {"English": "Today is {wd}, {d} {m}.", "Pidgin": "Today na {wd}, {d} {m}.",
                "Yoruba": "Òní ni {wd}, {d} {m}.", "Hausa": "Yau {wd} ce, {d} ga {m}.",
                "Igbo": "Taa bụ {wd}, {d} {m}."},
       "time": {"English": "It is {t} {p}.", "Pidgin": "Time na {t} {p}.", "Yoruba": "Aago {t} {p} ni.",
                "Hausa": "Yanzu ƙarfe {t} {p}.", "Igbo": "Ugbu a bụ elekere {t} {p}."}}

# asked on folded text (lowercase, no tone marks); the words also say which language to answer in
ASK = [
    ("time", "Pidgin", r"\bwetin be (?:the )?time\b|\bwhat time (?:e|it) (?:be|dey)\b|\bwhich time (?:e|it) (?:be|dey)\b"
                       r"|\btime don reach\b"),
    ("time", "English", r"\bwhat(?:'s| is)? (?:the )?time\b(?! (?:did|do|does|will|was|were|she|he|they|i|you|we)\b)"
                        r"|\btime (?:is it|now)\b"),
    ("time", "Yoruba", r"\ba(?:a|ag)?go (?:melo|meloo)\b"),
    ("time", "Hausa", r"\b[kƙ]arfe nawa\b"),
    ("time", "Igbo", r"\b(?:kedu|ole) (?:oge|elekere)\b|\b(?:elekere|oge) ole\b"),
    ("date", "Pidgin", r"\bwhich day (?:be|na) (?:it|today)\b|\btoday na which day\b|\bwhat day (?:be|na) today\b"
                       r"|\bwetin be today(?:'s)? date\b"),
    ("date", "English", r"\bwhat(?:'s| is)? (?:the )?date\b|\btoday(?:'s)? date\b|\bdate (?:of )?today\b"
                        r"|\bwhat day is (?:it|today)\b|\bwhich day is (?:it|today)\b"),
    ("date", "Yoruba", r"\bojo (?:wo|wo lo|wo ni) (?:ni )?oni\b|\b(?:ki ni|kini) ojo oni\b"),
    ("date", "Hausa", r"\bwace rana ce yau\b|\byau (?:wace )?rana ce\b|\bkwanan (?:wata )?nawa\b"),
    ("date", "Igbo", r"\bubochi (?:ole|kedu) (?:ka )?taa\b|\btaa bu ubochi ole\b|\bkedu ubochi taa\b"),
]
ASK = [(k, lang, re.compile(rx)) for k, lang, rx in ASK]


def now():
    """Nigeria time now (naive, like the rest of the book)."""
    return dt.datetime.now()


def asked(folded):
    """("time" | "date", language of the words) for a message already folded (extract.fold), else None."""
    return next(((k, lang) for k, lang, rx in ASK if rx.search(folded)), None)


def _part(hour):
    return 0 if 5 <= hour < 12 else 1 if 12 <= hour < 16 else 2 if 16 <= hour < 20 else 3


def date_text(lang="English", when=None):
    import ui_text

    when, lang = when or now(), lang if lang in SAY["date"] else "English"
    wd = ui_text.t(f"wd_{when.weekday()}", lang) or when.strftime("%A")
    return SAY["date"][lang].format(wd=wd, d=when.day, m=MONTHS[lang][when.month - 1])


def time_text(lang="English", when=None):
    when, lang = when or now(), lang if lang in SAY["time"] else "English"
    h = when.hour % 12 or 12
    return SAY["time"][lang].format(t=f"{h}:{when.minute:02d}", p=PART[lang][_part(when.hour)])


def answer(kind, lang="English", when=None):
    """'What time is it?' -> the time and the day (people asking the time often want both); 'what day?' -> the day."""
    if kind == "time":
        return time_text(lang, when) + " " + date_text(lang, when)
    return date_text(lang, when)


def now_line(when=None):
    """For the AI prompts: 'Now in Nigeria: Saturday 3 October 2026, 2:15 pm.'"""
    when = when or now()
    return f"Now in Nigeria: {when.strftime('%A')} {when.day} {when.strftime('%B %Y')}, " \
           f"{when.hour % 12 or 12}:{when.minute:02d} {'am' if when.hour < 12 else 'pm'}."
