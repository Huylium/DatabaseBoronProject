import csv
import os
import re
from string import capwords

# takes (..) series 
STRIP_SERIES = True   


# inputs must change based on files (books was originally called books-1..?????)
BOOKS_INPUT = "books.csv" 
BORROWERS_INPUT = "borrowers.csv"
OUTPUT_DIR = "output"   



# helpers
def normCase(string): # removes extra spaces and caps every word
    return capwords(" ".join(string.split()))

def quoter(string):
    # wrap text in double quotes; a quote inside the text is doubled
    return '"' + string.replace('"', '""') + '"'


def normalizeBooks(inputPath, outDir):
    #output variables
    books = {}          # isbn = title
    authors = {}        # lowercase name = (author_id, name)
    book_authors = {}   # (isbn, author_id)
    skipped = [] # holds the skips

    with open(inputPath, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)   # comma delimiter, respects "quoted, fields"
        next(reader)             # skips the header row
        for row in reader:
            if len(row) < 4:
                skipped.append(row)
                continue
            isbn = row[1].strip()    # ISBN13 (row[0] is ISBN10)
            title = row[2]
            if STRIP_SERIES:
                title = re.sub(r"\s*\([^)]*\)\s*$", "", title)
            books[isbn] = normCase(title)

            for name in row[3].split(","):
                name = normCase(name)
                if not name:
                    continue
                key = name.lower()
                if key not in authors:
                    authors[key] = (len(authors) + 1, name)
                book_authors[(isbn, authors[key][0])] = None

    os.makedirs(outDir, exist_ok=True)

    with open(os.path.join(outDir, "books.csv"), "w", encoding="utf-8", newline="\n") as f:
        for isbn, title in books.items():
            f.write(f"{isbn},{quoter(title)}\n")

    with open(os.path.join(outDir, "authors.csv"), "w", encoding="utf-8", newline="\n") as f:
        for author_id, name in authors.values():
            f.write(f"{author_id},{quoter(name)}\n")

    with open(os.path.join(outDir, "book_authors.csv"), "w", encoding="utf-8", newline="\n") as f:
        for isbn, author_id in book_authors:
            f.write(f"{isbn},{author_id}\n")

    return books, authors, book_authors, skipped


def normalizeBorrowers(inputPath, outDir):
    # Input columns:  ID0000id, ssn, first_name, last_name, email, address, city, state, phone
    # Output columns: Card_id, Ssn, Bname, Address, Phone  (matches the BORROWER table)
    borrowers = {}   # card_id = (ssn, name, address, phone); dict removes repeated ids
    skipped = []

    with open(inputPath, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        next(reader)   # skip the header row
        for row in reader:
            if len(row) < 9:
                skipped.append(row)
                continue
            cardId = row[0].strip()
            ssn = row[1].strip()
            name = normCase(row[2] + " " + row[3])             # first + last = Bname
            address = ", ".join(                                # street, city, state
                " ".join(part.split()) for part in (row[5], row[6], row[7])
            )
            phone = row[8].strip()
            # row[4] (email) is dropped: the BORROWER table has no email column
            borrowers[cardId] = (ssn, name, address, phone)

    os.makedirs(outDir, exist_ok=True)

    with open(os.path.join(outDir, "borrowers.csv"), "w", encoding="utf-8", newline="\n") as f:
        for cardId, (ssn, name, address, phone) in borrowers.items():
            f.write(",".join(quoter(v) for v in (cardId, ssn, name, address, phone)) + "\n")

    return borrowers, skipped


if __name__ == "__main__":
    books, authors, book_authors, skipped = normalizeBooks(BOOKS_INPUT, OUTPUT_DIR)
    print(len(books), "books,", len(authors), "authors,", len(book_authors), "links")
    print("skipped book rows:", len(skipped))

    borrowers, skipped = normalizeBorrowers(BORROWERS_INPUT, OUTPUT_DIR)
    print(len(borrowers), "borrowers")
    print("skipped borrower rows:", len(skipped))