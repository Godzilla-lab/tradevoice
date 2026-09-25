"""Long voice notes: many entries + summary + helpful extras, with the safety checks. No key needed (fake AI).

python eval/test_note.py
The Yoruba note is a real one from the team (25 Sep), transcribed by Intron.
"""
import json
import os
import sys
import tempfile
from unittest import mock

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import llm  # noqa: E402
import note  # noqa: E402

YORUBA = ("Mo bá ìyá Bísí sọ̀rọ̀, mo ní kí ìyá Bísí fún mi ní balance mi 50,000 naira lànà wden jeming 2 million gbogbo "
          "ta jọ sọ pẹ̀lú bag rice àti spaghetti ta jọ ra ti ṣe tán gbogbo nǹkan ta bá ti sọ a máa ṣàlàyé owó tó kù owó "
          "venti mi ilé tí mò ń rent mi 1.8 million ni so a need láti ṣí gbogbo ẹ̀")
PIDGIN = ("I sell 2 bags rice to Mama Tunde 30k she go pay Monday, then I pay 5000 for transport, "
          "Oga Emeka pay me 20k wey he owe, and my shop rent na 400k for the year")
AI = {"entries": [{"said": "bag rice àti spaghetti ta jọ ra", "type": "expense", "item": "rice and spaghetti",
                   "amount": None, "customer": None, "confidence": 0.4, "note": "amount not said"}],
      "summary": "O bá Ìyá Bísí sọ̀rọ̀ nípa balance ₦50,000. Ẹ sọ̀rọ̀ nípa ₦2,000,000 àti ìrẹsì pẹ̀lú spaghetti. "
                 "Owó ilé rẹ jẹ́ ₦1,800,000.",
      "summary_en": "You talked to Iya Bisi about her ₦50,000 balance. You talked about ₦2,000,000. "
                    "You bought rice and spaghetti together. Your house rent is ₦1,800,000.",
      "unclear": ["Kí ni ₦2,000,000 yẹn wà fún?"], "unclear_en": ["What is the ₦2,000,000 for?"]}


def fake(resp):
    return mock.patch.object(llm, "chat", return_value=(json.dumps(resp), "fake-ai"))


def run():
    checks = []
    with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "x"}):
        with fake(AI):
            r = note.understand(YORUBA, "Yoruba")
        checks += [("long note detected", note.is_long(YORUBA)),
                   ("AI summary kept (all its numbers were said)", r["summary"] == AI["summary"]),
                   ("written English summary kept", r["summary_en"] == AI["summary_en"]),
                   ("English rent tip for the screen", any("a month" in x for x in r["extras_en"])),
                   ("rent tip computed: ₦150,000 a month", any("₦150,000" in x for x in r["extras"])),
                   ("unclear ₦2m is asked, not guessed", len(r["unclear"]) == 1),
                   ("spoken reply has amounts in words", "one million, eight hundred thousand naira"
                    in note.spoken_text(r, "Yoruba"))]
        with fake(dict(AI, summary_en=AI["summary_en"] + " That is ₦150,000 a month.")):
            r = note.understand(YORUBA, "Yoruba")
        checks.append(("invented ₦150,000 in the AI summary is rejected", "150,000" not in r["summary"]))
        bad_entry = dict(AI, entries=[{"said": "ilé tí mò ń rent", "type": "expense", "amount": 2500000}])
        with fake(bad_entry):
            r = note.understand(YORUBA, "Yoruba")
        checks.append(("entry amount never said (₦2.5m) is removed", r["entries"][0]["amount"] is None))
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("NVIDIA_API_KEY", None)
        os.environ.pop("LOCAL_LLM_URL", None)
        r = note.understand(PIDGIN, "Pidgin")
    got = [(e["type"], e["amount"]) for e in r["entries"]]
    checks.append(("offline: split into 4 parts", got == [("credit_sale", 30000), ("expense", 5000),
                                                            ("payment_received", 20000), ("expense", 400000)]))
    checks.append(("short note stays on the single-entry path",
                   not note.is_long("I sell 3 bag rice give Mama Tunde 45k, she go pay Friday")))
    for name, ok in checks:
        print(("✓" if ok else "✗"), name)
    fails = sum(not ok for _, ok in checks)
    print(f"\n{len(checks) - fails}/{len(checks)} long-note checks pass")
    return fails


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
