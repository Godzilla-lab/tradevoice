"""The NAIC "real-world validation" evidence, from the pilot's own log: one HTML page with numbers and charts.

    python scripts/validation_report.py                          pilot window 6 to 12 Oct 2026 (Lagos days)
    python scripts/validation_report.py --start 2026-10-06 --end 2026-10-17 --out validation.html
On the live server: sudo bash /opt/tradevoice/app/deploy/server/validation_report.sh   (puts it in your home folder)

Open the file in a browser and Print > Save as PDF. It holds counts only: no names, phone numbers, amounts or words
(the log never had them). The team's own phones (TEAM_PHONES, TEAM_WHATSAPP) are left out of every number.
"""
import argparse
import datetime as dt
import html
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import settings  # noqa: E402,F401  (loads .env: TEAM_PHONES)

import events  # noqa: E402

WAT = dt.timezone(dt.timedelta(hours=1))
ATTRIBUTION = ("N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy, "
               "and powered by Awarri Technologies.")
# what the team changed during the pilot because of what traders and testers ran into (from the commit history)
CHANGES = [
    ("6 Oct", "WhatsApp sign-up without templates, delivery failures shown on the dashboard, limits on codes and floods"),
    ("7 Oct", "Customers list: the add button no longer covers anyone's amount; long lists show 20 at a time"),
    ("9 Oct", "Sign-up without WhatsApp: SMS codes through a team phone, or number and password while none is set up"),
    ("9 Oct", "TradeVoice on Telegram: the same bot, free, for traders who use Telegram"),
    ("9 Oct", "Dashboard: N-ATLaS's own answers counted correctly in its share and in the speed table"),
]
WHERE = {"live talk": "Live talk", "voice": "Voice question"}


def _t(r):
    return dt.datetime.fromisoformat(r["ts"])


def _family(engine):
    return (engine or "?").split(":")[0]


def collect(start, end):
    """Counts for [start, end) (aware datetimes), the team left out."""
    rows = [r for r in events.rows() if start <= _t(r) < end]
    people = lambda kind=None: {r["who"] for r in rows if r["who"] and not r["who"].startswith("g")  # noqa: E731
                                and (kind is None or r["kind"] == kind)}
    talk = [r for r in rows if r["kind"] in ("understand", "message")]
    days = {}
    for r in rows:
        if r["who"] and not r["who"].startswith("g"):
            days.setdefault(r["who"], set()).add(_t(r).astimezone(WAT).date())
    per_day = {}
    d = start.astimezone(WAT).date()
    while d < end.astimezone(WAT).date():
        per_day[d.strftime("%a %d %b")] = 0
        d += dt.timedelta(days=1)
    for r in talk:
        k = _t(r).astimezone(WAT).strftime("%a %d %b")
        if k in per_day:
            per_day[k] += 1
    where = {}
    for r in talk:
        k = ("Telegram" if r["channel"] == "telegram" else "WhatsApp") if r["kind"] == "message" else \
            WHERE.get(r["engine"], "Ask chat")
        where[k] = where.get(k, 0) + 1
    langs = {}
    for r in talk:
        langs[r["lang"] or "Not set"] = langs.get(r["lang"] or "Not set", 0) + 1
    llm_ok = [r for r in rows if r["kind"] == "llm" and r["ok"]]
    models = {}
    for r in llm_ok:
        k = "N-ATLaS" if events.is_natlas(r) else f"Backup AI ({(r['engine'] or '?').split('/')[-1]})"
        models[k] = models.get(k, 0) + 1
    hearing = {}
    for r in rows:
        if r["kind"] == "hear" and r["ok"]:
            k = {"natlas": "N-ATLaS speech", "intron": "Intron", "intron-stream": "Intron (live talk)"}.get(
                _family(r["engine"]), _family(r["engine"]))
            hearing[k] = hearing.get(k, 0) + 1
    import team
    problems = {}
    for r in rows:
        if not r["ok"]:
            words = team.describe(r)[1]
            problems[words] = problems.get(words, 0) + 1
    ms = [r["ms"] for r in rows if r["kind"] == "understand" and r["ms"] is not None]
    signups = [r for r in rows if r["kind"] == "signup"]
    return {
        "events": len(rows),
        "traders": len(people()),
        "signups": len(signups),
        "signups_nocode": sum(1 for r in signups if r["engine"] == "no code"),
        "conversations": len(talk),
        "records": sum(1 for r in rows if r["kind"] == "record_saved"),
        "customers": sum(1 for r in rows if r["kind"] == "customer_added"),
        "voice_heard": sum(1 for r in rows if r["kind"] == "hear" and r["ok"]),
        "voice_replies": sum(1 for r in rows if r["kind"] == "voice" and r["ok"]),
        "photos": sum(1 for r in rows if r["kind"] == "photo_read" and r["ok"]),
        "unanswered": sum(1 for r in rows if r["kind"] == "unanswered"),
        "ai_answers": len(llm_ok),
        "natlas_share": round(100 * models.get("N-ATLaS", 0) / len(llm_ok)) if llm_ok else None,
        "natlas_failed": sum(1 for r in rows if r["kind"] == "llm" and not r["ok"] and events.is_natlas(r)),
        "reply_s": round(statistics.median(ms) / 1000, 1) if ms else None,
        "per_day": per_day, "where": dict(sorted(where.items(), key=lambda kv: -kv[1])),
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "models": dict(sorted(models.items(), key=lambda kv: -kv[1])),
        "hearing": dict(sorted(hearing.items(), key=lambda kv: -kv[1])),
        "speed": events._speed_table(rows),
        "funnel": [("Opened the app or wrote to a bot", len(people("web_visit") | people("message"))),
                   ("Signed up", len(people("signup"))),
                   ("Saved a record", len(people("record_saved"))),
                   ("Came back another day", sum(1 for w in days if len(days[w]) > 1))],
        "problems": sorted(problems.items(), key=lambda kv: -kv[1])[:10],
        "team_left_out": len(events.team_phones()),
    }


