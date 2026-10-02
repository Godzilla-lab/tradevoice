"""N-ATLaS (NCAIR1/N-ATLaS, Llama-3 8B) on a Modal GPU, as an OpenAI-compatible API (vLLM).

One-time set-up (on your own machine, never paste keys into chat or commit them):
    pip install modal && modal setup
    modal secret create natlas NATLAS_KEY=<long random string> HF_TOKEN=<your Hugging Face read token>

Deploy (prints the URL; add /v1 and put it in .env as NATLAS_URL, with the same NATLAS_KEY):
    modal deploy deploy/modal_natlas.py
    NATLAS_WARM=1 modal deploy deploy/modal_natlas.py     # keep 1 GPU always on: pilot + NAIC check 15-17 Oct

Check it:   python scripts/check_models.py --natlas
Benchmark:  python eval/run_eval.py --cases eval/cases_hard.jsonl --llm natlas

Costs: an L4 bills only while a container runs. With NATLAS_WARM=0 it sleeps after SLEEP_AFTER minutes idle and
the next message wakes it (about 1-3 minutes; the app answers with the backup models meanwhile).
Benchmark the base model on the same GPU:  NATLAS_MODEL_ID=meta-llama/Meta-Llama-3-8B-Instruct modal deploy ...
(needs Meta's licence accepted on Hugging Face; or use the NVIDIA API's meta/llama3-8b-instruct instead).
"""
import os
import subprocess

import modal

MODEL_ID = os.getenv("NATLAS_MODEL_ID", "NCAIR1/N-ATLaS")
SERVED_NAME = "natlas"            # = NATLAS_MODEL in the app's .env
GPU = os.getenv("NATLAS_GPU", "L4")  # 24 GB: the 16-bit model (~16 GB) + KV cache for 8K context
WARM = int(os.getenv("NATLAS_WARM", "0"))
SLEEP_AFTER = int(os.getenv("NATLAS_SLEEP_MIN", "15"))
PORT = 8000

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.10.2", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
hf_cache = modal.Volume.from_name("tradevoice-hf-cache", create_if_missing=True)      # weights download once
vllm_cache = modal.Volume.from_name("tradevoice-vllm-cache", create_if_missing=True)  # compiled kernels

app = modal.App("tradevoice-natlas")


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
        "--api-key", os.environ["NATLAS_KEY"],  # only our app can call it
        "--uvicorn-log-level", "warning",
    ]
    subprocess.Popen(cmd)
