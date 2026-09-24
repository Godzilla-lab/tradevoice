"""Measure extraction accuracy + latency. Paste the output into your submission (Testing + reliability).

python eval/run_eval.py                 # text cases (rules, or LLM if NVIDIA_API_KEY is set)
python eval/run_eval.py --cases eval/cases_team.jsonl   # the team's NEW phrases (honest score)
python eval/run_eval.py --audio eval/audio   # also transcribe eval/audio/<id>.(wav|m4a|ogg|mp3) first
"""
import argparse
import glob
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from extract import extract  # noqa: E402

FIELDS = ("type", "amount", "customer")


def norm(v):
    return " ".join(str(v).lower().split()) if v is not None else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=os.path.join(os.path.dirname(__file__), "cases.jsonl"))
    ap.add_argument("--audio", help="folder of recorded voice notes named by case id")
    args = ap.parse_args()

    cases = [json.loads(line) for line in open(args.cases) if line.strip()]
    hits = {f: 0 for f in FIELDS}
    all_ok, lat, asr_lat, fails, engines = 0, [], [], [], set()
    for c in cases:
        text = c["text"]
        if args.audio:
            files = glob.glob(os.path.join(args.audio, c["id"] + ".*"))
            if not files:
                print(f"skip {c['id']}: no audio")
                continue
            from asr import transcribe

            # cases_lang.jsonl carries "lang": route Yoruba/Hausa/Igbo audio to omniASR
            r = transcribe(files[0], {"yoruba": "Yoruba", "hausa": "Hausa", "igbo": "Igbo"}.get(c.get("lang"),
                                                                                             "English / Pidgin"))
            asr_lat.append(r["latency_ms"])
            text = r["text"]
        rec, meta = extract(text)
        engines.add(meta["engine"])
        lat.append(meta["latency_ms"])
        ok = {f: norm(rec.get(f)) == norm(c[f]) for f in FIELDS}
        for f in FIELDS:
            hits[f] += ok[f]
        if all(ok.values()):
            all_ok += 1
        else:
            fails.append((c["id"], text, {f: (rec.get(f), c[f]) for f in FIELDS if not ok[f]}))

    n = len(lat)
    if not n:
        print("No cases to run (empty file or no matching audio).")
        return
    print(f"\nEngine: {', '.join(sorted(engines))}   cases: {n}")
    for f in FIELDS:
        print(f"  {f:<9} {hits[f]}/{n}  ({hits[f] / n:.0%})")
    print(f"  ALL FIELDS {all_ok}/{n}  ({all_ok / n:.0%})")
    print(f"  understanding latency: median {statistics.median(lat):.0f} ms, max {max(lat)} ms")
    if asr_lat:
        print(f"  speech-to-text latency: median {statistics.median(asr_lat):.0f} ms, max {max(asr_lat)} ms")
    for cid, text, diff in fails:
        print(f"  ✗ {cid} {text!r}\n      got vs expected: {diff}")


if __name__ == "__main__":
    main()
