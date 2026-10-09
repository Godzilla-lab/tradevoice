"""The NAIC PDFs from the markdown documents, with the browser that comes with Playwright (Chromium).

    pip install markdown            (once; a laptop tool, not needed on the server)
    python scripts/make_pdfs.py     -> docs/naic/pdf/*.pdf

Makes: N-ATLaS integration evidence, technical documentation, team profile, validation write-up (the numbers page
comes from deploy/server/validation_report.sh: open it and Save as PDF), and the video script for the team.
"""
import html
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "naic", "pdf")
DOCS = [   # (markdown, pdf name, title on the page)
    ("docs/naic/NATLAS_INTEGRATION.md", "TradeVoice-NATLAS-integration.pdf", "N-ATLaS integration evidence"),
    ("docs/TECHNICAL.md", "TradeVoice-technical-documentation.pdf", "Technical documentation"),
    ("docs/naic/VALIDATION.md", "TradeVoice-validation-writeup.pdf", "Real-world validation"),
    ("docs/naic/TEAM_PROFILE.md", "TradeVoice-team-profile.pdf", "Team profile"),
    ("docs/naic/VIDEO_SCRIPT.md", "TradeVoice-video-script.pdf", "Video script"),
]
CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font: 10.5pt/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #16161d; }
h1 { font-size: 20pt; margin: 0 0 6pt; } h2 { font-size: 13.5pt; margin: 18pt 0 6pt; border-bottom: 1px solid #e4e2dc; padding-bottom: 3pt; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; } p, li { margin: 4pt 0; } a { color: #3B4CE0; text-decoration: none; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 9.5pt; } tr { break-inside: avoid; }
h1, h2, h3 { break-after: avoid; page-break-after: avoid; }
th, td { border: 1px solid #e4e2dc; padding: 4pt 6pt; text-align: left; vertical-align: top; } th { background: #f4f3ef; }
code { font: 9pt Menlo, Consolas, monospace; background: #f4f3ef; padding: 0 2pt; border-radius: 2pt; }
pre { background: #f4f3ef; padding: 8pt; border-radius: 4pt; font-size: 8pt; white-space: pre; overflow: hidden; page-break-inside: avoid; }
pre code { background: none; padding: 0; } .brand { color: #5f5f6b; font-size: 9pt; margin-bottom: 10pt; }
"""


LIST = re.compile(r"^\s*([-*]|\d+\.)\s")


def tidy(md):
    """GitHub-style markdown -> what Python-Markdown expects: a blank line before a list, 4-space nesting."""
    out, code = [], False
    for line in md.split("\n"):
        if line.lstrip().startswith("```"):
            code = not code
        elif not code:
            if LIST.match(line) and out and out[-1].strip() and not LIST.match(out[-1]) \
                    and not out[-1].startswith((" ", "|")):
                out.append("")
            m = re.match(r"^( {1,3})(\S)", line)
            if m:
                line = " " * (2 * len(m.group(1))) + line[len(m.group(1)):]
        out.append(line)
    return "\n".join(out)


def page(md_text, title):
    import markdown
    body = markdown.markdown(tidy(md_text), extensions=["tables", "fenced_code", "sane_lists"])
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>TradeVoice: {html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body><div class=\"brand\">TradeVoice · NAIC 2026 · {html.escape(title)}</div>"
            f"{body}</body></html>")


PRINT_JS = """
const { chromium } = require("playwright");
(async () => {
  const [src, out] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto("file://" + src, { waitUntil: "load" });
  await p.pdf({ path: out, format: "A4", printBackground: true,
    displayHeaderFooter: true, headerTemplate: "<span></span>",
    footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#888">TradeVoice · page <span class="pageNumber"></span> of <span class="totalPages"></span></div>',
    margin: { top: "16mm", bottom: "16mm", left: "14mm", right: "14mm" } });
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
"""


def main():
    try:
        import markdown  # noqa: F401
    except ImportError:
        sys.exit("Needs the markdown package: pip install markdown")
    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp()
    js = os.path.join(work, "print.cjs")
    with open(js, "w") as f:
        f.write(PRINT_JS)
    npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    env = dict(os.environ, NODE_PATH=os.environ.get("NODE_PATH") or npm_root)
    made = 0
    for src, name, title in DOCS:
        path = os.path.join(ROOT, src)
        if not os.path.exists(path):
            print(f"skipped (not written yet): {src}")
            continue
        htm = os.path.join(work, name.replace(".pdf", ".html"))
        with open(htm, "w", encoding="utf-8") as f:
            f.write(page(open(path, encoding="utf-8").read(), title))
        r = subprocess.run(["node", js, htm, os.path.join(OUT, name)], env=env, capture_output=True, text=True)
        if r.returncode:
            print(f"failed: {src}: {r.stderr.strip()[:300]}")
            continue
        made += 1
        print(f"made docs/naic/pdf/{name}")
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
