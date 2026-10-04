"""/team: the team's dashboard (counts only, no names, amounts or messages) and the anonymised CSV export that
backs the NAIC "real-world validation" PDF. Needs ADMIN_TOKEN: /team?key=<ADMIN_TOKEN> (or header X-Admin-Key)."""
import csv
import hmac
import html
import io
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

import events

router = APIRouter()


def _allowed(request: Request):
    want = os.getenv("ADMIN_TOKEN", "")
    got = request.query_params.get("key") or request.headers.get("x-admin-key", "")
    if not want or not hmac.compare_digest(want, got):
        raise HTTPException(403, "Team only")


def _table(title, data, total=None):
    if not data:
        return f"<section><h2>{title}</h2><p class=muted>Nothing yet</p></section>"
    total = total or sum(v for v in data.values() if isinstance(v, (int, float))) or 1
    rows = "".join(f"<tr><td>{html.escape(str(k))}</td><td class=n>{v}</td>"
                   f"<td class=bar><span style='width:{min(100, 100 * v / total):.0f}%'></span></td></tr>"
                   for k, v in data.items())
    return f"<section><h2>{title}</h2><table>{rows}</table></section>"


def _speed():
    """A voice turn, step by step, last 24 hours (times only): which step makes live talk slow."""
    t = events.speed(1)
    if not t:
        return "<section><h2>Speed of a voice turn (last 24 h)</h2><p class=muted>Nothing yet</p></section>"
    rows = "".join(f"<tr><td>{html.escape(n)}</td><td class=n>{c}</td><td class=n>{m / 1000:.1f} s</td>"
                   f"<td class=n>{p / 1000:.1f} s</td><td class=n>{x / 1000:.1f} s</td></tr>" for n, c, m, p, x in t)
    return ("<section><h2>Speed of a voice turn (last 24 h)</h2><table><tr><td class=muted>step</td>"
            "<td class='n muted'>count</td><td class='n muted'>typical</td><td class='n muted'>9 in 10</td>"
            f"<td class='n muted'>slowest</td></tr>{rows}</table></section>")


@router.get("/team", response_class=HTMLResponse)
def team(request: Request):
    _allowed(request)
    s = events.summary()
    key = html.escape(request.query_params.get("key", ""))
    cap = (f"<p class='warn'>{s['active_30d']} active traders in 30 days: the N-ATLaS licence allows 1,000. "
           "Contact Awarri (datasupport@awarri.com) now.</p>") if s["licence_warn"] else ""
    tiles = [("Active traders (30 days)", f"{s['active_30d']} / 1,000"), ("New today", s["new_today"]),
             ("New this week", s["new_7d"]), ("Active this week", s["active_7d"]),
             ("Real interactions", s["interactions"]), ("Records saved", s["records_saved"]),
             ("N-ATLaS share (understanding)", f"{s['natlas_share']}%" if s["natlas_share"] is not None else "-"),
             ("Errors", s["errors"])]
    tiles_html = "".join(f"<div class=tile><b>{v}</b><span>{k}</span></div>" for k, v in tiles)
    first = max(s["funnel"].values()) or 1
    page = f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>TradeVoice team</title><style>
:root{{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e4e4df;--accent:#0f7b5f;--warn:#b54708}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141413;--card:#1f1f1d;--ink:#ecece8;--muted:#a3a39c;--line:#33332f;
--accent:#3fbf96;--warn:#f79009}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif;padding:16px}}
main{{max-width:880px;margin:auto}} h1{{font-size:22px;margin:4px 0 2px}} h2{{font-size:15px;margin:0 0 8px}}
.muted{{color:var(--muted)}} .warn{{color:var(--warn);font-weight:600}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;margin:16px 0}}
.tile,section{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}}
.tile b{{display:block;font-size:22px}} .tile span{{color:var(--muted);font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}}
table{{width:100%;border-collapse:collapse}} td{{padding:3px 0;font-size:14px}} td.n{{text-align:right;padding:0 8px;
font-variant-numeric:tabular-nums}} td.bar{{width:40%}} td.bar span{{display:block;height:8px;border-radius:4px;
background:var(--accent)}} a{{color:var(--accent)}}
</style></head><body><main>
<h1>TradeVoice: team dashboard</h1><p class=muted>Counts only: no names, amounts or messages. Traders are anonymous
codes. Guests (web, not linked): {s['guests_total']}. {f"The team's own {s['team_left_out']} phones are left out (TEAM_PHONES)." if s['team_left_out'] else "Team phones are counted too: list them in TEAM_PHONES to leave them out."}</p>{cap}
<div class=tiles>{tiles_html}</div>{_speed()}<div class=grid>
{_table("Funnel", s["funnel"], first)}
{_table("Channel (traders)", s["channels"])}
{_table("Languages", s["languages"])}
{_table("Messages by type", s["messages_by_type"])}
{_table("Understanding: which model answered", s["understanding"])}
{_table("Hearing: which model", s["hearing"])}
{_table("Voice replies (Intron calls vs free cached)", s["voice_replies"])}
{_table("Tools used (code did the maths)", s["tools"])}
{_table("Two hearings merged by N-ATLaS (Yoruba, Hausa, Igbo)", s["hearing_merge"])}
{_table("Questions nothing could answer (by language): add the common ones as tools", s["unanswered"])}
</div><p><a href="/team/export.csv?key={key}">Download the anonymised interaction log (CSV)</a> · for the NAIC
validation PDF.</p>
<p class=muted>N-ATLaS is an initiative of the Federal Ministry of Communications, Innovation and Digital Economy,
and powered by Awarri Technologies.</p></main></body></html>"""
    return HTMLResponse(page, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.get("/team/export.csv")
def export(request: Request):
    _allowed(request)
    out = io.StringIO()
    w = csv.writer(out)
    cols = ["ts", "who", "channel", "kind", "lang", "engine", "ok", "ms"]
    w.writerow(cols)
    for r in events.rows():
        w.writerow([r[c] for c in cols])
    return Response(out.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=tradevoice-interactions.csv", "Cache-Control": "no-store"})
