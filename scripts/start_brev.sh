#!/usr/bin/env bash
# One command to bring TradeVoice up on Brev after the machine was stopped:
#   bash scripts/start_brev.sh          (stop everything: bash scripts/start_brev.sh stop)
# Starts: AI brain (vLLM :8001), photo reader (vLLM :8002), web app (:8000), public link.
# Public link: set NGROK_AUTHTOKEN + NGROK_DOMAIN in .env for a FIXED link that survives restarts;
# otherwise a new https://….trycloudflare.com link is printed each time.
set -euo pipefail
cd "$(dirname "$0")/.."   # run from the repo root (.env, books and the databases live there)
set -a; [ -f .env ] && source .env; set +a
VLLM=${VLLM:-$HOME/vllm-env/bin/vllm}
PY=${PY:-.venv/bin/python}
LLM=${LOCAL_LLM_MODEL:-Qwen/Qwen2.5-7B-Instruct-AWQ}
VLM=${LOCAL_VISION_MODEL:-Qwen/Qwen2.5-VL-7B-Instruct-AWQ}

if [ "${1:-}" = "stop" ]; then
  for s in llm vision app link; do tmux kill-session -t $s 2>/dev/null || true; done
  echo "Stopped. Now stop the machine in the Brev console so it stops costing credits."; exit 0
fi

wait_for() {  # url, name
  echo -n "⏳ waiting for $2 "
  for _ in $(seq 1 180); do curl -sf "$1" >/dev/null && { echo " ✅"; return 0; }; echo -n "."; sleep 5; done
  echo " ❌ $2 did not start: tmux attach -t ${3:-$2}"; exit 1
}

tmux has-session -t llm 2>/dev/null || tmux new -d -s llm \
  "$VLLM serve $LLM --port 8001 --gpu-memory-utilization ${LLM_GPU:-0.35} --max-model-len 4096 2>&1 | tee /tmp/llm.log"
wait_for http://localhost:8001/v1/models "AI brain" llm

tmux has-session -t vision 2>/dev/null || tmux new -d -s vision \
  "$VLLM serve $VLM --port 8002 --gpu-memory-utilization ${VLM_GPU:-0.45} --max-model-len ${VLM_LEN:-8192} \
   --limit-mm-per-prompt '{\"image\":1}' 2>&1 | tee /tmp/vision.log"
wait_for http://localhost:8002/v1/models "photo reader" vision

tmux has-session -t app 2>/dev/null || tmux new -d -s app "$PY src/web.py 2>&1 | tee /tmp/app.log"
wait_for http://localhost:8000/api/status "web app" app

if [ -n "${NGROK_AUTHTOKEN:-}" ] && [ -n "${NGROK_DOMAIN:-}" ]; then
  command -v ngrok >/dev/null || { curl -sL https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz \
    | sudo tar xz -C /usr/local/bin; }
  ngrok config add-authtoken "$NGROK_AUTHTOKEN" >/dev/null
  tmux has-session -t link 2>/dev/null || tmux new -d -s link "ngrok http --url=$NGROK_DOMAIN 8000"
  LINK="https://$NGROK_DOMAIN"
else
  [ -x ./cloudflared ] || { curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o cloudflared && chmod +x cloudflared; }
  tmux has-session -t link 2>/dev/null || tmux new -d -s link "./cloudflared tunnel --url http://localhost:8000 2>&1 | tee /tmp/link.log"
  for _ in $(seq 1 30); do LINK=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/link.log 2>/dev/null | head -1) && [ -n "$LINK" ] && break; sleep 2; done
fi

$PY scripts/check_models.py || true
echo
echo "🟢 TradeVoice is up:  ${LINK:-(link not ready: tmux attach -t link)}"
echo "   Screens: tmux attach -t llm | vision | app | link   (leave with Ctrl+B then D)"
echo "   When done: bash scripts/start_brev.sh stop, then STOP the machine in the Brev console."
