"""In-memory fakes for the pipeline's interfaces. Shared by all test files."""

from __future__ import annotations

from datetime import datetime, timezone

from jobagent.interfaces import Digest
from jobagent.models import Job, TrackerRow


def make_job(n: int = 1, *, source: str = "fake", day: int = 1, **overrides) -> Job:
    fields = dict(
        source=source,
        url=f"https://jobs.example.com/{n}",
        title=f"Software Engineer {n}",
        company=f"Company {n}",
        location="Worldwide",
        description=f"Build things with TypeScript. Job {n}.",
        posted_at=datetime(2026, 11, day, tzinfo=timezone.utc),
    )
    fields.update(overrides)
    return Job(**fields)


class FakeSource:
    def __init__(self, name: str, jobs: list[Job] | None = None, error: Exception | None = None):
        self.name = name
        self.label = name.title()
        self.jobs = jobs or []
        self.error = error
        self.calls = 0

    def fetch(self, session):
        self.calls += 1
        if self.error:
            raise self.error
        return list(self.jobs)


class FakeScorer:
    """Scores from a fixed table: {job.id: score}. Unknown ids are left unscored."""

    def __init__(self, scores: dict[str, int], *, fail_score: bool = False, fail_draft_ids=()):
        self.scores = scores
        self.fail_score = fail_score
        self.fail_draft_ids = set(fail_draft_ids)
        self.scored_batches: list[list[str]] = []
        self.drafted: list[str] = []

    def score(self, jobs, profile):
        self.scored_batches.append([j.id for j in jobs])
        if self.fail_score:
            raise RuntimeError("llm down")
        return {j.id: (self.scores[j.id], f"reason {j.id}") for j in jobs if j.id in self.scores}

    def draft(self, job, profile, reason):
        if job.id in self.fail_draft_ids:
            raise RuntimeError("draft failed")
        self.drafted.append(job.id)
        return f"draft for {job.title}"


class MemoryTracker:
    def __init__(self, seen: set[str] | None = None):
        self.seen = set(seen or ())
        self.rows: list[TrackerRow] = []

    def seen_ids(self) -> set[str]:
        return set(self.seen)

    def append(self, rows: list[TrackerRow]) -> None:
        self.rows.extend(rows)
        self.seen |= {r.id for r in rows}


class CapturingNotifier:
    def __init__(self):
        self.digests: list[Digest] = []
        self.failures: list[str] = []

    def send(self, digest: Digest) -> None:
        self.digests.append(digest)

    def send_failure(self, message: str) -> None:
        self.failures.append(message)
