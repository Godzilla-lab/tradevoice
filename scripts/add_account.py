"""Team-created accounts, for testers while WhatsApp sign-up codes can't be sent yet (Meta verification pending).

    python scripts/add_account.py 08031234567 "Ada" "Ada Stores"            new account, prints a temporary password
    python scripts/add_account.py 08031234567 --reset                      new temporary password, logs out every phone
On the live server: sudo bash /opt/tradevoice/app/deploy/server/add_account.sh … (same arguments).

Only someone with access to the server can do this, for people the team knows: give the password to the tester in
person (or by your own WhatsApp), never in a group. They log in with phone + password, then Me > Password to change it.
"""
import argparse
import hashlib
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import settings  # noqa: E402,F401  (loads .env)

import accounts  # noqa: E402
import v2  # noqa: E402

SYLLABLES = [c + v for c in "bdfgkmnprstwy" for v in "aeiou"]


def temp_password():
    """Easy to type on a phone, hard to guess: e.g. Kobamu-4827-Tesi."""
    word = lambda n: "".join(secrets.choice(SYLLABLES) for _ in range(n))  # noqa: E731
    return f"{word(3).title()}-{secrets.randbelow(9000) + 1000}-{word(2).title()}"


def page_hash(password):
    """What the app's login page sends instead of the password (web/app.html: hp("pw:" + password))."""
    return hashlib.sha256(("tv:pw:" + password).encode()).hexdigest()


def create(phone, name, biz, kind="", market="", lang="English"):
    phone = v2._norm(phone)
    if not phone:
        raise SystemExit("That isn't a Nigerian number (like 08031234567 or 2348031234567).")
    if v2._has_account(phone):
        raise SystemExit("This number already has an account. To give it a new password: --reset")
    if len(name.strip()) < 2 or len(biz.strip()) < 2:
        raise SystemExit("Give the person's name and the business name.")
    password = temp_password()
    with v2._lock, v2._db() as c:
        c.execute("INSERT INTO users (phone, created_at) VALUES (?,?) ON CONFLICT(phone) DO NOTHING",
                  (phone, v2._now().isoformat()))
        c.execute("UPDATE users SET pw_hash=?, name=?, shop=?, biz_type=?, market=?, lang=?, delete_at=NULL "
                  "WHERE phone=?", (v2._pw_hash(page_hash(password)), name.strip()[:60], biz.strip()[:60],
                                    kind if kind in v2.TYPES else "", market.strip()[:80], lang, phone))
    v2._event("signup", phone)
    return phone, password


def reset(phone):
    phone = v2._norm(phone)
    if not phone or not v2._has_account(phone):
        raise SystemExit("No account with that number.")
    password = temp_password()
    with v2._lock, v2._db() as c:
        c.execute("UPDATE users SET pw_hash=? WHERE phone=?", (v2._pw_hash(page_hash(password)), phone))
        c.execute("DELETE FROM sessions WHERE phone=?", (phone,))   # every phone logged in before is logged out
    return phone, password


def main(argv=None):
    a = argparse.ArgumentParser(description="Create a TradeVoice account for a tester (no WhatsApp code needed).")
    a.add_argument("phone")
    a.add_argument("name", nargs="?", default="")
    a.add_argument("business", nargs="?", default="")
    a.add_argument("--type", default="", help="one of: " + ", ".join(v2.TYPES))
    a.add_argument("--market", default="")
    a.add_argument("--lang", default="English", choices=["English", "Yoruba", "Hausa", "Igbo"])
    a.add_argument("--reset", action="store_true", help="new temporary password for an existing account")
    args = a.parse_args(argv)
    if args.reset:
        phone, password = reset(args.phone)
        what = "New temporary password (every phone that was logged in is now logged out)"
    else:
        phone, password = create(args.phone, args.name, args.business, args.type, args.market, args.lang)
        what = "Account created ✅  Temporary password"
    base = (os.getenv("PUBLIC_URL") or "").rstrip("/")
    print(f"\n{what}:\n\n    {password}\n")
    print(f"For {accounts.masked(phone)}: open {base + '/app' if base else 'the app'} → Log in → phone number + this password.")
    print("Then Me → Password → choose their own. Give the password in person or by your own WhatsApp, never in a group.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
