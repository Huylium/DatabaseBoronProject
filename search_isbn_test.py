from search import search

rows = search("9780451210630")
print("full ISBN:", len(rows), "result(s)")
for row in rows:
    print("   ", row)

print()
for row in search("a case of need"):
    print(row["isbn"], row["status"])