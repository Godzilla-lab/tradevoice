"""Measure extraction accuracy + latency. Paste the output into your submission (Testing + reliability).

python eval/run_eval.py                                  # 20 easy English/Pidgin cases
python eval/run_eval.py --cases eval/cases_hard.jsonl --sleep 1.5    # ~200 trap cases, 5 languages (~10 min)
python eval/run_eval.py --cases eval/cases_hard.jsonl --rules-only   # same, no AI: the baseline to beat
python eval/run_eval.py --cases eval/cases_hard.jsonl --lang yoruba --category negation,part_payment
python eval/run_eval.py --cases eval/cases_team.jsonl    # the team's NEW phrases (the most honest score)
python eval/run_eval.py --audio eval/audio               # transcribe eval/audio/<id>.(wav|m4a|ogg|mp3) first
python eval/run_eval.py --compare eval/results/A.json eval/results/B.json   # is B really better than A?

Every run saves eval/results/<cases>-<engine>-<time>.json (per-case answers) for --compare.
Scores come with a 95% range (Wilson interval): 16/16 correct only proves "somewhere between 81% and 100%".
"""
import argparse
import datetime as dt
import difflib
import glob
import json
import math
import os
import statistics
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from extract import TYPES, extract, fold  # noqa: E402

HERE = os.path.dirname(__file__)
FIELDS = ("type", "amount", "customer")
TODAY = dt.date(2026, 9, 27)  # fixed "today" so due dates are comparable between runs
ASR_LANG = {"yoruba": "Yoruba", "hausa": "Hausa", "igbo": "Igbo"}


def norm(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).lower().split()) if v is not None else None


def wilson(k, n, z=1.96):
    """95% range for a score of k/n (honest for small n and for 100%)."""
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def score(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:4.0%}  (95%: {lo:.0%}-{hi:.0%})" if n else "-"


def check(case, rec):
    """Per-field right/wrong for one case. 'flag' cases pass if the AI signals doubt instead of guessing."""
    if case.get("flag"):
        doubt = (rec.get("confidence") or 1) < 0.6 or bool(rec.get("note"))
        return {"flagged": doubt}
    ok = {f: norm(rec.get(f)) == norm(case[f]) for f in FIELDS}
    if not ok["customer"] and case.get("customer_alts"):  # e.g. an Arabic name written in Latin letters
        ok["customer"] = norm(rec.get("customer")) in {norm(a) for a in case["customer_alts"]}
    if case.get("due_weekday"):
        try:
            ok["due"] = dt.date.fromisoformat(str(rec.get("due_date"))).strftime("%A") == case["due_weekday"]
        except ValueError:
            ok["due"] = False
    return ok


def macro_f1(pairs):
    f1s = []
    for t in TYPES:
        tp = sum(1 for g, p in pairs if g == t and p == t)
        fp = sum(1 for g, p in pairs if g != t and p == t)
        fn = sum(1 for g, p in pairs if g == t and p != t)
        if tp + fp + fn:
            f1s.append(2 * tp / (2 * tp + fp + fn))
    return sum(f1s) / len(f1s) if f1s else 0.0


