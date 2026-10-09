"""The reply's language (and so its voice) is the trader's language: Yoruba stays Yoruba, Hausa is Hausa, Igbo is
Igbo. Measured on every test sentence in eval/cases*.jsonl (made-up names): the guesser never mixes the three local
languages, never reads English or Pidgin as one of them, and reads most Hausa and Igbo as such; a trader who chose a
language keeps it. python eval/test_language.py
"""
import collections
import glob
import json
import os
import sys

os.environ["TV_NO_DOTENV"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import askbook  # noqa: E402
import converse  # noqa: E402

CHECKS = []


def check(name, ok, got=""):
    CHECKS.append(bool(ok))
    print(f"{'✓' if ok else '✗'} {name}" + ("" if ok else f"\n    got: {str(got)[:400]}"))


def main():
    conf, n, seen = collections.Counter(), collections.Counter(), set()
    for f in glob.glob(os.path.join(os.path.dirname(__file__), "cases*.jsonl")):
        for line in open(f, encoding="utf-8"):
            try:
                c = json.loads(line)
            except ValueError:
                continue
            lang, text = (c.get("lang") or "").capitalize(), c.get("text") or ""
            if not lang or not text or text in seen:
                continue
            seen.add(text)
            n[lang] += 1
            conf[(lang, askbook.guess_language(text))] += 1
    local = ("Yoruba", "Hausa", "Igbo")
    mixed = sum(conf[(a, b)] for a in local for b in local if a != b)
    check(f"Yoruba, Hausa and Igbo are never taken for each other ({sum(n[x] for x in local)} sentences)", mixed == 0, conf)
    check("English and Pidgin are never taken for a local language",
          all(conf[(a, b)] == 0 for a in ("English", "Pidgin") for b in local), conf)
    for lang, floor in (("Yoruba", 0.95), ("Hausa", 0.9), ("Igbo", 0.95)):
        share = conf[(lang, lang)] / max(n[lang], 1)
        check(f"{lang} read as {lang}: {share:.0%} of {n[lang]} (at least {floor:.0%})", share >= floor, share)
    st = {"prefer": "Yoruba"}
    check("a trader who chose Yoruba gets Yoruba, even when the words look like Hausa",
          converse._lang("Na biya 27000 kudin mota zuwa kasuwa", st) == "Yoruba")
    check("…and for a bare 'hi'", converse._lang("hi", st) == "Yoruba")
    check("a trader on English who speaks Hausa is answered in Hausa",
          converse._lang("Na biya 27000 kudin mota zuwa kasuwa", {"prefer": "English"}) == "Hausa")
    check("…and English stays English", converse._lang("Who owes me the most?", {"prefer": "English"}) == "English")
    print(f"\n{sum(CHECKS)}/{len(CHECKS)} language checks pass")
    return all(CHECKS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
