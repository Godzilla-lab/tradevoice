"""Load .env automatically (so `python src/app.py` works without `set -a; source .env; set +a`).
The .env file wins over values inherited from the shell or tmux: tmux keeps the .env from when Brev started, so
an edited key (a new WhatsApp token) would otherwise be ignored until tmux restarts. Never prints values."""
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")  # .env lives at the repo root


def load(path=_PATH):
    if os.getenv("TV_NO_DOTENV") or not os.path.exists(path):  # tests use their own fake keys
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
        if key:
            os.environ[key] = value


load()
