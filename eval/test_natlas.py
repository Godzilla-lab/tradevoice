"""N-ATLaS is the main brain: tried first, with the model card's settings and worked examples, and the backups
take over when it is down. No GPU or network: a fake server stands in for N-ATLaS and the cloud.

python eval/test_natlas.py
"""
import datetime as dt
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
for k in ("NVIDIA_API_KEY", "LOCAL_LLM_URL", "NATLAS_URL", "NATLAS_KEY", "LLM_SHOTS_FOR"):
    os.environ.pop(k, None)
import extract  # noqa: E402
import llm  # noqa: E402

CALLS = []      # (model name as sent, kwargs)
DOWN = set()    # served names that fail
REPLY = {}      # served name -> reply text


class Err(Exception):
    def __init__(self, status):
        super().__init__(f"status {status}")
        self.status_code = status


def fake_client(kind, timeout, retries=0, model=None):
    def create(**kw):
        CALLS.append((kw["model"], kw))
        if kw["model"] in DOWN:
            raise Err(401 if kw["model"] == "natlas" else 503)
        text = REPLY.get(kw["model"], '{"ok": true}')
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


llm._client = fake_client
passed = total = 0


def check(name, cond):
    global passed, total
    total += 1
    passed += bool(cond)
    print(f"{'✓' if cond else '✗'} {name}")


def reset(env=None, down=(), models=("cloud/a", "cloud/b")):
    CALLS.clear()
    DOWN.clear()
    DOWN.update(down)
    REPLY.clear()
    llm._working.clear()
    llm._resting.clear()
    llm.LLM_MODELS[:] = list(models)
    for k in ("NVIDIA_API_KEY", "NATLAS_URL", "LOCAL_LLM_URL"):
        os.environ.pop(k, None)
    os.environ.update(env or {})


SYS = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
SHOTS = [("u1", "a1"), ("u2", "a2")]
BOTH = {"NVIDIA_API_KEY": "x", "NATLAS_URL": "http://natlas/v1"}

# 1. N-ATLaS first, with the card's settings
reset(BOTH)
out, model = llm.chat(SYS, shots=SHOTS)
name, kw = CALLS[0]
check("N-ATLaS is tried first when NATLAS_URL is set", name == "natlas" and len(CALLS) == 1)
check("answer is labelled as N-ATLaS (for /team engine share)", model == "natlas:NCAIR1/N-ATLaS"
      and llm.is_natlas(model))
check("card settings: temperature 0.1, repetition penalty 1.12", kw["temperature"] == 0.1
      and kw["extra_body"]["repetition_penalty"] == 1.12)
check("chat template gets today's date_string", kw["extra_body"]["chat_template_kwargs"]["date_string"])
roles = [m["role"] for m in kw["messages"]]
check("worked examples go between the system prompt and the question",
      roles == ["system", "user", "assistant", "user", "assistant", "user"]
      and kw["messages"][1]["content"] == "u1" and kw["messages"][-1]["content"] == "hi")

# 2. N-ATLaS down (any error, even auth) -> the backups answer
reset(BOTH, down={"natlas"})
out, model = llm.chat(SYS, shots=SHOTS)
check("N-ATLaS down (401) -> next model answers instead of failing", model == "cloud/a"
      and [c[0] for c in CALLS] == ["natlas", "cloud/a"])
check("cloud models don't get the examples or N-ATLaS settings",
      len(CALLS[1][1]["messages"]) == 2 and "extra_body" not in CALLS[1][1] and CALLS[1][1]["temperature"] == 0.0)

# 3. after a fallback, N-ATLaS still leads once it is back (and its rest period is over)
DOWN.clear()
llm._resting.clear()
out, model = llm.chat(SYS)
check("N-ATLaS leads again after recovering (not pushed behind the last good backup)", model.startswith("natlas"))

# 4. only N-ATLaS configured (no NVIDIA key)
reset({"NATLAS_URL": "http://natlas/v1"})
check("N-ATLaS alone counts as 'AI available'", llm.available() and not llm.available("vision"))
out, model = llm.chat(SYS)
check("without NVIDIA key only N-ATLaS is tried", [c[0] for c in CALLS] == ["natlas"])

# 5. not configured -> never tried
reset({"NVIDIA_API_KEY": "x"}, models=("natlas", "cloud/a"))
out, model = llm.chat(SYS)
check("no NATLAS_URL -> N-ATLaS skipped even if listed", model == "cloud/a" and "natlas" not in [c[0] for c in CALLS])

# 6. vision is never sent to N-ATLaS (text-only model)
reset(BOTH)
llm.VISION_MODELS[:] = ["cloud/vision"]
out, model = llm.chat([{"role": "user", "content": "photo"}], kind="vision")
check("photos go to the vision models, not N-ATLaS", model == "cloud/vision")

# 7. benchmarks can give everyone the examples, or nobody
reset(BOTH, down={"natlas"})
llm.SHOTS_FOR = "all"
llm.chat(SYS, shots=SHOTS)
check("LLM_SHOTS_FOR=all gives the backup the examples too (fair benchmark)", len(CALLS[1][1]["messages"]) == 6)
reset(BOTH)
llm.SHOTS_FOR = ""
llm.chat(SYS, shots=SHOTS)
check("LLM_SHOTS_FOR='' = zero-shot N-ATLaS", len(CALLS[0][1]["messages"]) == 2)
llm.SHOTS_FOR = "natlas"

# 8. end to end: extract() records the engine, and our guards still check N-ATLaS
TODAY = dt.date(2026, 9, 27)
reset({"NATLAS_URL": "http://natlas/v1"})
REPLY["natlas"] = json.dumps({"type": "credit_sale", "item": "rice", "quantity": 2, "unit": "bag", "amount": 20000,
                              "customer": "Mama Ada", "due_date": None, "confidence": 0.9, "note": None})
rec, meta = extract.extract("Sold 2 bags of rice to Mama Ada for 20k, she will pay later", today=TODAY)
check("extract() says N-ATLaS made the record", llm.is_natlas(meta["engine"]) and rec["amount"] == 20000)
check("extract() sends N-ATLaS the 5 worked examples (one per language)",
      len(CALLS[0][1]["messages"]) == 2 + 2 * len(extract.SHOTS) and len(extract.SHOTS) == 5)
REPLY["natlas"] = json.dumps({"type": "sale", "amount": 5000, "customer": "Mama Ada"})
rec, meta = extract.extract("Mama Ada never pay the 5000 for rice", today=TODAY)
check("rules still overrule N-ATLaS ('never pay' = credit, not a sale)", rec["type"] == "credit_sale")
REPLY["natlas"] = "Sorry, I can't help with that."
rec, meta = extract.extract("Sold beans for 3000", today=TODAY)
check("N-ATLaS gives no JSON -> offline rules, never a crash", meta["engine"].startswith("rules")
      and rec["amount"] == 3000)

# 9. the worked examples are valid records, and their amounts were said in their sentences
ok = True
for text, answer in extract.SHOTS:
    a = json.loads(answer)
    ok &= a["type"] in extract.TYPES and a["customer"] in (None,) + tuple([a["customer"]] if a["customer"]
                                                                            and a["customer"] in text else [])
check("worked examples are valid records with names that appear in the sentence", ok)

print(f"\n{passed}/{total} N-ATLaS checks pass")
sys.exit(0 if passed == total else 1)
