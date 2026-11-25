"""Filter stage: is this a tech role I could do, and can I apply from Pakistan?

M0 STUB. Lane B (M2) replaces the body of `evaluate` with the real rules from
PLAN.md section 3: category, location eligibility and seniority. Keep the
signature: the pipeline calls `evaluate(job)` once per fetched job.
"""

from __future__ import annotations

from jobagent.models import Category, Job, Verdict


def evaluate(job: Job) -> Verdict:
    """Return keep/drop for one job, with its category and location rule.

    Contract:
    - keep=True  -> category is set, location_rule says why location passed
                    ("worldwide", "asia", "emea", "pakistan", "timezone", "unspecified").
    - keep=False -> reason is a short, groupable label ("non-tech", "us-only",
                    "staff+ title", ...). It's counted in RunStats.dropped, so keep
                    the label set small and stable.
    """
    return Verdict(keep=True, category=Category.TECH_ENTRY, location_rule="unchecked")
