CREATE TABLE book (
    isbn VARCHAR(13) PRIMARY KEY,
    title VARCHAR(500) NOT NULL
):

CREATE TABLE authors (
    author_id INT PRIMARY KEY,
    name VARCHAR(500) NOT NULL
):

CREATE TABLE book_authors (
    isbn VARCHAR(13) references book(isbn)
    author_id INT references authors(author_id)
    PRIMARY KEY (isbn, author_id)

    
):

CREATE TABLE borrower (
    card_id INT PRIMARY KEY,
    ssn INT NOT NULL,
    Bname VARCHAR(500) NOT NULL,
    address VARCHAR(500) NOT NULL,
    phone INT NOT NULL
):

CREATE TABLE book_loans(
    loan_id INT PRIMARY KEY,
    isbn VARCHAR(13) NOT NULL,
    card_id INT NOT NULL,
    date_out VARCHAR NOT NULL,
    due_date VARCHAR NOT NULL,
):

CREATE TABLE fines(
    loan_id INT references book_loans(loan_id),
    fine_amt INT NOT NULL,
    paid BOOLEAN NOT NULL,

):