# ---------------------------------------------------------------- the page

def bars(data, unit=""):
    """Horizontal bars, one row per item, value written at the end (no legend needed)."""
    if not data:
        return '<p class="muted">Nothing yet in this window.</p>'
    top = max(data.values()) or 1
    rows = []
    for k, v in data.items():
        w = max(2, round(100 * v / top))
        rows.append(f'<div class="bar"><span class="k">{html.escape(str(k))}</span><span class="track">'
                    f'<span class="fill" style="width:{w}%"></span></span><span class="v">{v:,}{unit}</span></div>')
    return "".join(rows)


def columns(data):
    """Conversations per day as columns, labelled under each day, value on top."""
    if not data:
        return ""
    top, n = max(data.values()) or 1, len(data)
    w, h, gap = 640, 200, 10
    bw = (w - gap * (n - 1)) / n
    parts = []
    for i, (k, v) in enumerate(data.items()):
        x, bh = i * (bw + gap), (h - 40) * v / top
        y = h - 24 - bh
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(bh, 1):.1f}" rx="4" class="col"/>'
                     f'<text x="{x + bw / 2:.1f}" y="{y - 5:.1f}" class="val">{v}</text>'
                     f'<text x="{x + bw / 2:.1f}" y="{h - 6}" class="lab">{html.escape(k[4:])}</text>')
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Conversations per day">{"".join(parts)}</svg>'


def tile(label, value, note=""):
    v = "n/a" if value is None else value
    return f'<div class="tile"><b>{v}</b><span>{html.escape(label)}</span>{f"<small>{html.escape(note)}</small>" if note else ""}</div>'


def render(d, start, end):
    first, last = start.astimezone(WAT).date(), (end - dt.timedelta(seconds=1)).astimezone(WAT).date()
    speed = "".join(f"<tr><td>{html.escape(n)}</td><td>{c}</td><td>{m / 1000:.1f} s</td><td>{p / 1000:.1f} s</td></tr>"
                    for n, c, m, p, _ in d["speed"]) or '<tr><td colspan="4" class="muted">No timed turns yet.</td></tr>'
    problems = "".join(f"<li>{html.escape(w)}: {n}</li>" for w, n in d["problems"]) or "<li>None recorded.</li>"
    changes = "".join(f"<li><b>{day}</b> {html.escape(c)}</li>" for day, c in CHANGES)
    nocode = f"{d['signups_nocode']} without a code (no SMS phone yet)" if d["signups_nocode"] else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TradeVoice pilot validation</title><style>
