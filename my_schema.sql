CREATE TABLE book (
    isbn VARCHAR(13) PRIMARY KEY,
    title VARCHAR(500) NOT NULL
):

CREATE TABLE authors (
    author_id INT PRIMARY KEY,
    name VARCHAR(500) NOT NULL
):

CREATE TABLE book_authors (
    isbn VARCHAR(13) REFERENCES book(isbn)
    author_id INT REFERENCES authors(author_id)
    PRIMARY KEY (isbn, author_id)

    
):

CREATE TABLE borrower (
    card_id VARCHAR(10) PRIMARY KEY,
    ssn VARCHAR(11) NOT NULL UNIQUE,
    Bname VARCHAR(500) NOT NULL,
    address VARCHAR(500) NOT NULL,
    phone VARCHAR(20)
):

CREATE TABLE book_loans(
    loan_id SERIAL PRIMARY KEY,
    isbn VARCHAR(13) NOT NULL REFERENCES book(isbn),
    card_id VARCHAR(10) NOT NULL REFERENCES borrower(card_id),
    date_out DATE NOT NULL,
    due_date DATE NOT NULL,
    date_in DATE
):

CREATE TABLE fines(
    loan_id INT references book_loans(loan_id),
    fine_amt INT NOT NULL,
    paid BOOLEAN NOT NULL,

):