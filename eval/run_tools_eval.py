"""Tool-call accuracy per language (E10): does TradeVoice pick the right tool, with the right fields, and does the
code then get the right number? Also: messages that are NOT tool questions (records, book questions) must not
trigger a tool.

    python eval/run_tools_eval.py              the code's word rules alone (offline, what tests/CI run)
    python eval/run_tools_eval.py --llm        rules first, then N-ATLaS for what they miss (as the app does;
                                               needs NATLAS_URL in .env, wakes the GPU)
Cases: eval/cases_tools.jsonl (made-up names). Today is fixed at Saturday 3 Oct 2026 for the dates. The book is the
demo book, taught 1 bag of rice = 40 mudu and 1 bag of beans = 30 paint.
"""
import argparse
import datetime as dt
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TODAY = dt.date(2026, 10, 3)
LANGS = ("English", "Pidgin", "Yoruba", "Hausa", "Igbo")


def setup(use_llm=False):
    if not use_llm:
        os.environ["TV_NO_DOTENV"] = "1"
        for k in list(os.environ):
            if k.endswith("API_KEY") or k.startswith(("LOCAL_", "NATLAS")):
                os.environ.pop(k)
    os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "tools.db")
    os.environ["BOOKS_DIR"] = tempfile.mkdtemp()
    os.environ["ACCOUNTS_DB"] = os.path.join(tempfile.mkdtemp(), "a.db")
    sys.path.insert(0, os.path.join(HERE, "..", "src"))
    if use_llm:
        import settings  # noqa: F401  (loads .env)
    import ledger
    import seed_demo

    seed_demo.seed()
    ledger.remember("unit", "rice|bag|mudu", 40)
    ledger.remember("unit", "beans|bag|paint", 30)


def score(case, use_llm=False):
    """(right tool?, right fields and result?, what was picked)"""
    import tools

    choice = tools.pick(case["text"], today=TODAY)
    if choice is None and use_llm:
        choice = tools.ai_pick(case["text"], TODAY)
    got = (choice or {}).get("tool") or "none"
    if case["tool"] == "none" or got != case["tool"]:
        return got == case["tool"], got == case["tool"], got
    want = case["check"]
    out = tools.run(choice, case["text"], case["lang"], TODAY) or {}
    ok = True
    for k, v in want.items():
        if k == "value":
            ok &= isinstance(out.get("value"), (int, float)) and abs(out["value"] - v) < 0.51
        elif k == "date":
            ok &= out.get("value") == v
        elif k in ("counted", "started_with", "quantity"):
            ok &= abs(float(choice.get(k) or 0) - v) < 0.51
        else:
            ok &= choice.get(k) == v
    return True, bool(ok), got


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--show", action="store_true", help="print every miss")
    a = ap.parse_args(argv)
    setup(a.llm)
    cases = [json.loads(x) for x in open(os.path.join(HERE, "cases_tools.jsonl"), encoding="utf-8")]
    table = {lang: [0, 0, 0] for lang in LANGS}       # cases, right tool, right tool + fields + result
    misses = []
    for c in cases:
        tool_ok, all_ok, got = score(c, a.llm)
        t = table[c["lang"]]
        t[0] += 1
        t[1] += tool_ok
        t[2] += all_ok
        if not all_ok:
            misses.append((c["id"], c["text"], c["tool"], got))
    print(f"Tool calls ({'rules + N-ATLaS' if a.llm else 'rules only, offline'}), {len(cases)} sentences:")
    print(f"  {'language':<9} {'cases':>5}  {'right tool':>10}  {'all right':>9}")
    for lang, (n, t, f) in table.items():
        print(f"  {lang:<9} {n:>5}  {t / n:>9.0%}  {f / n:>9.0%}")
    n = sum(v[0] for v in table.values())
    print(f"  {'all':<9} {n:>5}  {sum(v[1] for v in table.values()) / n:>9.0%}  "
          f"{sum(v[2] for v in table.values()) / n:>9.0%}")
    if a.show:
        for m in misses:
            print(f"  MISS {m[0]:<22} want {m[2]:<15} got {m[3]:<15} {m[1]}")
    return table


if __name__ == "__main__":
    main()
