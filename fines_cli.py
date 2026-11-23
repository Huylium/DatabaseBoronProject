"""
Command-line runner for the Fines functions (Milestone 2).

Examples:
    python fines_cli.py refresh                  # recompute fines as of today
    python fines_cli.py refresh --today 2026-12-05
    python fines_cli.py show                     # who owes money (paid fines hidden)
    python fines_cli.py show --all               # include paid history
    python fines_cli.py show --card ID000002
    python fines_cli.py pay ID000001

Connection: set LIBRARY_DB to a PostgreSQL connection string, e.g.
    export LIBRARY_DB="dbname=library user=postgres password=secret host=localhost"
(defaults to "dbname=library", which uses your local PostgreSQL login).
"""
import argparse
import os
import sys
from datetime import date

import psycopg

from fines import FineError, format_fines, get_fines, pay_fines, refresh_fines


def connect():
    return psycopg.connect(os.environ.get("LIBRARY_DB", "dbname=library"))


def main(argv=None):
    p = argparse.ArgumentParser(description="Library fines")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("refresh", help="create/update fines for all late loans")
    r.add_argument("--today", type=date.fromisoformat, help="pretend today is YYYY-MM-DD (testing)")

    s = sub.add_parser("show", help="show fines grouped by borrower")
    s.add_argument("--all", action="store_true", help="include paid fines")
    s.add_argument("--card", help="only this borrower")

    y = sub.add_parser("pay", help="pay all of a borrower's fines")
    y.add_argument("card_id")

    args = p.parse_args(argv)
    with connect() as conn:
        if args.cmd == "refresh":
            n = refresh_fines(conn, args.today)
            print(f"Fines refreshed: {n} row(s) created or updated.")
        elif args.cmd == "show":
            print(format_fines(get_fines(conn, args.all, args.card), args.all))
        elif args.cmd == "pay":
            try:
                total = pay_fines(conn, args.card_id)
                print(f"Payment of ${total:.2f} received from {args.card_id}. All fines cleared.")
            except FineError as e:
                print(f"Payment refused: {e}")
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
