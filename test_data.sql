-- Optional practice data for testing fines. Run AFTER loading the Milestone 1 data into an EMPTY book_loans/fines.
-- Five practice loans (today = 2026-11-23). Each loan lasts 14 days.
INSERT INTO book_loans (isbn, card_id, date_out, due_date, date_in) VALUES
 ((SELECT isbn FROM book LIMIT 1 OFFSET 0), 'ID000001', '2026-10-01', '2026-10-15', '2026-10-14'), -- 1: returned early
 ((SELECT isbn FROM book LIMIT 1 OFFSET 1), 'ID000001', '2026-10-01', '2026-10-15', '2026-10-25'), -- 2: returned 10 days late
 ((SELECT isbn FROM book LIMIT 1 OFFSET 2), 'ID000002', '2026-11-04', '2026-11-18', NULL),         -- 3: still out, 5 days late
 ((SELECT isbn FROM book LIMIT 1 OFFSET 3), 'ID000003', '2026-11-20', '2026-12-04', NULL),         -- 4: still out, not due yet
 ((SELECT isbn FROM book LIMIT 1 OFFSET 4), 'ID000004', '2026-09-01', '2026-09-15', '2026-09-23'); -- 5: returned 8 days late, already paid
INSERT INTO fines VALUES (5, 2.00, TRUE);                                                            -- loan 5's fine was paid
