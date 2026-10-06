"""The WhatsApp message templates TradeVoice needs, for messages a trader didn't just ask for. Outside Meta's
24-hour window only an approved template is delivered. Without these, the app still works: codes go to traders
who wrote to the bot in the last 24 hours, everyone else taps "Send it on WhatsApp", and daily summaries wait in
the app.

    python scripts/whatsapp_templates.py --print     the exact templates, to create by hand in WhatsApp Manager
    python scripts/whatsapp_templates.py --create    create them through Meta's API (needs WHATSAPP_WABA_ID and a
                                                     token with whatsapp_business_management)
    python scripts/whatsapp_templates.py --status    which ones Meta approved
On the live server: sudo bash /opt/tradevoice/app/deploy/server/whatsapp_templates.sh --status (same options)

When a template shows APPROVED, put its name in .env with keys.sh (WHATSAPP_TPL_CODE, WHATSAPP_TPL_SUMMARY,
WHATSAPP_TPL_PAID, WHATSAPP_TPL_ALERT). The app uses it from the next restart.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import settings  # noqa: E402,F401  (loads .env)

GRAPH = f"https://graph.facebook.com/{os.getenv('WHATSAPP_GRAPH_VERSION', 'v23.0')}"

# setting in .env -> the template (Meta's format). Text is plain, calm, no emojis; {{1}} is filled by the app.
TEMPLATES = {
    "WHATSAPP_TPL_CODE": {
        "name": "tradevoice_code", "language": "en", "category": "AUTHENTICATION",
        "components": [{"type": "BODY", "add_security_recommendation": True},
                       {"type": "FOOTER", "code_expiration_minutes": 10},
                       {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE", "text": "Copy code"}]}],
    },
    "WHATSAPP_TPL_SUMMARY": {
        "name": "tradevoice_daily", "language": "en", "category": "UTILITY",
        "components": [{"type": "BODY",
                        "text": "Good morning from TradeVoice. Your shop today: {{1}} The reminders are ready in the "
                                "app for you to send.",
                        "example": {"body_text": [["2 customer(s) promised to pay today. Your reminders are ready. "
                                                   "Open: https://tradevoice.duckdns.org/app"]]}}],
    },
    "WHATSAPP_TPL_PAID": {
        "name": "tradevoice_paid", "language": "en", "category": "UTILITY",
        "components": [{"type": "BODY",
                        "text": "Payment received through your TradeVoice link. {{1}} It is already in your book.",
                        "example": {"body_text": [["Mama Ngozi paid 5,000 naira. She still owes you 10,000 naira."]]}}],
    },
    "WHATSAPP_TPL_ALERT": {
        "name": "tradevoice_alert", "language": "en", "category": "UTILITY",
        "components": [{"type": "BODY",
                        "text": "TradeVoice system alert for the team: {{1}} Check the team dashboard for details.",
                        "example": {"body_text": [["N-ATLaS is not answering. The backup models are answering."]]}}],
    },
}


def _head():
    return {"Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}"}


def show():
    for env, t in TEMPLATES.items():
        print(f"\n{t['name']}  ({t['category']}, language: English)  ->  then: keys.sh {env}  (value: {t['name']})")
        for c in t["components"]:
            if c["type"] == "BODY":
                print("  Body: " + (c.get("text") or "Meta's standard code text, with 'Add security recommendation' ticked"))
                if c.get("example"):
                    print("  Example for {{1}}: " + c["example"]["body_text"][0][0])
            elif c["type"] == "FOOTER":
                print(f"  Code expires in: {c['code_expiration_minutes']} minutes")
            elif c["type"] == "BUTTONS":
                print("  Button: Copy code")


def create():
    import requests
    waba = os.getenv("WHATSAPP_WABA_ID")
    if not (waba and os.getenv("WHATSAPP_TOKEN")):
        sys.exit("Needs WHATSAPP_WABA_ID (WhatsApp Manager > Account tools > Phone numbers, the account ID) and "
                 "WHATSAPP_TOKEN. Set them with keys.sh, or use --print and create them by hand.")
    for env, t in TEMPLATES.items():
        r = requests.post(f"{GRAPH}/{waba}/message_templates", headers=_head(), json=t, timeout=30)
        try:
            d = r.json()
        except ValueError:
            d = {}
        if r.ok:
            print(f"{t['name']}: sent to Meta for review ({d.get('status', 'PENDING')}). Then: keys.sh {env}")
        else:
            msg = (d.get("error") or {}).get("error_user_msg") or (d.get("error") or {}).get("message") or r.text[:200]
            print(f"{t['name']}: not created: {msg}")


def status():
    import requests
    waba = os.getenv("WHATSAPP_WABA_ID")
    if not (waba and os.getenv("WHATSAPP_TOKEN")):
        sys.exit("Needs WHATSAPP_WABA_ID and WHATSAPP_TOKEN (keys.sh).")
    r = requests.get(f"{GRAPH}/{waba}/message_templates", headers=_head(), timeout=30,
                     params={"fields": "name,status,category,language", "limit": 200})
    if not r.ok:
        sys.exit(f"Meta said HTTP {r.status_code}: {r.text[:200]}")
    have = {x["name"]: x for x in r.json().get("data", [])}
    for env, t in TEMPLATES.items():
        x = have.get(t["name"])
        in_env = os.getenv(env) == t["name"]
        print(f"{t['name']:<18} {(x or {}).get('status', 'NOT CREATED'):<12} "
              f"{'in use' if in_env and x and x.get('status') == 'APPROVED' else ('set in .env' if in_env else f'not in .env ({env})')}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--print", action="store_true")
    g.add_argument("--create", action="store_true")
    g.add_argument("--status", action="store_true")
    g.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.print:
        show()
    elif a.create:
        create()
    elif a.status:
        status()
    else:
        print(json.dumps(TEMPLATES, indent=2))


if __name__ == "__main__":
    main()
