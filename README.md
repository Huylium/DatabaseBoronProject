# Database Boron Project
Database project for Group Boron for 4347 Database Systems

Language/version: Python 3.10+ and PostgreSQL. Verified with 
- CPython 3.12.14, PostgreSQL 16.2, and Psycopg 3.3.9.
- 
Compiler: not applicable; run the Python source directly. No separate compilation or build step is needed.

Third-party dependency: psycopg[binary]==3.3.9. Imports include psycopg, psycopg.rows.dict_row, and psycopg.sql.

Other imports are standard-library modules or files that are included with the project.

1. Set up Python and PostgreSQL
Open Git Bash in the extracted project folder. Install Python and PostgreSQL first, start the PostgreSQL service, and make sure psql and createdb are on PATH.

python -m venv .venv
source .venv/Scripts/activate
python -m pip install "psycopg[binary]==3.3.9"

If needed, use py -3 instead of python to create the environment. On macOS/Linux, activate with source
.venv/bin/activate. For PostgreSQL on Windows, a PATH example is below; replace 19 with your installed version:
export PATH="/c/Program Files/PostgreSQL/19/bin:$PATH"
Run this next command by itself, enter your PostgreSQL password, and press Enter:
read -r -s -p "PostgreSQL password: " PGPASSWORD
Then set the connection. Adjust the user, host, or port if your installation differs:

export PGPASSWORD
export LIBRARY_DB="host=localhost port=5432 dbname=library user=postgres"

3. Create and load the database
Skip this section if library is already populated. my_schema.sql drops existing tables, so use it only for a fresh setup.
Run these commands from the project root:
createdb -h localhost -U postgres library
psql -h localhost -U postgres -d library -v ON_ERROR_STOP=1 -f my_schema.sql
psql -h localhost -U postgres -d library -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
\copy book FROM 'output/books.csv' WITH (FORMAT csv)
\copy authors FROM 'output/authors.csv' WITH (FORMAT csv)
\copy book_authors FROM 'output/book_authors.csv' WITH (FORMAT csv)
\copy borrower FROM 'output/borrowers.csv' WITH (FORMAT csv)
COMMIT;
SQL
Use the included output/ files; they have no headers. Import once. Loans and fines start empty. Repeat the
connection-variable setup in a new terminal.

4. Run the features
Keep the virtual environment active and LIBRARY_DB set. Search uses one case-insensitive substring across ISBN, title,
or author:
python -c 'from search import search; print(search("will"))'
For checkout and returns, replace 12 below with the loan ID printed by checkout or find. checkin accepts one to three
loan IDs separated by spaces:
python loans_cli.py checkout 9780195153445 ID000001
python loans_cli.py find --card ID000001
python loans_cli.py checkin 12
Borrower creation is a Python function. This example returns a new card ID; reusing the same SSN is rejected:
python - <<'PY'
import os, psycopg
from borrowers import create_borrower
with psycopg.connect(os.environ["LIBRARY_DB"]) as conn:
print(create_borrower(conn, "Demo User", "000-00-0001", "1 Demo Street"))
PY
Refresh fines before viewing or paying. Payment requires the late books to be returned. Use show --all to include paid
history:
python fines_cli.py refresh
python fines_cli.py show
python fines_cli.py pay ID000001

5. Run the tests
createdb -h localhost -U postgres library_loans_test
export LIBRARY_TEST_DB="host=localhost dbname=library_loans_test user=postgres"
python -m unittest loans_test -v
Skip createdb if the test database exists. Tests supply their own records in a temporary schema; no CSV import is
needed. A successful run ends with 31 tests and OK. The GUI is part of Milestone 3.


NOTES:
-Have normalizer.py within the same folder of books.csv and borrowers.csv.
-Run "python normalize.py" in the folder directory.
