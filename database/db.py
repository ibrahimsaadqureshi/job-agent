import sqlite3

DB_PATH = "database/jobs.db"


def save_job(job):

    conn = sqlite3.connect(
        DB_PATH
    )

    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO jobs
    (
        title,
        company,
        location,
        url,
        source,
        description
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    (
        job["title"],
        job["company"],
        job["location"],
        job["url"],
        job["source"],
        job.get(
            "description",
            ""
        )
    ))

    conn.commit()

    conn.close()