"""No emojis in anything TradeVoice says or shows (the owner's rule, 3 Oct): words only.

no_emoji(text): an emoji between two sentences becomes a full stop ("Saved ✅ Mama Tunde owes…" -> "Saved. Mama Tunde
owes…"), anywhere else it is dropped. Used on every reply that leaves the server (web, WhatsApp, the AI's own words)
and by scripts/build_app.py on the built pages. Arrows (↑ ↓) and ticks/crosses used as signs (✓ ✕) are not emojis.
"""
import re

E = ("(?:[\U0001F000-\U0001FAFF☀-⛿✅✉✏✔✖❌❎❓-❗➕-➗"
     "➡⭐⭕⏰-⏺⌚⌛⬆⬇⤴⤵〰〽㊗㊙]️?‍?)+")
EMOJI = re.compile(E)
_UPPER = "A-ZÀ-ÝẸỌṢỊỤƊƘƁ{"


def no_emoji(text):
    if not text or not EMOJI.search(text):
        return text
    t = re.sub(rf"(?<=[^\W_)\]])[ \t]?{E}[ \t]+(?=[{_UPPER}])", ". ", text)   # "Saved ✅ Mama" -> "Saved. Mama"
    t = re.sub(rf"[ \t]?{E}(?=[ \t]*($|\n))", "", t)                         # at the end of a line
    t = re.sub(rf"{E}[ \t]?", "", t)                                         # anywhere else
    return re.sub(r"(?<=\S)[ \t]{2,}(?=\S)", " ", t)


def no_emoji_keep_layout(text):
    """The same rules for a whole file (a built page, source code): spacing elsewhere is left exactly as it is."""
    t = re.sub(rf"(?<=[^\W_)\]])[ \t]?{E}[ \t]+(?=[{_UPPER}])", ". ", text)
    t = re.sub(rf"[ \t]{E}(?=[\"'`<]|[ \t]*\n)", "", t)
    return re.sub(rf"{E}[ \t]?", "", t)
