from search import search

for text in ["will", "WILL", "crichton", "zzzzqq", ""]:
    rows = search(text)
    print(f"{text!r}: {len(rows)} result(s)")
    for row in rows[:3]:
        print("   ", row)