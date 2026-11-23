"""
CS-4347 Library Project - Milestone 2: Fines
PostgreSQL + psycopg (pip install "psycopg[binary]")

Rules (from the spec):
  - $0.25 per day late
  - returned late  -> fine = (date_in  - due_date) * 0.25   (final)
  - still out late -> fine = (today    - due_date) * 0.25   (estimate, grows daily)
  - existing unpaid fine -> update amount only if it changed
  - existing paid fine   -> never touch it
"""
from datetime import date
from decimal import Decimal

DAILY_RATE = Decimal("0.25")   # Decimal, not float: money must be exact


def refresh_fines(conn, today=None):
    """Create or update a FINES row for every late loan.

    Meant to run once a day (like a nightly batch job). Safe to run repeatedly:
    a second run on the same day changes nothing.
    `today` can be passed in for testing; it defaults to the real date.
    Returns how many fine rows were created or updated.
    """
    today = today or date.today()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO fines (loan_id, fine_amt, paid)
            SELECT loan_id,
                   (COALESCE(date_in, %(today)s) - due_date) * %(rate)s,
                   FALSE
            FROM   book_loans
            WHERE  COALESCE(date_in, %(today)s) > due_date          -- only late loans
            ON CONFLICT (loan_id) DO UPDATE
               SET fine_amt = EXCLUDED.fine_amt
             WHERE fines.paid = FALSE                                -- paid fines are frozen
               AND fines.fine_amt <> EXCLUDED.fine_amt               -- only if amount changed
            """,
            {"today": today, "rate": DAILY_RATE},
        )
        changed = cur.rowcount
    conn.commit()
    return changed


class FineError(Exception):
    """Raised when a payment is not allowed; the message is shown to the librarian."""


def pay_fines(conn, card_id):
    """Pay ALL unpaid fines for one borrower (no partial payments).

    Refused if the borrower has nothing to pay, or still has a late book out
    (its fine is still growing, so it can't be settled yet).
    Returns the total amount paid.
    """
    with conn.cursor() as cur:
        # Check 1: how much does this borrower owe right now?
        cur.execute(
            """
            SELECT COALESCE(SUM(f.fine_amt), 0),
                   COUNT(*) FILTER (WHERE bl.date_in IS NULL)
            FROM   fines f
            JOIN   book_loans bl ON bl.loan_id = f.loan_id
            WHERE  bl.card_id = %s AND f.paid = FALSE
            """,
            (card_id,),
        )
        total, books_still_out = cur.fetchone()

        if total == 0:
            cur.execute("SELECT 1 FROM borrower WHERE card_id = %s", (card_id,))
            conn.rollback()
            if cur.fetchone() is None:
                raise FineError(f"No borrower found with card ID {card_id}.")
            raise FineError(f"Borrower {card_id} has no unpaid fines.")

        # Check 2: no paying while a late book is still out.
        if books_still_out > 0:
            conn.rollback()
            raise FineError(
                f"Borrower {card_id} still has {books_still_out} late book(s) checked out. "
                "Those books must be returned before fines can be paid."
            )

        # Pay: mark every unpaid fine for this borrower as paid, all at once.
        cur.execute(
            """
            UPDATE fines SET paid = TRUE
            WHERE  paid = FALSE
              AND  loan_id IN (SELECT loan_id FROM book_loans WHERE card_id = %s)
            """,
            (card_id,),
        )
    conn.commit()   # checks + update happen in ONE transaction
    return total


def get_fines(conn, include_paid=False, card_id=None):
    """Fines grouped by borrower (one row per card_id, amounts SUMmed).

    include_paid=False (default): only borrowers who currently owe money.
    include_paid=True:            also show paid history.
    card_id: optional, limit to one borrower.

    Returns a list of dicts:
      card_id, bname, unpaid_total, paid_total, late_books_out
    late_books_out > 0 means the borrower can't pay yet (see pay_fines).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.card_id,
                   b.bname,
                   COALESCE(SUM(f.fine_amt) FILTER (WHERE NOT f.paid), 0)                       AS unpaid_total,
                   COALESCE(SUM(f.fine_amt) FILTER (WHERE f.paid), 0)                           AS paid_total,
                   COUNT(*) FILTER (WHERE NOT f.paid AND bl.date_in IS NULL)                    AS late_books_out
            FROM   fines f
            JOIN   book_loans bl ON bl.loan_id = f.loan_id
            JOIN   borrower   b  ON b.card_id  = bl.card_id
            WHERE  (%(card)s::text IS NULL OR b.card_id = %(card)s::text)
            GROUP  BY b.card_id, b.bname
            HAVING %(all)s OR SUM(f.fine_amt) FILTER (WHERE NOT f.paid) > 0
            ORDER  BY b.card_id
            """,
            {"all": include_paid, "card": card_id},
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.commit()
    return rows


def money(amount):
    return f"${amount:,.2f}"


def format_fines(rows, include_paid=False):
    """Turn get_fines() output into a printable table (for the CLI now, GUI later)."""
    if not rows:
        return "No fines to show."
    header = f"{'CARD':<10} {'BORROWER':<25} {'OWED':>9}"
    if include_paid:
        header += f" {'PAID':>9}"
    header += "  NOTE"
    lines = [header, "-" * len(header)]
    for r in rows:
        line = f"{r['card_id']:<10} {r['bname'][:25]:<25} {money(r['unpaid_total']):>9}"
        if include_paid:
            line += f" {money(r['paid_total']):>9}"
        if r["late_books_out"]:
            line += f"  {r['late_books_out']} late book(s) still out - can't pay yet"
        lines.append(line)
    return "\n".join(lines)


def has_unpaid_fines(conn, card_id, today=None):
    """For the CHECKOUT feature: True if this borrower may NOT check out because of fines.

    Counts an unpaid fine in FINES, and also an overdue book still out even if
    the nightly refresh hasn't created its fine row yet.
    Usage in checkout():  if has_unpaid_fines(conn, card_id): refuse with a message.
    """
    today = today or date.today()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (SELECT 1 FROM fines f JOIN book_loans bl ON bl.loan_id = f.loan_id
                           WHERE bl.card_id = %(card)s AND f.paid = FALSE)
                OR EXISTS (SELECT 1 FROM book_loans
                           WHERE card_id = %(card)s AND date_in IS NULL AND due_date < %(today)s)
            """,
            {"card": card_id, "today": today},
        )
        blocked = cur.fetchone()[0]
    conn.commit()
    return blocked
