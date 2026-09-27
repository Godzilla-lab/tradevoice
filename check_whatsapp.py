"""Why isn't the WhatsApp bot answering? Run on Brev:  .venv/bin/python check_whatsapp.py
Checks every link in the chain and says which one is broken. Never prints tokens or secrets."""
import os
import re
import subprocess

import requests

import settings  # noqa: F401  (loads .env)

OK, BAD = "✅", "❌"
GRAPH = f"https://graph.facebook.com/{os.getenv('WHATSAPP_GRAPH_VERSION', 'v23.0')}"
token = os.getenv("WHATSAPP_TOKEN", "")
phone_id = os.getenv("WHATSAPP_PHONE_ID") or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
verify = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
problems = 0


def say(good, text, fix=""):
    global problems
    print(f"{OK if good else BAD} {text}")
    if not good:
        problems += 1
        if fix:
            print(f"   → {fix}")
    return good


print("1) .env")
say(bool(token) and "your" not in token.lower() and len(token) > 50, "WHATSAPP_TOKEN is set",
    "Meta → WhatsApp → API Setup → 'Generate access token', paste it after WHATSAPP_TOKEN= in .env")
say(phone_id.isdigit() and len(phone_id) >= 15, f"Phone number ID is set ({phone_id[:4]}…{phone_id[-4:]})"
    if phone_id else "Phone number ID is set", "WHATSAPP_PHONE_NUMBER_ID=<the 'Phone number ID' from API Setup>")
say(bool(verify), "WHATSAPP_VERIFY_TOKEN is set", "WHATSAPP_VERIFY_TOKEN=tradevoice-2026 (the same word you typed in Meta)")
if os.getenv("WHATSAPP_APP_SECRET"):
    print("⚠️  WHATSAPP_APP_SECRET is set: if it is not exactly the App secret (App settings → Basic), every message is "
          "refused. If unsure, leave it empty.")

print("\n2) Meta accepts the token and the phone number ID")
if token and phone_id:
    try:
        r = requests.get(f"{GRAPH}/{phone_id}", params={"fields": "display_phone_number,verified_name"},
                         headers={"Authorization": f"Bearer {token}"}, timeout=20)
        j = r.json()
        if r.ok:
            say(True, f"Meta knows this number: {j.get('display_phone_number')} ({j.get('verified_name')})")
        else:
            msg = (j.get("error") or {}).get("message", r.text[:200])
            fix = ("The token has expired (temporary tokens last 24 hours): generate a new one in API Setup."
                   if "expired" in msg.lower() or "session" in msg.lower() else
                   "Check the token and the Phone number ID (API Setup, under the test number).")
            say(False, f"Meta refused: {msg}", fix)
    except Exception as e:  # noqa: BLE001
        say(False, f"Could not reach Meta: {e}")
else:
    print("   (skipped: fix step 1 first)")

print("\n3) Our server answers Meta's check")
try:
    r = requests.get("http://localhost:8000/whatsapp/webhook", timeout=10,
                     params={"hub.mode": "subscribe", "hub.verify_token": verify, "hub.challenge": "12345"})
    say(r.text == "12345", "The app answers the webhook check",
        "Restart the app: tmux kill-session -t app; tmux new -d -s app '.venv/bin/python web.py'")
    st = requests.get("http://localhost:8000/api/status", timeout=10).json()
    say(st.get("whatsapp"), "The running app has WhatsApp switched on", "Restart the app (it reads .env when it starts)")
    seen = st.get("whatsapp_seen") or {}
except Exception as e:  # noqa: BLE001
    say(False, f"The app is not running on port 8000 ({type(e).__name__})",
        "tmux new -d -s app '.venv/bin/python web.py'")
    seen = {}

print("\n4) The public link")
link = None
for cmd in (["tmux", "capture-pane", "-pt", "link", "-S", "-3000"], ["cat", "/tmp/link.log"]):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        found = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", out)
        if found:
            link = found[-1]
            break
    except Exception:  # noqa: BLE001
        pass
link = os.getenv("NGROK_DOMAIN") and f"https://{os.getenv('NGROK_DOMAIN')}" or link
if link:
    try:
        r = requests.get(f"{link}/whatsapp/webhook", timeout=20,
                         params={"hub.mode": "subscribe", "hub.verify_token": verify, "hub.challenge": "12345"})
        say(r.text == "12345", f"The public link works: {link}", "Restart the link: tmux kill-session -t link; ./start_brev.sh")
    except Exception as e:  # noqa: BLE001
        say(False, f"The public link does not answer ({type(e).__name__})", "Restart the link session")
    print(f"\n   👉 In Meta → WhatsApp → Configuration, the Callback URL must be EXACTLY:\n      {link}/whatsapp/webhook"
          f"\n      Verify token: {'(the WHATSAPP_VERIFY_TOKEN value)' if verify else '?'}  → 'Verify and save'"
          "\n      Then under 'Webhook fields' → 'messages' → Subscribe (must be ON).")
else:
    say(False, "No public link found", "Start it: ./start_brev.sh (or the link tmux session)")

print("\n5) Messages from Meta since the app started")
if seen:
    print(f"   Deliveries from Meta: {seen.get('posts', 0)}  ·  messages: {seen.get('messages', 0)}  ·  "
          f"refused (bad secret): {seen.get('bad_signature', 0)}  ·  replies sent: {seen.get('sent', 0)}")
    if seen.get("last_error"):
        print(f"   Last error: {seen['last_error']}")
        if "131030" in seen["last_error"]:
            print("   → Your phone is not on the test number's list: API Setup → 'To' → add your number and confirm the code.")
        elif "401" in seen["last_error"] or "expired" in seen["last_error"].lower():
            print("   → Token expired or wrong: new token in API Setup → .env → restart the app.")
    if not seen.get("posts"):
        print("   → Meta has sent NOTHING to us. Send 'hi' again, then run this again. If still 0: the Callback URL is "
              "old/wrong or 'messages' is not subscribed (step 4).")
    elif seen.get("bad_signature"):
        print("   → Empty WHATSAPP_APP_SECRET in .env (or paste the right one), then restart the app.")

print("\n6) Voice notes on WhatsApp")
try:
    import whatsapp  # noqa: E402

    path = whatsapp.voice_file("Hello, I am your book.", "Pidgin")
    if path:
        size = os.path.getsize(path)
        os.remove(path)
        say(size > 1000, f"A voice note can be made ({size} bytes, ogg)")
    else:
        say(False, "No voice set up", "SPITCH_API_KEY in .env, and: .venv/bin/pip install spitch")
except Exception as e:  # noqa: BLE001
    say(False, f"Making a voice note failed: {type(e).__name__}: {e}"[:300],
        "If it mentions ffmpeg: sudo apt-get install -y ffmpeg. If Spitch: check SPITCH_API_KEY.")
if seen.get("last_voice_error"):
    print(f"   Last voice error while replying: {seen['last_voice_error']}")
    if "upload" in seen["last_voice_error"]:
        print("   → Meta refused the audio upload: check the token has whatsapp_business_messaging permission.")
if seen:
    print(f"   Voice notes sent since the app started: {seen.get('voice_sent', 0)}")
print("   (Voice replies are on by default; a trader can send 'voice off' / 'voice on'.)")

print("\n" + ("All good: send 'hi' to the test number." if not problems else f"{problems} thing(s) to fix above."))