def report(rows, engines, fallbacks):
    scored = [r for r in rows if "flagged" not in r["ok"]]
    n = len(scored)
    print(f"\nEngine: {', '.join(sorted(engines))}   cases: {len(rows)}"
          + (f"   ⚠️ AI failed -> rules used on {fallbacks}" if fallbacks else ""))
    if n:
        for f in FIELDS:
            print(f"  {f:<10} {score(sum(r['ok'][f] for r in scored), n)}")
        due = [r for r in scored if "due" in r["ok"]]
        if due:
            print(f"  {'due day':<10} {score(sum(r['ok']['due'] for r in due), len(due))}")
        print(f"  {'ALL FIELDS':<10} {score(sum(r['all'] for r in scored), n)}")
        print(f"  type macro-F1 {macro_f1([(r['case']['type'], r['rec'].get('type')) for r in scored]):.2f}")
        # the costly mistake: a WRONG number in someone's book (worse than an empty one the trader fills in)
        wrong_money = [r for r in scored if r["case"]["amount"] is not None and r["rec"].get("amount") is not None
                       and not r["ok"]["amount"]]
        invented = [r for r in scored if r["case"]["amount"] is None and r["rec"].get("amount") is not None]
        print(f"  🚨 wrong amount written: {len(wrong_money)}/{n}   invented amount: {len(invented)}"
              f"/{sum(r['case']['amount'] is None for r in scored)}")
    flags = [r for r in rows if "flagged" in r["ok"]]
    if flags:
        print(f"  unclear notes where the AI asked instead of guessing: {sum(r['ok']['flagged'] for r in flags)}"
              f"/{len(flags)}")
    errs = [r for r in rows if r.get("error")]
    if errs:
        ai = [r for r in scored if not r.get("error")]
        print(f"  AI answered {len(ai)}/{len(scored)}: ALL FIELDS on those {score(sum(r['all'] for r in ai), len(ai))}")
        why = Counter(" ".join(str(r["error"]).split())[:90] for r in errs)
        print("  why the AI failed (-> rules used):")
        for msg, k in why.most_common(5):
            print(f"    {k:>3} x {msg}")
    lat = [r["latency_ms"] for r in rows]
    print(f"  understanding latency: median {statistics.median(lat):.0f} ms, "
          f"90% under {sorted(lat)[int(0.9 * (len(lat) - 1))]} ms, max {max(lat)} ms")
    asr = [r["asr_ms"] for r in rows if r.get("asr_ms")]
    if asr:
        print(f"  speech-to-text latency: median {statistics.median(asr):.0f} ms, max {max(asr)} ms")
        sims = defaultdict(list)
        for r in rows:
            if "heard_sim" in r["case"]:
                sims[r["case"].get("lang", "-")].append(r["case"]["heard_sim"])
        print("  heard vs really said (letters match, no tone marks; 100% = perfect): " + ", ".join(
            f"{k} {statistics.mean(v):.0%}" for k, v in sorted(sims.items())) + "   engines: " + ", ".join(
            sorted({r["case"].get("asr_engine", "?") for r in rows if "heard_sim" in r["case"]})))

    for key in ("lang", "category"):
        groups = defaultdict(list)
        for r in scored:
            groups[r["case"].get(key, "-")].append(r)
        if len(groups) > 1:
            print(f"\n  ALL FIELDS by {key}:")
            for g, rs in sorted(groups.items(), key=lambda kv: sum(r["all"] for r in kv[1]) / len(kv[1])):
                weak = Counter(f for r in rs for f in FIELDS if not r["ok"][f])
                print(f"    {g:<16} {score(sum(r['all'] for r in rs), len(rs))}"
                      + (f"   misses: {dict(weak)}" if weak else ""))

    if n:
        print("\n  Type confusion (rows = truth, columns = AI answer):")
        short = {"sale": "sale", "credit_sale": "credit", "payment_received": "payment", "expense": "expense",
                 "credit_purchase": "I owe", "payment_made": "I paid"}
        seen = [t for t in TYPES if any(t in (r["case"]["type"], r["rec"].get("type")) for r in scored)]
        print("    " + " " * 10 + "".join(f"{short.get(t, t):>9}" for t in seen))
        for g in seen:
            cnt = Counter(r["rec"].get("type") for r in scored if r["case"]["type"] == g)
            if cnt:
                print(f"    {short.get(g, g):<10}" + "".join(f"{cnt.get(t, 0):>9}" for t in seen))

    bad = [r for r in rows if not r["all"]]
    if bad:
        print(f"\n  Mistakes ({len(bad)}):")
    for r in bad:
        c, rec = r["case"], r["rec"]
        diff = {f: (rec.get(f), c[f]) for f in FIELDS if f in r["ok"] and not r["ok"][f]}
        if "due" in r["ok"] and not r["ok"]["due"]:
            diff["due"] = (rec.get("due_date"), c["due_weekday"])
        if "flagged" in r["ok"]:
            diff = {"should have asked": (rec.get("confidence"), rec.get("note"))}
        src = " (rules: AI failed)" if r.get("error") else ""
        print(f"  ✗ {c['id']} [{c.get('category', '')}]{src} {r['text']!r}\n      got vs expected: {diff}")


