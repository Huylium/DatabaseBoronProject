# Set LIBRARY_TEST_DB first. The tests use their own tables in a temporary
# schema and clean up afterward, leaving the application data alone.
#Yaseen Hafid yxh190036

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
import os
from pathlib import Path
from threading import Barrier
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql

from fines import FineError, get_fines, pay_fines, refresh_fines
from loans import LoanError, checkin, checkout, find_active_loans
from search import search_books


class BookLoanTests(unittest.TestCase):
    DAY = date.today()
    BOOKS = [f"978000000000{i}" for i in range(1, 7)]

    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("LIBRARY_TEST_DB")
        if not cls.dsn:
            raise RuntimeError(
                "Set LIBRARY_TEST_DB to a PostgreSQL test database connection string. "
                "See README_loans.md."
            )
        # give this run its own schema so it doesnt mix with other test runs
        cls.schema = "loans_test_" + uuid4().hex
        with psycopg.connect(cls.dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
            cls.addClassCleanup(cls._drop_schema)
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema)))
            conn.execute(Path(__file__).with_name("my_schema.sql").read_text(encoding="utf-8"))

    @classmethod
    def _drop_schema(cls):
        # remove only the schema created for this run.
        with psycopg.connect(cls.dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))

    @classmethod
    def _connect(cls):
        conn = psycopg.connect(cls.dsn, autocommit=True)
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema)))
        
        conn.execute("SET lock_timeout TO '5s'")
        conn.execute("SET statement_timeout TO '10s'")
        return conn

    def setUp(self):
        # start each test with the same small set of books and borrowers.
        self.conn = self._connect()
        self.addCleanup(self.conn.close)
        self.conn.execute(
            "TRUNCATE fines, book_loans, book_authors, authors, book, borrower RESTART IDENTITY"
        )
        with self.conn.cursor() as cur:
            cur.executemany("INSERT INTO book VALUES (%s, %s)",
                            [(isbn, f"Test Book {i}") for i, isbn in enumerate(self.BOOKS, 1)])
            cur.executemany(
                "INSERT INTO borrower (card_id, ssn, bname, address) VALUES (%s, %s, %s, %s)",
                [("ID000001", "000-00-0001", "Alice Smith", "1 Test Street"),
                 ("ID000002", "000-00-0002", "Bob Jones", "2 Test Street")],
            )

    def _seed_loan(self, book=0, card="ID000001", due=None, returned=None):
        # add past or current loans directly when a test needs specific dates.
        due = due or self.DAY + timedelta(days=14)
        return self.conn.execute(
            """INSERT INTO book_loans (isbn, card_id, date_out, due_date, date_in)
               VALUES (%s, %s, %s, %s, %s) RETURNING loan_id""",
            (self.BOOKS[book], card, due - timedelta(days=14), due, returned),
        ).fetchone()[0]

    def test_checkout_sets_dates_and_preserves_text_isbn(self):
        loan = checkout(self.conn, self.BOOKS[0], "ID000001", today=self.DAY)
        self.assertEqual(loan["isbn"], self.BOOKS[0])
        self.assertEqual(loan["date_out"], self.DAY)
        self.assertEqual(loan["due_date"], self.DAY + timedelta(days=14))
        self.assertIsNone(loan["date_in"])

    def test_leading_zero_and_alphanumeric_isbn(self):
        self.conn.execute("INSERT INTO book VALUES ('012345678X', 'Legacy ISBN')")
        self.assertEqual(checkout(self.conn, "012345678X", "ID000001")["isbn"], "012345678X")

    def test_three_allowed_fourth_refused(self):
        for isbn in self.BOOKS[:3]:
            checkout(self.conn, isbn, "ID000001")
        with self.assertRaisesRegex(LoanError, "3 active loans"):
            checkout(self.conn, self.BOOKS[3], "ID000001")
        self.assertEqual(len(find_active_loans(self.conn, card_id="ID000001")), 3)

    def test_returned_history_does_not_count_toward_limit(self):
        for i in range(3):
            self._seed_loan(book=i, returned=self.DAY)
        checkout(self.conn, self.BOOKS[3], "ID000001")
        self.assertEqual(len(find_active_loans(self.conn)), 1)

    def test_unavailable_to_same_or_different_borrower(self):
        checkout(self.conn, self.BOOKS[0], "ID000001")
        for card in ["ID000001", "ID000002"]:
            with self.subTest(card=card), self.assertRaisesRegex(LoanError, "not available"):
                checkout(self.conn, self.BOOKS[0], card)

    def test_missing_book_and_borrower(self):
        with self.assertRaisesRegex(LoanError, "No book"):
            checkout(self.conn, "missing", "ID000001")
        with self.assertRaisesRegex(LoanError, "No borrower"):
            checkout(self.conn, self.BOOKS[0], "missing")
        self.assertEqual(find_active_loans(self.conn), [])

    def test_empty_and_wrong_type_inputs(self):
        for isbn, card in [("", "ID000001"), (None, "ID000001"), (123, "ID000001"),
                           (self.BOOKS[0], " ")]:
            with self.subTest(isbn=isbn, card=card), self.assertRaises(LoanError):
                checkout(self.conn, isbn, card)

    def test_unpaid_returned_fine_blocks_checkout(self):
        loan_id = self._seed_loan(due=self.DAY - timedelta(days=2), returned=self.DAY)
        self.conn.execute("INSERT INTO fines VALUES (%s, 0.50, FALSE)", (loan_id,))
        with self.assertRaisesRegex(LoanError, "unpaid fines"):
            checkout(self.conn, self.BOOKS[1], "ID000001")

    def test_overdue_without_refresh_blocks_checkout(self):
        self._seed_loan(due=self.DAY - timedelta(days=1))
        with self.assertRaisesRegex(LoanError, "unpaid fines"):
            checkout(self.conn, self.BOOKS[1], "ID000001")

    def test_returned_late_without_refresh_also_blocks_checkout(self):
        self._seed_loan(due=self.DAY - timedelta(days=1), returned=self.DAY)
        with self.assertRaisesRegex(LoanError, "unpaid fines"):
            checkout(self.conn, self.BOOKS[1], "ID000001")

    def test_due_today_is_not_overdue(self):
        self._seed_loan(due=self.DAY)
        checkout(self.conn, self.BOOKS[1], "ID000001")

    def test_paid_fine_allows_checkout(self):
        loan_id = self._seed_loan(due=self.DAY - timedelta(days=1), returned=self.DAY)
        self.conn.execute("INSERT INTO fines VALUES (%s, 0.25, TRUE)", (loan_id,))
        checkout(self.conn, self.BOOKS[1], "ID000001")

    def test_another_borrowers_fine_does_not_block(self):
        loan_id = self._seed_loan(card="ID000002", due=self.DAY - timedelta(days=1), returned=self.DAY)
        self.conn.execute("INSERT INTO fines VALUES (%s, 0.25, FALSE)", (loan_id,))
        checkout(self.conn, self.BOOKS[1], "ID000001")

    def test_find_by_isbn_card_name_and_combination(self):
        expected = checkout(self.conn, self.BOOKS[0], "ID000001")["loan_id"]
        checkout(self.conn, self.BOOKS[1], "ID000002")
        for filters in [{"isbn": self.BOOKS[0]}, {"card_id": "ID000001"},
                        {"borrower_name": "SMI"},
                        {"isbn": self.BOOKS[0][-3:], "card_id": "ID000001", "borrower_name": "alice"}]:
            with self.subTest(filters=filters):
                rows = find_active_loans(self.conn, **filters)
                self.assertEqual([r["loan_id"] for r in rows], [expected])
                self.assertEqual(rows[0]["title"], "Test Book 1")
        self.assertEqual(find_active_loans(self.conn, isbn=self.BOOKS[0], card_id="ID000002"), [])

    def test_find_excludes_returns_and_handles_no_match(self):
        self._seed_loan(returned=self.DAY)
        self.assertEqual(find_active_loans(self.conn), [])
        self.assertEqual(find_active_loans(self.conn, borrower_name="nobody"), [])

    def test_find_treats_wildcards_and_sql_text_literally(self):
        checkout(self.conn, self.BOOKS[0], "ID000001")
        # inputs should be searched as text
        for text in ["%", "_", "\\", "' OR 1=1 --"]:
            with self.subTest(text=text):
                self.assertEqual(find_active_loans(self.conn, borrower_name=text), [])

    def test_checkin_updates_date_keeps_history_and_restores_availability(self):
        # check that existing search code sees the checkout and return.
        loan = checkout(self.conn, self.BOOKS[0], "ID000001")
        self.assertEqual(search_books(self.conn, self.BOOKS[0])[0]["status"], "OUT")
        rows = checkin(self.conn, [loan["loan_id"]])
        self.assertEqual(rows[0]["date_in"], self.DAY)
        self.assertEqual(find_active_loans(self.conn), [])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM book_loans").fetchone()[0], 1)
        self.assertEqual(search_books(self.conn, self.BOOKS[0])[0]["status"], "IN")
        checkout(self.conn, self.BOOKS[0], "ID000002")

    def test_checkin_three_selected_loans(self):
        ids = [checkout(self.conn, isbn, "ID000001")["loan_id"] for isbn in self.BOOKS[:3]]
        self.assertEqual(len(checkin(self.conn, ids)), 3)
        self.assertEqual(find_active_loans(self.conn), [])

    def test_checkin_multiple_borrowers(self):
        ids = [checkout(self.conn, self.BOOKS[0], "ID000001")["loan_id"],
               checkout(self.conn, self.BOOKS[1], "ID000002")["loan_id"]]
        self.assertEqual(len(checkin(self.conn, ids)), 2)

    def test_invalid_return_selection_does_not_change_loans(self):
        loan_id = checkout(self.conn, self.BOOKS[0], "ID000001")["loan_id"]
        for ids in [[], [loan_id, loan_id], [loan_id, 99999], [0], [-1], [True],
                    ["1"], [2**40], [1, 2, 3, 4], None]:
            with self.subTest(ids=ids), self.assertRaises(LoanError):
                checkin(self.conn, ids)
        self.assertEqual(len(find_active_loans(self.conn)), 1)

    def test_already_returned_loan_rolls_back_entire_selection(self):
        first = checkout(self.conn, self.BOOKS[0], "ID000001")["loan_id"]
        second = checkout(self.conn, self.BOOKS[1], "ID000001")["loan_id"]
        checkin(self.conn, [first])
        with self.assertRaisesRegex(LoanError, "already been checked in"):
            checkin(self.conn, [first, second])
        self.assertEqual([r["loan_id"] for r in find_active_loans(self.conn)], [second])

    def test_return_before_checkout_refused(self):
        loan_id = checkout(self.conn, self.BOOKS[0], "ID000001")["loan_id"]
        with self.assertRaisesRegex(LoanError, "before checkout"):
            checkin(self.conn, [loan_id], today=self.DAY - timedelta(days=1))
        self.assertEqual(len(find_active_loans(self.conn)), 1)

    def test_on_time_return_creates_no_fine(self):
        loan_id = self._seed_loan(due=self.DAY)
        checkin(self.conn, [loan_id])
        self.assertEqual(get_fines(self.conn), [])

    def test_late_return_creates_exact_fine(self):
        loan_id = self._seed_loan(due=self.DAY - timedelta(days=7))
        checkin(self.conn, [loan_id])
        self.assertEqual(self.conn.execute("SELECT fine_amt, paid FROM fines").fetchone(),
                         (Decimal("1.75"), False))

    def test_late_return_updates_existing_unpaid_fine(self):
        loan_id = self._seed_loan(due=self.DAY - timedelta(days=4))
        self.conn.execute("INSERT INTO fines VALUES (%s, 0.25, FALSE)", (loan_id,))
        checkin(self.conn, [loan_id])
        self.assertEqual(self.conn.execute("SELECT COUNT(*), SUM(fine_amt) FROM fines").fetchone(),
                         (1, Decimal("1.00")))

    def test_paid_fine_is_never_overwritten(self):
        loan_id = self._seed_loan(due=self.DAY - timedelta(days=4))
        self.conn.execute("INSERT INTO fines VALUES (%s, 0.50, TRUE)", (loan_id,))
        checkin(self.conn, [loan_id])
        self.assertEqual(self.conn.execute("SELECT fine_amt, paid FROM fines").fetchone(),
                         (Decimal("0.50"), True))

    def test_full_late_return_payment_checkout_flow(self):
        # Follow a late book through return, payment, and borrowing again.
        loan_id = self._seed_loan(due=self.DAY - timedelta(days=3))
        refresh_fines(self.conn)
        with self.assertRaises(FineError):
            pay_fines(self.conn, "ID000001")
        checkin(self.conn, [loan_id])
        self.assertEqual(get_fines(self.conn)[0]["unpaid_total"], Decimal("0.75"))
        with self.assertRaises(LoanError):
            checkout(self.conn, self.BOOKS[1], "ID000001")
        self.assertEqual(pay_fines(self.conn, "ID000001"), Decimal("0.75"))
        self.assertEqual(get_fines(self.conn), [])
        checkout(self.conn, self.BOOKS[1], "ID000001")
        self.assertEqual(refresh_fines(self.conn), 0)

    def test_loan_and_fine_changes_rollback_together_on_database_error(self):
        loan_id = self._seed_loan(due=self.DAY - timedelta(days=2))
        # Force the fine save to fail and check that the return is undone too.
        self.conn.execute("ALTER TABLE fines ADD CHECK (fine_amt < 0)")
        try:
            with self.assertRaises(psycopg.errors.CheckViolation):
                checkin(self.conn, [loan_id])
            self.assertIsNone(self.conn.execute(
                "SELECT date_in FROM book_loans WHERE loan_id = %s", (loan_id,)).fetchone()[0])
        finally:
            self.conn.execute("ALTER TABLE fines DROP CONSTRAINT fines_fine_amt_check")

    def test_outer_transaction_can_rollback_checkout(self):
        with self.conn.transaction() as transaction:
            checkout(self.conn, self.BOOKS[0], "ID000001")
            raise psycopg.Rollback(transaction)
        self.assertEqual(find_active_loans(self.conn), [])

    def _race(self, requests):
        # Let two separate connections try checkout at about the same time.
        barrier = Barrier(2)

        def attempt(isbn, card):
            with self._connect() as conn:
                barrier.wait(timeout=5)
                try:
                    checkout(conn, isbn, card)
                    return "success"
                except LoanError:
                    return "refused"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt, *request) for request in requests]
            return sorted(future.result(timeout=15) for future in futures)

    def test_concurrent_checkout_cannot_lend_same_book_twice(self):
        self.assertEqual(self._race([(self.BOOKS[0], "ID000001"), (self.BOOKS[0], "ID000002")]),
                         ["refused", "success"])
        self.assertEqual(len(find_active_loans(self.conn)), 1)

    def test_concurrent_checkout_cannot_exceed_three_loan_limit(self):
        for isbn in self.BOOKS[:2]:
            checkout(self.conn, isbn, "ID000001")
        self.assertEqual(self._race([(self.BOOKS[2], "ID000001"), (self.BOOKS[3], "ID000001")]),
                         ["refused", "success"])
        self.assertEqual(len(find_active_loans(self.conn)), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
