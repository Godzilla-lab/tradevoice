"""Erase an account now, when its owner asks for it sooner than the 90 days the delete screen gives (their right
under the Nigeria Data Protection Act). Only for a request from the owner of that number.

    python scripts/erase_account.py 08031234567          shows what would be erased
    python scripts/erase_account.py 08031234567 --yes    erases it for good
On the live server: sudo bash /opt/tradevoice/app/deploy/server/erase_account.sh … (same arguments).

Backup copies that still hold it are pruned within 30 days (scripts/backup.py).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import settings  # noqa: E402,F401  (loads .env)

import accounts  # noqa: E402
import ledger  # noqa: E402
import v2  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Erase an account and its book now.")
    ap.add_argument("phone")
    ap.add_argument("--yes", action="store_true", help="really erase it")
    a = ap.parse_args(argv)
    phone = v2._norm(a.phone)
    if not phone:
        raise SystemExit("That isn't a Nigerian number (like 08031234567 or 2348031234567).")
    book = ledger.book_file(phone)
    has_book, has_account = os.path.exists(book), v2._has_account(phone)
    if not has_book and not has_account:
        raise SystemExit("Nothing is stored for that number.")
    when = v2.closing(phone)
    print(f"{phone}: account {'yes' if has_account else 'no'}, book {'yes' if has_book else 'no'}"
          + (f", deleted by its owner, due to be erased on {when}" if when else ", still open"))
    if not a.yes:
        print("Nothing erased. Add --yes to erase it for good.")
        return 1
    accounts.delete_account(phone)
    print("Erased. Backup copies that still hold it are gone within 30 days.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
