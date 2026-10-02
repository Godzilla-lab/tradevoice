"""The live app IS the design: web/app.html and web/landing.html are built from design/tradevoice-2.0/ and must keep
its look exactly (every <style> block and the page skeleton byte-identical). Only logic is swapped.

python eval/test_design.py
"""
import os
import re
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DESIGN = os.path.join(ROOT, "design", "tradevoice-2.0")
passed = total = 0


def check(name, cond):
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"{'✓' if cond else '✗'} {name}")


def styles(html):
    return re.findall(r"<style>(.*?)</style>", html, re.S)


def skeleton(html):
    """The page's markup without its scripts (whitespace between tags ignored)."""
    body = re.sub(r"<script.*?</script>", "", html.split("<body>", 1)[1], flags=re.S)
    return re.sub(r">\s+<", "><", body).strip()


out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_app.py")], capture_output=True, text=True)
check("the build applies every logic swap to the current design", out.returncode == 0)
for src, built in (("app.html", "app.html"), ("landing2.html", "landing.html")):
    d = open(os.path.join(DESIGN, src), encoding="utf-8").read()
    b = open(os.path.join(ROOT, "web", built), encoding="utf-8").read()
    check(f"{built}: every style is the design's, byte for byte", styles(d) == styles(b) and len(styles(d)) > 0)
    if built == "app.html":
        check(f"{built}: page skeleton identical to the design", skeleton(d) == skeleton(b))
        check(f"{built}: loads the live layer", '<script src="/static/live.js"></script>' in b)
        check(f"{built}: no account or password is kept in the phone's storage",
              "AC[a.phone]=a" not in b and "!==A.pw" not in b and "!==r.acct.pw" not in b)
    else:
        check(f"{built}: 'Open the app' goes to /app, not a preview link", "claude.ai/artifact" not in b
              and b.count('href="/app"') == 4)
check("the design files themselves are untouched by the build",
      "TVL." not in open(os.path.join(DESIGN, "app.html"), encoding="utf-8").read())

print(f"\n{passed}/{total} design checks pass")
sys.exit(0 if passed == total else 1)
