#Yaseen Hafid yxh190036
#Using our existing PostgreSQL schema, each operation uses a transaction; when called inside an existing transaction, the caller controls the final commit.

from datetime import date, timedelta

from psycopg.rows import dict_row

from fines import DAILY_RATE


class LoanError(Exception):
    # A checkout or return was refused
    pass


def _required_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise LoanError(f"{label} is required and must be text.")
    return value.strip()


def _today(value):
    if value is None:
        return date.today()
    if type(value) is not date:
        raise LoanError("The operation date must be a datetime.date value.")
    return value


def _substring(value):
    # Treat %, _ and backslash as literal search characters, not wildcards.
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def checkout(conn, isbn, card_id, today=None):
    # check out one book and return its new loan as a dictionary. Refuses missing records, a fourth active loan, an unavailable book, or unpaid fines. 

    isbn = _required_text(isbn, "ISBN")
    card_id = _required_text(card_id, "Borrower card ID")
    day = _today(today)

    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        # All loan writes lock borrower rows first, then book rows and serializing requests for the same borrower/book protects both checkout limits.

        cur.execute("SELECT card_id FROM borrower WHERE card_id = %s FOR UPDATE", (card_id,))
        if cur.fetchone() is None:
            raise LoanError(f"No borrower found with card ID {card_id}.")
        cur.execute("SELECT isbn FROM book WHERE isbn = %s FOR UPDATE", (isbn,))
        if cur.fetchone() is None:
            raise LoanError(f"No book found with ISBN {isbn}.")

        cur.execute(
            "SELECT 1 FROM book_loans WHERE isbn = %s AND date_in IS NULL",
            (isbn,),
        )
        if cur.fetchone() is not None:
            raise LoanError(f"Book {isbn} is already checked out and is not available.")

        cur.execute(
            "SELECT COUNT(*) AS active FROM book_loans WHERE card_id = %s AND date_in IS NULL",
            (card_id,),
        )
        if cur.fetchone()["active"] >= 3:
            raise LoanError(f"Borrower {card_id} already has 3 active loans (the maximum).")

      
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM book_loans bl
                LEFT JOIN fines f ON f.loan_id = bl.loan_id
                WHERE bl.card_id = %(card)s
                  AND (f.paid = FALSE
                       OR (COALESCE(bl.date_in, %(today)s) > bl.due_date
                           AND f.loan_id IS NULL))
            ) AS blocked
            """,
            {"card": card_id, "today": day},
        )
        if cur.fetchone()["blocked"]:
            raise LoanError(
                f"Borrower {card_id} has unpaid fines. Return overdue books and settle fines first."
            )

        cur.execute(
            """
            INSERT INTO book_loans (isbn, card_id, date_out, due_date, date_in)
            VALUES (%s, %s, %s, %s, NULL)
            RETURNING loan_id, isbn, card_id, date_out, due_date, date_in
            """,
            (isbn, card_id, day, day + timedelta(days=14)),
        )
        loan = cur.fetchone()
    return loan


def find_active_loans(conn, isbn=None, card_id=None, borrower_name=None):
    # Return outstanding loans, optionally filtered by ISBN, card, and/or name.

    isbn = None if isbn is None else _substring(_required_text(isbn, "ISBN"))
    card_id = None if card_id is None else _required_text(card_id, "Borrower card ID")
    name = None if borrower_name is None else _substring(_required_text(borrower_name, "Borrower name"))
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT bl.loan_id, bl.isbn, b.title, bl.card_id, br.bname,
                   bl.date_out, bl.due_date, bl.date_in
            FROM book_loans bl
            JOIN book b ON b.isbn = bl.isbn
            JOIN borrower br ON br.card_id = bl.card_id
            WHERE bl.date_in IS NULL
              AND (%(isbn)s::text IS NULL OR bl.isbn ILIKE %(isbn)s)
              AND (%(card)s::text IS NULL OR bl.card_id = %(card)s)
              AND (%(name)s::text IS NULL OR br.bname ILIKE %(name)s)
            ORDER BY bl.card_id, bl.loan_id
            """,
            {"isbn": isbn, "card": card_id, "name": name},
        )
        return cur.fetchall()


def checkin(conn, loan_ids, today=None):
    # return 1-3 selected loans and return the updated loan dictionaries. the entire selection will succeed or none of it will. 
    try:
        ids = list(loan_ids)
    except TypeError:
        raise LoanError("Provide a list of 1-3 loan IDs.") from None
    if not 1 <= len(ids) <= 3:
        raise LoanError("Select between 1 and 3 loans to check in.")
    if any(type(value) is not int or not 0 < value <= 2147483647 for value in ids):
        raise LoanError("Each loan ID must be a positive integer within the database ID range.")
    if len(set(ids)) != len(ids):
        raise LoanError("Select each loan ID only once.")
    day = _today(today)

    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        # Read the owners first so every writer follows the same lock order.

        cur.execute("SELECT loan_id, card_id, isbn FROM book_loans WHERE loan_id = ANY(%s)", (ids,))
        selected = cur.fetchall()
        missing = sorted(set(ids) - {row["loan_id"] for row in selected})
        if missing:
            raise LoanError("Loan ID(s) not found: " + ", ".join(map(str, missing)) + ".")
        cards = sorted({row["card_id"] for row in selected})
        books = sorted({row["isbn"] for row in selected})
        cur.execute(
            "SELECT card_id FROM borrower WHERE card_id = ANY(%s) ORDER BY card_id FOR UPDATE",
            (cards,),
        )
        cur.fetchall()
        cur.execute("SELECT isbn FROM book WHERE isbn = ANY(%s) ORDER BY isbn FOR UPDATE", (books,))
        cur.fetchall()
        cur.execute(
            "SELECT * FROM book_loans WHERE loan_id = ANY(%s) ORDER BY loan_id FOR UPDATE",
            (ids,),
        )
        selected = cur.fetchall()
        if len(selected) != len(ids):
            raise LoanError("A selected loan no longer exists. Search again before checking in.")
        for loan in selected:
            if loan["date_in"] is not None:
                raise LoanError(f"Loan {loan['loan_id']} has already been checked in.")
            if day < loan["date_out"]:
                raise LoanError(f"Return date cannot be before checkout for loan {loan['loan_id']}.")

        cur.execute(
            """
            UPDATE book_loans SET date_in = %s WHERE loan_id = ANY(%s)
            RETURNING loan_id, isbn, card_id, date_out, due_date, date_in
            """,
            (day, ids),
        )
        returned = cur.fetchall()
        # Same fixed-decimal calculation/upsert rule as fines.refresh_fines(),
        
        cur.execute(
            """
            INSERT INTO fines (loan_id, fine_amt, paid)
            SELECT loan_id, (date_in - due_date) * %s, FALSE
            FROM book_loans WHERE loan_id = ANY(%s) AND date_in > due_date
            ON CONFLICT (loan_id) DO UPDATE SET fine_amt = EXCLUDED.fine_amt
            WHERE fines.paid = FALSE AND fines.fine_amt <> EXCLUDED.fine_amt
            """,
            (DAILY_RATE, ids),
        )
    return sorted(returned, key=lambda row: row["loan_id"])
