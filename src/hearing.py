"""What the hearing models agree on (ROADMAP Part 5, items 3 and 4).

1. Two models, one note: for Yoruba / Hausa / Igbo the N-ATLaS hearing server runs the trader's language model AND
   the Nigerian-accented English model on the same voice note (traders mix languages). The N-ATLaS LLM merges the
   two into one sentence and fixes names against the trader's book ("generative error correction", HyPoradise).
   Guard: an amount is kept only if a hearing model really heard it, and a merge that is much longer than both
   transcripts (made-up words) is thrown away. If N-ATLaS is asleep or slow, the trader's language model's words
   are used, as before.
2. What to ask again: amounts the two models heard differently, and words a model wasn't sure of, go with the
   words to the chat (state["heard_check"]), which asks for just that part ("Say the amount again").
"""
import contextlib
import contextvars
import os
import re
import time

_LIVE = contextvars.ContextVar("hearing_live", default=False)


@contextlib.contextmanager
def live():
    """A live conversation turn: no N-ATLaS merge (one N-ATLaS call per turn is the reply itself). The two models are
    still compared by code (check()), so an amount they heard differently is still asked again."""
    token = _LIVE.set(True)
    try:
        yield
    finally:
        _LIVE.reset(token)

MERGE_PROMPT = """Two speech models heard the same short voice note from a Nigerian market trader who may mix
__LANG__ and English.
A (__LANG__ model): __A__
B (English model): __B__
Customer names and items in the trader's book: __BOOK__
Write the ONE sentence the trader most likely said, in the words they used (keep __LANG__ words in __LANG__ and
English words in English). Use a name from the book only when A or B clearly sounds like it. Never add a number,
an amount or a name that is not in A or B. Reply with the sentence only."""


def _numbers(text):
    from extract import _amount_values, parse_amount

    out = set(_amount_values(text))
    a = parse_amount(text)
    if a is not None:
        out.add(float(a))
    return out


def merge(a, b, lang, vocab=None, timeout=None):
    """-> (merged words, how): how is "merged", or why A was kept ("same", "no_b", "live", "asleep", "amount", "long",
    "failed")."""
    a, b = (a or "").strip(), (b or "").strip()
    if not b:
        return a, "no_b"
    if not a:
        return b, "no_a"
    if re.sub(r"\W+", "", a.lower()) == re.sub(r"\W+", "", b.lower()):
        return a, "same"
    if _LIVE.get():
        return a, "live"          # speed: the turn's one N-ATLaS call is the reply, not the hearing
    import llm

    if not llm.natlas_on() or llm._resting.get("natlas", 0) > time.time():
        return a, "asleep"        # never wait for a cold brain in the middle of hearing
    book = ", ".join(((vocab or {}).get("names") or [])[:15] + ((vocab or {}).get("items") or [])[:8]) or "(none)"
    prompt = (MERGE_PROMPT.replace("__LANG__", lang).replace("__A__", a).replace("__B__", b)
              .replace("__BOOK__", book))
    t0 = time.perf_counter()
    try:
        wait = float(timeout or os.getenv("NATLAS_MERGE_TIMEOUT", "8"))
        text, _ = llm.chat([{"role": "user", "content": prompt}], max_tokens=120, temperature=0.0,
                           timeout=wait, deadline=wait, models=["natlas"])
    except Exception as e:  # noqa: BLE001
        print(f"hearing merge failed: {type(e).__name__}: {e}")
        _event(False, t0)
        return a, "failed"
    text = (text or "").strip().strip('"').splitlines()[0].strip() if (text or "").strip() else ""
    if not text:
        _event(False, t0)
        return a, "failed"
    if len(text) > 1.6 * max(len(a), len(b)) + 20:
        _event(False, t0)
        return a, "long"
    heard = _numbers(a) | _numbers(b)
    if not _numbers(text) <= heard:      # an amount nobody heard: keep the trader's language model's words
        _event(False, t0)
        return a, "amount"
    _event(True, t0)
    return text, "merged"


def _event(ok, t0):
    try:
        import events
        events.log("hear_merge", engine="natlas", ok=ok, ms=(time.perf_counter() - t0) * 1000)
    except Exception:  # noqa: BLE001
        pass


NUMBER_WORDS = re.compile(
    r"\d|^(k|naira|hundred|thousand|million|half|ogun|ogoji|aadota|egberun|ogorun|dubu|dari|miliyan|naira|puku|nari|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|"
    r"seventy|eighty|ninety|okan|meji|meta|merin|marun|mefa|meje|mejo|mesan|mewa|daya|biyu|uku|hudu|biyar|shida|"
    r"bakwai|takwas|tara|goma|otu|abuo|ato|ano|ise|isii|asaa|asato|itoolu|iri)$")


def _fold(w):
    from extract import fold
    return re.sub(r"[^\w]", "", fold(w))


def check(first, second=None, merged=None):
    """What the chat should ask about, from the hearing results (dicts with text / unsure), or None.
    {"amounts": [every different amount the models heard, when they disagree], "unsure_amount": bool,
     "unsure_words": [folded words a model wasn't sure of]}"""
    from extract import parse_amount

    out = {}
    texts = [r.get("text") for r in (first, second) if r and r.get("text")]
    heard = sorted({float(x) for x in (parse_amount(t) for t in texts) if x is not None})
    if len(heard) > 1:
        out["amounts"] = heard
    words = [_fold(u.get("word") or "") for r in (first, second) if r for u in (r.get("unsure") or [])]
    final = {_fold(w) for w in (merged or (first or {}).get("text") or "").split()}
    words = [w for w in words if w and w in final]    # only words that made it into what the chat reads
    if any(NUMBER_WORDS.search(w) for w in words):
        out["unsure_amount"] = True
    names = [w for w in words if not NUMBER_WORDS.search(w)]
    if names:
        out["unsure_words"] = names[:10]
    return out or None
