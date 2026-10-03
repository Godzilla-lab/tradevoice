"""One place for every call to a language model, with model fallback.

N-ATLaS FIRST: when NATLAS_URL is set, N-ATLaS (NCAIR1/N-ATLaS, Llama-3 8B, on our Modal GPU: deploy/modal_natlas.py)
is tried before anything else. The cloud models and our Brev model are only backups when it is down, and every
answer says which model gave it, so /team can show N-ATLaS's share. Card settings: temperature 0.1,
repetition penalty 1.12, Llama-3.1 chat template with date_string, 8,092-token context.

Models on build.nvidia.com get deprecated (Llama 3.3 70B was scheduled for 25 Aug 2026), so we try a list in order
and remember the first one that works. Override with LLM_MODELS / VISION_MODELS (comma-separated).
Vision order favours multilingual models (Gemma 4, Qwen 3.5) for Yoruba/Igbo/Hausa pages; Llama 3.2 Vision is last
because Meta supports English only for image+text. See docs/RESEARCH.md → "Nigerian languages".
"""
import os
import re
import time

NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
LLM_MODELS = [m.strip() for m in os.getenv(
    "LLM_MODELS", os.getenv("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b,google/gemma-4-31b-it")).split(",") if m.strip()]
VISION_MODELS = [m.strip() for m in os.getenv(
    "VISION_MODELS", os.getenv("VISION_MODEL", "google/gemma-4-31b-it,meta/llama-3.2-11b-vision-instruct")).split(",") if m.strip()]
VISION_BASE_URL = os.getenv("VISION_BASE_URL", NVIDIA_BASE_URL)
# Backup brain on OUR Brev GPU: any OpenAI-compatible server (vLLM, NVIDIA NIM). Tried LAST, after the cloud models,
# with time kept aside for it. Put "local" in LLM_MODELS to choose its place yourself (LLM_MODELS=local = local only).
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")
# Photo reader on OUR Brev GPU too (vision model served by vLLM): LOCAL_VISION_URL + LOCAL_VISION_MODEL.
LOCAL_VISION_MODEL = os.getenv("LOCAL_VISION_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct-AWQ")
LOCAL_ENV = {"llm": "LOCAL_LLM_URL", "vision": "LOCAL_VISION_URL"}
# N-ATLaS: the main brain (text only; photos still go to the vision models)
NATLAS_MODEL = os.getenv("NATLAS_MODEL", "natlas")              # the --served-model-name on our vLLM server
NATLAS_TEMPERATURE = float(os.getenv("NATLAS_TEMPERATURE", "0.1"))
NATLAS_REPETITION_PENALTY = float(os.getenv("NATLAS_REPETITION_PENALTY", "1.12"))
OWN_SERVERS = ("natlas", "local")                                 # models that don't need NVIDIA_API_KEY
# which models get the worked examples (`shots`); benchmarks set LLM_SHOTS_FOR=all to compare fairly
SHOTS_FOR = os.getenv("LLM_SHOTS_FOR", "natlas")


def _local_name(kind):
    return LOCAL_VISION_MODEL if kind == "vision" else LOCAL_LLM_MODEL
LOCAL_RESERVE = float(os.getenv("LOCAL_LLM_RESERVE", "10"))      # seconds of the deadline kept for the local model
COOLDOWN = float(os.getenv("LLM_COOLDOWN", "120"))               # skip a model this long after it times out / 5xx

_working = {}  # kind -> model that last worked
_resting = {}  # model -> time until which we skip it (timed out / overloaded recently)


def natlas_on():
    return bool(os.getenv("NATLAS_URL"))


def available(kind="llm"):
    """Is any AI configured? (cloud key, or for text also N-ATLaS / our own GPU model)"""
    return bool(os.getenv("NVIDIA_API_KEY") or os.getenv(LOCAL_ENV[kind])
                or (kind == "vision" and os.getenv("VISION_API_KEY")) or (kind == "llm" and natlas_on()))


def _served_name(kind, model):
    return {"local": _local_name(kind), "natlas": NATLAS_MODEL}.get(model, model)


def _label(kind, model):
    return {"local": f"local:{_local_name(kind)}", "natlas": "natlas:NCAIR1/N-ATLaS"}.get(model, model)


def is_natlas(engine):
    """Did this engine label (from chat() or extract meta) come from N-ATLaS?"""
    return "natlas" in (engine or "").lower()


def wake_natlas():
    """Fire-and-forget ping so a scaled-to-zero Modal container starts loading before the trader's next message."""
    if not natlas_on():
        return

    def ping():
        try:
            import requests
            requests.get(os.environ["NATLAS_URL"].rstrip("/") + "/models", timeout=300,
                         headers={"Authorization": f"Bearer {os.getenv('NATLAS_KEY', 'none')}"})
        except Exception:  # noqa: BLE001  (best effort)
            pass
    import threading
    threading.Thread(target=ping, daemon=True).start()


def _client(kind, timeout, retries=0, model=None):
    from openai import OpenAI

    if model == "natlas":  # N-ATLaS on Modal (vLLM, OpenAI-compatible), e.g. https://<you>--tradevoice-natlas-serve.modal.run/v1
        return OpenAI(base_url=os.environ["NATLAS_URL"], api_key=os.getenv("NATLAS_KEY", "none"),
                      timeout=timeout, max_retries=retries)
    if model == "local":  # our own Brev GPU, e.g. http://localhost:8001/v1 (LLM) / :8002/v1 (vision)
        return OpenAI(base_url=os.environ[LOCAL_ENV[kind]], api_key=os.getenv("LOCAL_LLM_KEY", "local"),
                      timeout=timeout, max_retries=retries)
    if kind == "vision":
        return OpenAI(base_url=VISION_BASE_URL, api_key=os.getenv("VISION_API_KEY") or os.environ["NVIDIA_API_KEY"],
                      timeout=timeout, max_retries=retries)
    # no silent retries by default: if a model is slow or flaky we move to the next model instead of making the trader wait
    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=os.environ["NVIDIA_API_KEY"], timeout=timeout, max_retries=retries)


