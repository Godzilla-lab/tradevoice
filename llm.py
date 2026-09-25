"""One place for every call to NVIDIA's API (build.nvidia.com), with model fallback.

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
    "LLM_MODELS", os.getenv("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b,google/gemma-4-31b-it,"
                                         "qwen/qwen3.5-397b-a17b,meta/llama-3.3-70b-instruct")).split(",") if m.strip()]
VISION_MODELS = [m.strip() for m in os.getenv(
    "VISION_MODELS", os.getenv("VISION_MODEL", "google/gemma-4-31b-it,qwen/qwen3.5-397b-a17b,"
                                               "nvidia/nemotron-nano-12b-v2-vl,meta/llama-3.2-90b-vision-instruct")).split(",") if m.strip()]
VISION_BASE_URL = os.getenv("VISION_BASE_URL", NVIDIA_BASE_URL)
# Backup brain on OUR Brev GPU: any OpenAI-compatible server (vLLM, NVIDIA NIM). Tried LAST, after the cloud models,
# with time kept aside for it. Put "local" in LLM_MODELS to choose its place yourself (LLM_MODELS=local = local only).
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")
# Photo reader on OUR Brev GPU too (vision model served by vLLM): LOCAL_VISION_URL + LOCAL_VISION_MODEL.
LOCAL_VISION_MODEL = os.getenv("LOCAL_VISION_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct-AWQ")
LOCAL_ENV = {"llm": "LOCAL_LLM_URL", "vision": "LOCAL_VISION_URL"}


def _local_name(kind):
    return LOCAL_VISION_MODEL if kind == "vision" else LOCAL_LLM_MODEL
LOCAL_RESERVE = float(os.getenv("LOCAL_LLM_RESERVE", "10"))      # seconds of the deadline kept for the local model
COOLDOWN = float(os.getenv("LLM_COOLDOWN", "120"))               # skip a model this long after it times out / 5xx

_working = {}  # kind -> model that last worked
_resting = {}  # model -> time until which we skip it (timed out / overloaded recently)


def available(kind="llm"):
    """Is any AI configured? (cloud key, or for text also our own GPU model)"""
    return bool(os.getenv("NVIDIA_API_KEY") or os.getenv(LOCAL_ENV[kind])
                or (kind == "vision" and os.getenv("VISION_API_KEY")))


def _client(kind, timeout, retries=0, model=None):
    from openai import OpenAI

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


def chat(messages, kind="llm", max_tokens=400, temperature=0.0, timeout=60, models=None, deadline=None, retries=0):
    """Return (text, model_used). Tries each configured model (or `models`) until one answers.
    `deadline` (seconds, default LLM_DEADLINE=30) caps the TOTAL wait across all models, so a live demo never
    hangs: when it runs out the caller falls back to the offline rules."""
    pinned = models is not None
    models = list(models or (VISION_MODELS if kind == "vision" else LLM_MODELS))
    if os.getenv(LOCAL_ENV[kind]) and not pinned and "local" not in models:
        models.append("local")                    # our own GPU model: the last AI before the offline rules
    if not os.getenv("NVIDIA_API_KEY"):
        models = [m for m in models if m == "local"]
    if not pinned:
        now = time.time()
        fresh = [m for m in models if _resting.get(m, 0) <= now]
        models = fresh or models                  # skip models that just timed out (unless all did)
        if _working.get(kind) in models:          # try the last good model first
            models = [_working[kind]] + [m for m in models if m != _working[kind]]
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
        client = _client(kind, min(timeout, budget), retries, model)
        try:
            resp = client.chat.completions.create(model=_local_name(kind) if model == "local" else model,
                                                  messages=messages, temperature=temperature, max_tokens=max_tokens)
            if not pinned:
                _working[kind] = model
                _resting.pop(model, None)
            return clean(resp.choices[0].message.content), (f"local:{_local_name(kind)}" if model == "local" else model)
        except Exception as e:  # noqa: BLE001
            last = e
            if not _model_gone(e):
                raise  # network / auth / rate-limit after retries: let the caller fall back to rules
            if not pinned:
                _resting[model] = time.time() + COOLDOWN
    raise RuntimeError(f"No configured {kind} model is available (last error: {last})")
