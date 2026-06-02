import sqlite3

conn = sqlite3.connect(
    "database/jobs.db"
)

cursor = conn.cursor()

cursor.execute("""
SELECT
source,
COUNT(*)
FROM jobs
GROUP BY source
ORDER BY COUNT(*) DESC
""")

rows = cursor.fetchall()

print()

for row in rows:
    print(
        f"{row[0]:15} {row[1]}"
    )

print()

conn.close()