:root{{--bg:#f7f6f3;--card:#fff;--ink:#16161d;--muted:#5f5f6b;--hair:#e4e2dc;--accent:#3B4CE0}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111116;--card:#1b1b22;--ink:#f1f0ec;--muted:#a3a2ab;--hair:#2c2c35;--accent:#6f7cf2}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:760px;margin:0 auto;padding:32px 16px 64px}} h1{{font-size:1.9rem;margin:0 0 4px}} h2{{font-size:1.15rem;margin:32px 0 10px}}
.muted{{color:var(--muted)}} .card{{background:var(--card);border:1px solid var(--hair);border-radius:16px;padding:16px 18px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.tile{{background:var(--card);border:1px solid var(--hair);border-radius:14px;padding:12px 14px;display:grid}}
.tile b{{font-size:1.6rem;font-variant-numeric:tabular-nums}} .tile span{{color:var(--muted);font-size:.85rem}} .tile small{{color:var(--muted);font-size:.75rem}}
.bar{{display:grid;grid-template-columns:minmax(120px,34%) 1fr 64px;gap:10px;align-items:center;margin:6px 0}}
.bar .k{{font-size:.9rem}} .track{{background:var(--hair);border-radius:6px;height:12px;overflow:hidden}} .fill{{display:block;height:100%;background:var(--accent);border-radius:6px}}
.bar .v{{text-align:right;font-variant-numeric:tabular-nums}} svg{{width:100%;height:auto}} .col{{fill:var(--accent)}}
.val,.lab{{font-size:12px;text-anchor:middle;fill:var(--muted)}} table{{width:100%;border-collapse:collapse}} td,th{{padding:6px 4px;border-bottom:1px solid var(--hair);text-align:left;font-variant-numeric:tabular-nums}}
li{{margin:4px 0}} footer{{margin-top:36px;font-size:.85rem;color:var(--muted)}} @media print{{body{{background:#fff}} .card,.tile{{break-inside:avoid}}}}
</style></head><body><main>
<p class="muted">NAIC 2026 · Innovation and Enterprise · PS2 Voice-First Access</p>
<h1>TradeVoice pilot: real-world validation</h1>
<p class="muted">{first:%d %B} to {last:%d %B %Y}, Lagos time. From the live app's own event log at tradevoice.duckdns.org.
Counts only: the log never holds names, phone numbers, amounts or words. The team's own {d["team_left_out"]} phone(s) are left out of every number.</p>

<h2>At a glance</h2><div class="tiles">
{tile("traders who used it", d["traders"])}{tile("new sign-ups", d["signups"], nocode)}{tile("conversations", d["conversations"], "spoken or typed turns")}
{tile("records saved", d["records"])}{tile("voice notes heard", d["voice_heard"])}{tile("AI answers from N-ATLaS", f"{d['natlas_share']}%" if d["natlas_share"] is not None else None, f"of {d['ai_answers']} AI answers")}
{tile("typical reply time", f"{d['reply_s']} s" if d["reply_s"] is not None else None, "server side, median")}{tile("customers added", d["customers"])}{tile("photos of notebooks read", d["photos"])}
</div>

<h2>Conversations per day</h2><div class="card">{columns(d["per_day"])}</div>
<h2>Where traders talked to it</h2><div class="card">{bars(d["where"])}</div>
<h2>Languages</h2><div class="card">{bars(d["languages"])}</div>
<h2>Which AI understood them</h2><div class="card">{bars(d["models"])}<p class="muted">N-ATLaS is the main model; a backup answers only when it is asleep or busy. N-ATLaS did not answer {d["natlas_failed"]} time(s).</p></div>
<h2>Which model heard their voice</h2><div class="card">{bars(d["hearing"])}</div>
<h2>From first visit to coming back</h2><div class="card">{bars(dict(d["funnel"]))}</div>
<h2>Speed of each step</h2><div class="card"><table><tr><th>Step</th><th>Count</th><th>Typical</th><th>Slow (9 in 10)</th></tr>{speed}</table></div>
<h2>What went wrong</h2><div class="card"><ul>{problems}</ul><p class="muted">{d["unanswered"]} question(s) nothing could answer.</p></div>
<h2>What we changed during the pilot</h2><div class="card"><ul>{changes}</ul></div>

<footer>Made by scripts/validation_report.py from {d["events"]:,} logged events. N-ATLaS powers TradeVoice's understanding and hearing.<br>{ATTRIBUTION}</footer>
</main></body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="2026-10-06", help="first day (Lagos), YYYY-MM-DD")
    ap.add_argument("--end", default="2026-10-12", help="last day (Lagos), YYYY-MM-DD, included")
    ap.add_argument("--out", default="validation.html")
    a = ap.parse_args(argv)
    start = dt.datetime.combine(dt.date.fromisoformat(a.start), dt.time(), WAT)
    end = dt.datetime.combine(dt.date.fromisoformat(a.end) + dt.timedelta(days=1), dt.time(), WAT)
    d = collect(start, end)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render(d, start, end))
    print(f"{a.out}: {d['traders']} traders, {d['signups']} sign-ups, {d['conversations']} conversations, "
          f"{d['records']} records, N-ATLaS answered {d['natlas_share'] if d['natlas_share'] is not None else 'n/a'}% "
          f"of {d['ai_answers']} AI answers ({a.start} to {a.end}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
