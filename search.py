import os
import psycopg

SEARCH_SQL = """
    SELECT b.isbn, b.title,
           string_agg(a.name, ', ') AS authors,
           CASE WHEN EXISTS (SELECT 1 FROM book_loans l
                             WHERE l.isbn = b.isbn AND l.date_in IS NULL)
                THEN 'OUT' ELSE 'IN' END AS status
    FROM book b
    LEFT JOIN book_authors ba ON ba.isbn = b.isbn
    LEFT JOIN authors a ON a.author_id = ba.author_id
    WHERE b.isbn ILIKE %(pattern)s
       OR b.title ILIKE %(pattern)s
       OR EXISTS (SELECT 1
                  FROM book_authors ba2
                  JOIN authors a2 ON a2.author_id = ba2.author_id
                  WHERE ba2.isbn = b.isbn AND a2.name ILIKE %(pattern)s)
    GROUP BY b.isbn, b.title
    ORDER BY b.title
"""

def search_books(conn, text): #testing for fines collaboration
    text = text.strip()
    if not text:
        return []
    pattern = f"%{text}%"
    with conn.cursor() as cur:
        cur.execute(SEARCH_SQL, {"pattern": pattern})
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.commit()
    return rows

def search(text):
    with psycopg.connect(os.environ["LIBRARY_DB"]) as conn:
        return search_books(conn, text)