def compare(path_a, path_b):
    """McNemar test on the SAME cases: is B's gain bigger than luck?"""
    a = {r["id"]: r["all"] for r in json.load(open(path_a))["rows"]}
    b = {r["id"]: r["all"] for r in json.load(open(path_b))["rows"]}
    common = sorted(set(a) & set(b))
    only_a = sum(1 for i in common if a[i] and not b[i])
    only_b = sum(1 for i in common if b[i] and not a[i])
    print(f"{len(common)} shared cases.  A right: {sum(a[i] for i in common)}  B right: {sum(b[i] for i in common)}")
    print(f"Only A right: {only_a}   only B right: {only_b}")
    m = only_a + only_b
    if not m:
        print("Identical results.")
        return
    # exact two-sided binomial test on the disagreements
    k = min(only_a, only_b)
    p = min(1.0, 2 * sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m)
    print(f"p = {p:.3f} -> " + ("a real difference (p < 0.05)" if p < 0.05 else
                                "could be luck: don't claim one is better from this run"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=os.path.join(HERE, "cases.jsonl"))
    ap.add_argument("--audio", help="folder of recorded voice notes named by case id")
    ap.add_argument("--asr", choices=["local", "spitch", "spitch-local", "intron", "intron-local"],
                    help="speech-to-text engine for --audio (default: ASR_ENGINE in .env, else local)")
    ap.add_argument("--lang", help="only these languages, comma-separated (english,pidgin,yoruba,hausa,igbo)")
    ap.add_argument("--category", help="only these categories, comma-separated")
    ap.add_argument("--limit", type=int, help="only the first N cases (quick check)")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds between AI calls (free tier: 1.5)")
    ap.add_argument("--rules-only", action="store_true", help="ignore NVIDIA_API_KEY: score the offline rules")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"))
    args = ap.parse_args()
    if args.compare:
        return compare(*args.compare)
    if args.asr:
        os.environ["ASR_ENGINE"] = args.asr
    if args.rules_only:
        os.environ.pop("NVIDIA_API_KEY", None)
        os.environ.pop("LOCAL_LLM_URL", None)

    cases = [json.loads(line) for line in open(args.cases, encoding="utf-8") if line.strip()]
    if args.lang:
        cases = [c for c in cases if c.get("lang", "english") in args.lang.split(",")]
    if args.category:
        cases = [c for c in cases if c.get("category") in args.category.split(",")]
    cases = cases[:args.limit] if args.limit else cases

    rows, engines, fallbacks = [], set(), 0
    for i, c in enumerate(cases):
        text, asr_ms = c["text"], None
        if args.audio:
            files = glob.glob(os.path.join(args.audio, c["id"] + ".*"))
            if not files:
                print(f"skip {c['id']}: no audio")
                continue
            from asr import transcribe

            r = transcribe(files[0], ASR_LANG.get(c.get("lang"), "English / Pidgin"))
            asr_ms, text = r["latency_ms"], r["text"]
            c["heard_sim"] = round(difflib.SequenceMatcher(None, fold(text), fold(c["text"])).ratio(), 3)
            c["asr_engine"] = r["engine"]
        if args.sleep and i:
            time.sleep(args.sleep)
        rec, meta = extract(text, today=TODAY)
        engines.add(meta["engine"].split(" (")[0])
        fallbacks += bool(meta.get("error"))
        ok = check(c, rec)
        rows.append({"id": c["id"], "case": c, "text": text, "rec": rec, "ok": ok, "all": all(ok.values()),
                     "latency_ms": meta["latency_ms"], "asr_ms": asr_ms, "engine": meta["engine"],
                     "error": meta.get("error")})
        print(f"\r  {i + 1}/{len(cases)} {'✓' if rows[-1]['all'] else '✗'} {c['id']:<24}", end="", flush=True)
    print()
    if not rows:
        print("No cases to run (empty file, filters, or no matching audio).")
        return
    report(rows, engines, fallbacks)

    if not args.no_save:
        os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
        tag = "rules" if engines == {"rules"} else "ai"
        path = os.path.join(HERE, "results", f"{os.path.splitext(os.path.basename(args.cases))[0]}-{tag}-"
                                             f"{dt.datetime.now():%m%d-%H%M}.json")
        json.dump({"cases": args.cases, "engines": sorted(engines), "models": os.getenv("LLM_MODELS"),
                   "rows": rows}, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
        print(f"\nSaved {path}  (compare two runs: --compare A.json B.json)")


if __name__ == "__main__":
    main()
