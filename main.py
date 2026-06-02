from scrapers.yc import (
    get_yc_jobs
)

from scrapers.remoteok import (
    get_remoteok_jobs
)

from greenhouse.scraper import (
    get_greenhouse_jobs
)

from database.db import (
    save_job
)


print(
    "\nCollecting jobs...\n"
)

yc_jobs = get_yc_jobs()

greenhouse_jobs = (
    get_greenhouse_jobs()
)

remoteok_jobs = (
    get_remoteok_jobs()
)

all_jobs = []

all_jobs.extend(
    yc_jobs
)

all_jobs.extend(
    greenhouse_jobs
)

all_jobs.extend(
    remoteok_jobs
)

for job in all_jobs:

    save_job(job)

print()

print("Summary")

print("-" * 30)

print(
    f"YC:         {len(yc_jobs)}"
)

print(
    f"Greenhouse: {len(greenhouse_jobs)}"
)

print(
    f"RemoteOK:   {len(remoteok_jobs)}"
)

print("-" * 30)

print(
    f"Total:      {len(all_jobs)}"
)

print(
    "\nDatabase updated."
)