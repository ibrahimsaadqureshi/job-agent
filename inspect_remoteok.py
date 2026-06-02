from scrapers.remoteok import get_jobs
from pprint import pprint

jobs = get_jobs()

print("Total jobs:", len(jobs))

print("\nFIRST JOB:\n")
pprint(jobs[1])