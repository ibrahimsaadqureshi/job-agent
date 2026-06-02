from greenhouse.scraper import (
    get_greenhouse_jobs
)

jobs = get_greenhouse_jobs()

print()

print(
    f"Total jobs: "
    f"{len(jobs)}"
)

print()

for job in jobs[:10]:

    print(
        job["title"]
    )