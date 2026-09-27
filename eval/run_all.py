"""Run every automated check (no keys, no network, no GPU needed).   python eval/run_all.py"""
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
total = passed = 0
failed = []
for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
    out = subprocess.run([sys.executable, path], capture_output=True, text=True, cwd=os.path.dirname(HERE))
    m = (re.findall(r"^(\d+)/(\d+) \w", out.stdout, re.M) or [None])[-1]
    ok, n = (int(m[0]), int(m[1])) if m else (0, 0)
    total, passed = total + n, passed + ok
    good = out.returncode == 0 and m and ok == n
    print(f"{'✓' if good else '✗'} {os.path.basename(path):26} {ok}/{n}")
    if not good:
        failed.append(os.path.basename(path))
        print(out.stdout[-1500:], out.stderr[-1500:])
print(f"\n{passed}/{total} checks pass in {len(glob.glob(os.path.join(HERE, 'test_*.py')))} suites")
sys.exit(1 if failed else 0)
