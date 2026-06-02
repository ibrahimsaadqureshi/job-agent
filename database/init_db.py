import sqlite3

conn = sqlite3.connect("database/jobs.db")

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS jobs(

    id INTEGER PRIMARY KEY,

    title TEXT,
    company TEXT,
    location TEXT,

    url TEXT UNIQUE,

    source TEXT,

    description TEXT,

    score INTEGER DEFAULT 0,

    matched INTEGER DEFAULT 0,

    reviewed INTEGER DEFAULT 0,

    date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()

print("Database initialized")