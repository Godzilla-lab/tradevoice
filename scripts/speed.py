"""How long each step of a voice turn takes on this server (from the event log: times only, no words, no names).

    python scripts/speed.py            last 7 days
    python scripts/speed.py --days 1   today-ish
On the live server: sudo bash /opt/tradevoice/app/deploy/server/speed.sh

Steps, in the order a voice turn runs them:
  hearing      N-ATLaS speech model (voice note -> words)            event "hear"
  brain        N-ATLaS answering (record or question)                event "llm" (engine natlas)
  understand   the whole reply on the server (brain + book + rules)  event "understand"
  voice        Intron making the spoken reply (cached replies: 0)    event "voice" (engine intron)
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import settings  # noqa: E402,F401  (loads .env)

import events  # noqa: E402

STEPS = [("hearing", lambda r: r["kind"] == "hear" and r["ok"]),
         ("brain (N-ATLaS)", lambda r: r["kind"] == "llm" and r["ok"] and r["engine"] == "natlas"),
         ("brain (backup AI)", lambda r: r["kind"] == "llm" and r["ok"] and r["engine"] != "natlas"),
         ("N-ATLaS didn't answer", lambda r: r["kind"] == "llm" and not r["ok"] and r["engine"] == "natlas"),
         ("understand", lambda r: r["kind"] == "understand"),
         ("voice (Intron)", lambda r: r["kind"] == "voice" and r["ok"] and (r["engine"] or "").startswith("intron"))]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def table(rows):
    out = []
    for name, keep in STEPS:
        ms = [r["ms"] for r in rows if r["ms"] is not None and keep(r)]
        if ms:
            out.append((name, len(ms), statistics.median(ms), pct(ms, 90), max(ms)))
    return out


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("--days", type=float, default=7)
    args = a.parse_args(argv)
    rows = events.rows(since_days=args.days)
    t = table(rows)
    if not t:
        print(f"No timed voice turns in the last {args.days:g} days yet (the timing started with this update).")
        return 0
    print(f"Voice turn speed, last {args.days:g} days (seconds)\n")
    print(f"{'step':<20}{'count':>7}{'typical':>10}{'slow (9 in 10)':>16}{'slowest':>10}")
    for name, n, med, p90, mx in t:
        print(f"{name:<20}{n:>7}{med / 1000:>10.1f}{p90 / 1000:>16.1f}{mx / 1000:>10.1f}")
    print("\nA very slow 'slowest' (over 60 s) is a sleeping N-ATLaS waking up: NATLAS_WATCH=1 keeps it awake in market hours.")
    print("'N-ATLaS didn't answer': the time spent waiting before the backup AI answered instead (asleep, or an error).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
