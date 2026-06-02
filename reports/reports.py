import sqlite3

conn = sqlite3.connect(
    "database/jobs.db"
)

cursor = conn.cursor()

cursor.execute("""
SELECT source, COUNT(*)
FROM jobs
GROUP BY source
""")

rows = cursor.fetchall()

for row in rows:
    print(row)