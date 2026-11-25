"""In-run dedupe: the same posting listed on several boards in one run.

Cross-run dedupe is not here: the pipeline compares job ids with Tracker.seen_ids().

M0 STUB: collapses exact id matches only. Lane B (M2) adds the company + title
fingerprint from PLAN.md section 3. Keep the signature.
"""

from __future__ import annotations

from jobagent.models import Job


def dedupe_in_run(jobs: list[Job]) -> list[tuple[Job, tuple[str, ...]]]:
    """Collapse duplicates, keeping the first occurrence (sources are fetched in priority order).

    Returns (kept_job, other_sources_that_listed_it) pairs, in input order.
    """
    kept: dict[str, Job] = {}
    also_on: dict[str, list[str]] = {}
    for job in jobs:
        if job.id in kept:
            if job.source != kept[job.id].source and job.source not in also_on[job.id]:
                also_on[job.id].append(job.source)
            continue
        kept[job.id] = job
        also_on[job.id] = []
    return [(job, tuple(also_on[job_id])) for job_id, job in kept.items()]
