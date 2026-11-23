# Fines (Milestone 2)

**Files:** `fines.py` (logic), `fines_cli.py` (command-line runner)
**Requires:** Python 3.10+, PostgreSQL 14+, `pip install "psycopg[binary]"`
**Schema:** uses `book_loans` and `fines` from `my_schema.sql`, with no changes
(`fine_amt NUMERIC(10,2)` is fixed-decimal and `paid BOOLEAN`, as the spec requires).

## Functions
| Function | What it does |
|---|---|
| `refresh_fines(conn, today=None)` | Creates or updates a FINES row for every late loan at $0.25/day. Returned late: (date_in − due_date) × 0.25. Still out: (today − due_date) × 0.25. An unpaid fine is updated only when its amount changes; a paid fine is never touched. Safe to run any number of times (meant as a nightly job). |
| `pay_fines(conn, card_id)` | Pays **all** of a borrower's unpaid fines (no partial payments). Refused, with a clear message, if the borrower still has a late book checked out, has nothing to pay, or doesn't exist. |
| `get_fines(conn, include_paid=False, card_id=None)` | Fines **grouped by card_id** (summed per borrower). Paid fines are hidden by default; `include_paid=True` shows them. |
| `has_unpaid_fines(conn, card_id)` | For checkout: True if the borrower has an unpaid fine **or** an overdue book still out. |

## Design decisions
- **Payment while a late book is out:** the fine is still growing, so it can't be settled. Because partial payments aren't allowed either, any late book still out blocks the whole payment.
- **Checkout block:** an overdue book that is still out counts as an unpaid fine, even if the nightly refresh hasn't run yet.
- **Money:** amounts are computed in SQL `NUMERIC` and Python `Decimal`, never float.

## Running
```bash
export LIBRARY_DB="dbname=library user=postgres host=localhost"   # your connection
python fines_cli.py refresh                   # recompute all fines as of today
python fines_cli.py refresh --today 2026-12-05  # test as if it were another date
python fines_cli.py show                      # who owes money
python fines_cli.py show --all                # include paid fines
python fines_cli.py show --card ID000002
python fines_cli.py pay ID000001
```
