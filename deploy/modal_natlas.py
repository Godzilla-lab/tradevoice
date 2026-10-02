"""N-ATLaS (NCAIR1/N-ATLaS, Llama-3 8B) on a Modal GPU, as an OpenAI-compatible API (vLLM).

One-time set-up (on your own machine, never paste keys into chat or commit them):
    pip install modal && modal setup
    modal secret create natlas NATLAS_KEY=<long random string> HF_TOKEN=<your Hugging Face read token>

Deploy (prints the URL; add /v1 and put it in .env as NATLAS_URL, with the same NATLAS_KEY):
    modal deploy deploy/modal_natlas.py
    NATLAS_WARM=1 modal deploy deploy/modal_natlas.py     # 1 GPU on day AND night (only if market-hours warmth fails)

Check it:   python scripts/check_models.py --natlas
Benchmark:  python eval/run_eval.py --cases eval/cases_hard.jsonl --llm natlas

Costs: an L4 bills only while a container runs. It sleeps after 60 idle minutes (NATLAS_SLEEP_MIN) and the next
message wakes it (about 3.5-4 minutes on 2 Oct; the backup models answer meanwhile). Pilot and the 15-17 Oct check:
the web app pings it every 10 minutes from 7am to 8pm Nigeria time (src/natlas_watch.py), so it is warm in market
hours and asleep at night, and the team gets a WhatsApp if it stops answering.
Benchmark N-ATLaS's base model on the same GPU (a separate app, "tradevoice-natlas-base"; needs Meta's licence
accepted on Hugging Face for the HF_TOKEN's account; NVIDIA's API retired its Llama-3 8B models):
    NATLAS_MODEL_ID=meta-llama/Meta-Llama-3-8B-Instruct modal deploy deploy/modal_natlas.py
    then: NATLAS_URL=<that app's url>/v1 python eval/run_eval.py ... --llm natlas --shots all --raw
Stop it after: modal app stop tradevoice-natlas-base
"""
import os
import subprocess

import modal

MODEL_ID = os.getenv("NATLAS_MODEL_ID", "NCAIR1/N-ATLaS")
SERVED_NAME = "natlas"            # = NATLAS_MODEL in the app's .env
GPU = os.getenv("NATLAS_GPU", "L4")  # 24 GB: the 16-bit model (~16 GB) + KV cache for 8K context
WARM = int(os.getenv("NATLAS_WARM", "0"))
SLEEP_AFTER = int(os.getenv("NATLAS_SLEEP_MIN", "60"))  # idle minutes before the GPU sleeps
PORT = 8000

image = (
    modal.Image.debian_slim(python_version="3.12")
    # EXACT versions, tested together on 2 Oct 2026. Unpinned, a new transformers (5.x) broke vLLM at startup.
    # Change only on purpose, then run: python scripts/check_models.py --natlas
    .pip_install("vllm==0.10.2", "transformers==4.57.6", "tokenizers==0.22.2", "huggingface_hub==0.36.2",
                 "hf_transfer==0.1.9", "torch==2.8.0")
    # bake the model id into the image: the container doesn't see the env of the machine that ran `modal deploy`
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "NATLAS_MODEL_ID": MODEL_ID})
)
hf_cache = modal.Volume.from_name("tradevoice-hf-cache", create_if_missing=True)      # weights download once
vllm_cache = modal.Volume.from_name("tradevoice-vllm-cache", create_if_missing=True)  # compiled kernels

app = modal.App("tradevoice-natlas" if MODEL_ID == "NCAIR1/N-ATLaS" else "tradevoice-natlas-base")


@app.function(
    image=image,
    gpu=GPU,
    secrets=[modal.Secret.from_name("natlas")],
    volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
    min_containers=WARM,
    scaledown_window=SLEEP_AFTER * 60,
    timeout=24 * 60 * 60,
)
@modal.concurrent(max_inputs=16)
@modal.web_server(port=PORT, startup_timeout=15 * 60)
def serve():
    cmd = [
        "vllm", "serve", MODEL_ID,
        "--served-model-name", SERVED_NAME,
        "--host", "0.0.0.0", "--port", str(PORT),
        "--dtype", "bfloat16",
        "--max-model-len", "8192",            # the card: best within 8,092 tokens
        "--gpu-memory-utilization", "0.92",
        "--uvicorn-log-level", "warning",
    ]
    # only our app can call it. Passed as VLLM_API_KEY, not --api-key: vLLM prints its command-line args to the logs
    subprocess.Popen(cmd, env={**os.environ, "VLLM_API_KEY": os.environ["NATLAS_KEY"]})
