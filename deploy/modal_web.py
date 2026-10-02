"""The TradeVoice web app + WhatsApp webhook + /team on Modal: one always-on server with a permanent link
(https://<workspace>--tradevoice-web-serve.modal.run), no domain needed.

    modal deploy deploy/modal_web.py

Data: every trader's book (SQLite) and accounts.db live on the Modal Volume "tradevoice-data", mounted at /data.
Exactly ONE container runs (min = max = 1) so only one process ever writes the books. Changes are committed to the
volume after every request that writes and every 30 seconds, and once more on shutdown.
Settings/keys: the Modal secret "tradevoice-app" (NATLAS_URL, NATLAS_KEY, NATLAS_ASR_URL, NVIDIA_API_KEY,
ADMIN_TOKEN, PUBLIC_URL; later WHATSAPP_*, INTRON_API_KEY, PAYSTACK_*). Edit it in the Modal dashboard
(Secrets -> tradevoice-app), then run `modal app stop tradevoice-web && modal deploy deploy/modal_web.py`.
Never in the repo or the chat.
"""
import os

import modal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    # versions the 306 checks passed with on 2 Oct (pinned so a new release can't break the live app)
    .pip_install("fastapi==0.141.1", "uvicorn==0.53.0", "starlette==1.7.0", "pydantic==2.13.5",
                 "python-multipart==0.0.32", "requests==2.33.1", "openai==3.19.2", "pillow==12.3.0", "httpx==0.28.1")
    .env({"PYTHONPATH": "/app/src", "DB_PATH": "/data/tradevoice.db", "BOOKS_DIR": "/data/books",
          "ACCOUNTS_DB": "/data/accounts.db", "TRADEVOICE_ADMIN": "0", "TV_NO_DOTENV": "1"})
    .add_local_dir(os.path.join(ROOT, "src"), "/app/src", ignore=["__pycache__", "*.pyc", "app.py", "note.py"])
    .add_local_dir(os.path.join(ROOT, "web"), "/app/web")
)
data = modal.Volume.from_name("tradevoice-data", create_if_missing=True)
app = modal.App("tradevoice-web")


@app.function(image=image, volumes={"/data": data}, secrets=[modal.Secret.from_name("tradevoice-app")],
              min_containers=1, max_containers=1, timeout=24 * 60 * 60, cpu=0.25, memory=512)  # ~$10/month always on
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def serve():
    import atexit
    import threading
    import time

    os.makedirs("/data/books", exist_ok=True)
    os.chdir("/app")
    import web

    lock = threading.Lock()

    def commit():
        with lock:
            try:
                data.commit()
            except Exception as e:  # noqa: BLE001
                print(f"volume commit failed: {type(e).__name__}: {e}")

    def every_30s():
        while True:
            time.sleep(30)
            commit()
    threading.Thread(target=every_30s, daemon=True).start()
    atexit.register(commit)

    @web.app.middleware("http")
    async def save_after_writes(request, call_next):
        response = await call_next(request)
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            threading.Thread(target=commit, daemon=True).start()   # don't make the trader wait for the disk
        return response

    return web.app