def _model_gone(err):
    """Errors that mean 'try the next model': model removed/forbidden, or too slow/overloaded right now."""
    status = getattr(err, "status_code", None)
    text = str(err).lower()
    if type(err).__name__ in ("APITimeoutError", "Timeout", "ReadTimeout", "APIConnectionError"):
        return True
    return status in (400, 403, 404, 410, 422, 429, 500, 502, 503, 504) or any(
        s in text for s in ("not found", "deprecated", "does not exist", "unknown model", "not supported", "timed out"))


def clean(text):
    """Drop reasoning traces some models (e.g. Nemotron) emit before the answer."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    return text.strip()


def _event(kind, engine, ok, start):
    """Which model answered (for /team and the NAIC 'N-ATLaS share'). Never raises."""
    try:
        import events
        events.log("llm" if kind == "llm" else "photo_read", engine=engine, ok=ok,
                   ms=(time.perf_counter() - start) * 1000)
    except Exception:  # noqa: BLE001
        pass


def _with_shots(messages, shots):
    """Insert worked examples (user, assistant) pairs right after the system message."""
    if not shots:
        return messages
    head = [m for m in messages[:1] if m.get("role") == "system"]
    pairs = [{"role": r, "content": c} for u, a in shots for r, c in (("user", u), ("assistant", a))]
    return head + pairs + messages[len(head):]


def chat(messages, kind="llm", max_tokens=400, temperature=0.0, timeout=60, models=None, deadline=None, retries=0,
         shots=None, schema=None):
    """Return (text, model_used). Tries each configured model (or `models`) until one answers.
    `deadline` (seconds, default LLM_DEADLINE=30) caps the TOTAL wait across all models, so a live demo never
    hangs: when it runs out the caller falls back to the offline rules.
    `shots`: worked examples [(user, assistant), ...] given to N-ATLaS only (an 8B model gains ~10 points from
    examples, independent AfroBench evaluation; the big cloud models don't need the extra tokens).
    `schema`: a JSON schema N-ATLaS must follow (vLLM guided decoding: always valid JSON and valid tool names);
    other models just get the prompt, and the caller checks what comes back."""
    pinned = models is not None
    models = list(models or (VISION_MODELS if kind == "vision" else LLM_MODELS))
    if kind == "llm" and natlas_on() and not pinned and "natlas" not in models:
        models.insert(0, "natlas")                # N-ATLaS is the main brain; everything else is a backup
    if os.getenv(LOCAL_ENV[kind]) and not pinned and "local" not in models:
        models.append("local")                    # our own GPU model: the last AI before the offline rules
    if not os.getenv("NVIDIA_API_KEY"):
        models = [m for m in models if m in OWN_SERVERS]
    if not natlas_on():
        models = [m for m in models if m != "natlas"]
    if not pinned:
        now = time.time()
        fresh = [m for m in models if _resting.get(m, 0) <= now]
        models = fresh or models                  # skip models that just timed out (unless all did)
        if _working.get(kind) in models and "natlas" not in models:   # try the last good model first
            models = [_working[kind]] + [m for m in models if m != _working[kind]]   # (N-ATLaS always leads)
    deadline = float(deadline or os.getenv("LLM_DEADLINE", "30"))
    start = time.perf_counter()
    last = None
    for i, model in enumerate(models):
        remaining = deadline - (time.perf_counter() - start)
        # keep time for the local model if it is still to come
        budget = remaining - (LOCAL_RESERVE if "local" in models[i + 1:] else 0)
        if budget < 3:
            if model != "local" and "local" in models[i + 1:] and remaining >= 3:
                continue                          # skip ahead: the local model gets the reserved time
            last = last or TimeoutError(f"gave up after {deadline:.0f} s")
            break
        wait = min(timeout, budget)
        extra = {}
        msgs, temp = messages, temperature
        if SHOTS_FOR == "all" or model in SHOTS_FOR.split(","):
            msgs = _with_shots(messages, shots)
        if model == "natlas":
            wait = min(float(os.getenv("NATLAS_TIMEOUT", timeout)), budget)
            temp = NATLAS_TEMPERATURE
            extra = {"extra_body": {"repetition_penalty": NATLAS_REPETITION_PENALTY,
                                    "chat_template_kwargs": {"date_string": time.strftime("%d %b %Y")}}}
            if schema:
                extra["response_format"] = {"type": "json_schema",
                                            "json_schema": {"name": "answer", "schema": schema}}
        client = _client(kind, wait, retries, model)
        try:
            resp = client.chat.completions.create(model=_served_name(kind, model), messages=msgs,
                                                  temperature=temp, max_tokens=max_tokens, **extra)
            if not pinned:
                _working[kind] = model
                _resting.pop(model, None)
            _event(kind, _label(kind, model), True, start)
            return clean(resp.choices[0].message.content), _label(kind, model)
        except Exception as e:  # noqa: BLE001
            last = e
            if model == "natlas":
                _event(kind, "natlas", False, start)
            if not _model_gone(e) and model != "natlas":   # N-ATLaS down for ANY reason -> the backups
                raise  # network / auth / rate-limit after retries: let the caller fall back to rules
            if not pinned:
                _resting[model] = time.time() + COOLDOWN
    raise RuntimeError(f"No configured {kind} model is available (last error: {last})")
