"""Load .env automatically (so `python app.py` works without `set -a; source .env; set +a`).
Values already set in the shell win. Never prints values: .env holds keys."""
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load(path=_PATH):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1]:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()  # inline comment
        if key and key not in os.environ:
            os.environ[key] = value


load()
