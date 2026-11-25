"""The four seams of the pipeline.

Every external system sits behind one of these protocols, so the pipeline can run
end to end with local stand-ins (dry-run) or fakes (tests), and each piece can be
built and tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import requests

from jobagent.models import Candidate, Job, RunStats, TrackerRow


@runtime_checkable
class Source(Protocol):
    """A job board. One module per source in jobagent/sources/."""

    name: str  # short key used in the Sheet's `source` column, e.g. "remoteok"
    label: str  # human name for attribution, e.g. "Remote OK"

    def fetch(self, session: requests.Session) -> list[Job]:
        """Return the source's current postings, normalized.

        Raise on total failure (network down, bad payload); the pipeline logs the
        error and carries on with the other sources. Skip individual malformed
        items instead of raising.
        """
        ...


@runtime_checkable
class Scorer(Protocol):
    """Fit scoring and note drafting, backed by an LLM."""

    def score(self, jobs: list[Job], profile: str) -> dict[str, tuple[int, str]]:
        """Score jobs against the profile. Returns {job.id: (score 0-100, one-line reason)}.

        Jobs missing from the result are treated as unscored and retried next run.
        """
        ...

    def draft(self, job: Job, profile: str, reason: str) -> str:
        """Write a short tailored application note for one job."""
        ...


@runtime_checkable
class Tracker(Protocol):
    """The persistent job list (Google Sheet in production)."""

    def seen_ids(self) -> set[str]:
        """Ids of every job already recorded, for cross-run dedupe."""
        ...

    def append(self, rows: list[TrackerRow]) -> None:
        """Append new rows. Never edits existing rows."""
        ...


@dataclass
class Digest:
    """What the daily message says, independent of the channel."""

    run_date: str
    sections: dict[str, list[Candidate]] = field(default_factory=dict)  # title -> jobs
    stats: RunStats = field(default_factory=RunStats)
    sheet_url: str = ""
    threshold: int = 70

    @property
    def is_empty(self) -> bool:
        return not any(self.sections.values())


@runtime_checkable
class Notifier(Protocol):
    """Delivers the daily digest (Slack in production)."""

    def send(self, digest: Digest) -> None: ...

    def send_failure(self, message: str) -> None:
        """Short failure notice. Must not include job text, profile text or secrets."""
        ...
