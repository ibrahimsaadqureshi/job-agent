import sqlite3

conn = sqlite3.connect("database/jobs.db")
cursor = conn.cursor()

cursor.execute("""
SELECT
    score,
    title,
    company,
    source
FROM jobs
ORDER BY score DESC
LIMIT 200
""")

jobs = cursor.fetchall()

print("\nTop 25 Ranked Jobs\n")
print("-" * 100)

seen = set()
printed = 0

for score, title, company, source in jobs:

    key = (
        title.strip().lower(),
        company.strip().lower()
    )

    if key in seen:
        continue

    seen.add(key)

    print(f"{score:>4} | {title} | {company} | {source}")

    printed += 1

    if printed >= 25:
        break

conn.close()