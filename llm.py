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

_working = {}  # kind -> model that last worked


def _client(kind, timeout, retries=0):
    from openai import OpenAI

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
    models = models or (VISION_MODELS if kind == "vision" else LLM_MODELS)
    if not pinned and _working.get(kind) in models:  # try the last good model first
        models = [_working[kind]] + [m for m in models if m != _working[kind]]
    deadline = float(deadline or os.getenv("LLM_DEADLINE", "30"))
    start = time.perf_counter()
    last = None
    for model in models:
        remaining = deadline - (time.perf_counter() - start)
        if remaining < 3:
            last = last or TimeoutError(f"gave up after {deadline:.0f} s")
            break
        client = _client(kind, min(timeout, remaining), retries)
        try:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature,
                                                  max_tokens=max_tokens)
            if not pinned:
                _working[kind] = model
            return clean(resp.choices[0].message.content), model
        except Exception as e:  # noqa: BLE001
            last = e
            if not _model_gone(e):
                raise  # network / auth / rate-limit after retries: let the caller fall back to rules
    raise RuntimeError(f"No configured {kind} model is available (last error: {last})")
