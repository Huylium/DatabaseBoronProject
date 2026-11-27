# run checkout, loan searches, and returns from the terminal.
# Yaseen Hafid yxh190036
import argparse
import os
import sys

import psycopg

from loans import LoanError, checkin, checkout, find_active_loans


def main(argv=None):
    # Read the command and its inputs here; loans.py handles the library rules.
    parser = argparse.ArgumentParser(description="Library book loans")
    commands = parser.add_subparsers(dest="command", required=True)
    out = commands.add_parser("checkout", help="check out a book for 14 days")
    out.add_argument("isbn")
    out.add_argument("card_id")
    find = commands.add_parser("find", help="find active loans (all supplied filters must match)")
    find.add_argument("--isbn", help="ISBN or part of an ISBN")
    find.add_argument("--card", help="exact borrower card ID")
    find.add_argument("--name", help="borrower name substring, ignoring case")
    back = commands.add_parser("checkin", help="return 1-3 loans by their loan IDs")
    back.add_argument("loan_ids", nargs="+", type=int)
    args = parser.parse_args(argv)

    try:
        # use the same database setting as the search and fines commands.

        with psycopg.connect(os.environ.get("LIBRARY_DB", "dbname=library")) as conn:
            if args.command == "checkout":
                row = checkout(conn, args.isbn, args.card_id)
                print(f"Checked out {row['isbn']} to {row['card_id']}. "
                      f"Loan ID: {row['loan_id']}. Due: {row['due_date']}.")
            elif args.command == "find":
                rows = find_active_loans(conn, args.isbn, args.card, args.name)
                if not rows:
                    print("No active loans found.")
                for row in rows:
                    print(f"Loan {row['loan_id']} | {row['isbn']} | {row['title']} | "
                          f"{row['card_id']} | {row['bname']} | "
                          f"Out: {row['date_out']} | Due: {row['due_date']}")
            else:
                for row in checkin(conn, args.loan_ids):
                    print(f"Checked in loan {row['loan_id']} ({row['isbn']}) on {row['date_in']}.")
                print("Late-return fines updated, if applicable.")
    except LoanError as exc:
        # show why the request was refused so the librarian can correct it.

        print(f"Loan operation refused: {exc}", file=sys.stderr)
        return 1
    except psycopg.Error:
        # keep passwords and connection details out of the error output.
        print("Database operation failed. Check PostgreSQL, LIBRARY_DB, and the schema. "
              "The loan operation was rolled back.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
