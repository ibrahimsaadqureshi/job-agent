import sqlite3

from ranking.scorer import (
    calculate_score
)
conn = sqlite3.connect(
    "database/jobs.db"
)

cursor = conn.cursor()

cursor.execute("""
SELECT
    id,
    title,
    description
FROM jobs
""")

jobs = cursor.fetchall()

updated = 0

for job in jobs:

    job_id = job[0]
    title = job[1]
    description = job[2] or ""

    score, matched = (
        calculate_score(
            title,
            description
        )
    )

    cursor.execute(
        """
        UPDATE jobs
        SET
            score=?,
            matched=?
        WHERE id=?
        """,
        (
            score,
            len(matched),
            job_id
        )
    )

    updated += 1

conn.commit()

conn.close()

print(
    f"Ranked {updated} jobs"
)