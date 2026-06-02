import sqlite3

conn = sqlite3.connect(
    "database/jobs.db"
)

cursor = conn.cursor()

cursor.execute("""
SELECT
title,
company,
source
FROM jobs
ORDER BY RANDOM()
LIMIT 25
""")

rows = cursor.fetchall()

for row in rows:

    print("-" * 60)

    print(
        f"Title: {row[0]}"
    )

    print(
        f"Company: {row[1]}"
    )

    print(
        f"Source: {row[2]}"
    )

conn.close()
