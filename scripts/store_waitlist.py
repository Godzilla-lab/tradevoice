"""Who asked to be told when TradeVoice is in the App Store / Google Play (the website's "Soon" buttons, via WhatsApp).

    python scripts/store_waitlist.py            everyone, newest first
    python scripts/store_waitlist.py ios        only App Store (or: android)
On the live server: sudo bash /opt/tradevoice/app/deploy/server/store_waitlist.sh [ios|android]
These people asked for ONE message: the day it is in their store. Nothing else is sent to them from this list.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import settings  # noqa: E402,F401  (loads .env)

import accounts  # noqa: E402
import whatsapp  # noqa: E402


def rows(store=None):
    whatsapp.store_wait("0")   # makes sure the list exists
    with sqlite3.connect(accounts.ACCOUNTS_DB) as c:
        q = "SELECT phone, store, at FROM store_wait WHERE phone != '0'" + (" AND store=?" if store else "") + " ORDER BY at DESC"
        return c.execute(q, (store,) if store else ()).fetchall()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    store = argv[0] if argv and argv[0] in ("ios", "android") else None
    r = rows(store)
    name = {"ios": "App Store", "android": "Google Play"}
    print(f"{len(r)} waiting" + (f" for {name[store]}" if store else "") + ":")
    for phone, s, at in r:
        print(f"  +{phone}  {name.get(s, s):<12} asked {at[:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
