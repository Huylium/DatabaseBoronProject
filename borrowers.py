class BorrowerError(Exception):
    pass


def create_borrower(conn, name, ssn, address, phone=None):
    "Create a new borrower in library database"

    # Checks if required information is inputted
    if not name or not name.strip():
        raise BorrowerError("Sorry, the borrower name is required")

    if not ssn or not ssn.strip():
        raise BorrowerError("Sorry, the SSN is required")

    if not address or not address.strip():
        raise BorrowerError("Sorry, the address is required.")

    # Remove extra spaces from inputted info    
    name = name.strip()
    ssn = ssn.strip()
    address = address.strip()

    # Check if inputted SSN belongs to existing borrower
    with conn.cursor() as cur:
        cur.execute(
            "SELECT card_id FROM borrower WHERE ssn = %s",
            (ssn,)
        )

        existing = cur.fetchone()

        if existing:
            conn.rollback()
            raise BorrowerError("Sorry, a borrower with this SSN already exists")

        # Create a new card ID
        cur.execute("SELECT MAX (card_id) FROM borrower")
        last_id = cur.fetchone()[0]

        if last_id is None:
            next_number = 1
        else:
            next_number = int(last_id[2:]) + 1

        new_card_id = f"ID{next_number:06d}"
        
        # Adds new borrower to database
        cur.execute(
            "INSERT INTO borrower (card_id, ssn, bname, address, phone) "
            "VALUES (%s, %s, %s, %s, %s)",
            (new_card_id, ssn, name, address, phone)
        )

    conn.commit()
    return new_card_id

