"""Core data types shared by every stage of the pipeline.

These are the contracts that sources, filters, the scorer, the tracker and the
notifier agree on. Change them deliberately: the Sheet column order and the job
id format are persisted, so changing them breaks cross-run dedupe.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class Category(str, Enum):
    """Which digest section a kept job belongs to."""

    STACK = "stack"  # my current stack: TypeScript / React / Next.js / Node / NestJS
    AUTOMATION = "automation"  # n8n, Zapier, GoHighLevel, CRM / integration work
    TECH_ENTRY = "tech-entry"  # any other technical role I could start in and learn on


@dataclass(frozen=True)
class Job:
    """One job posting, normalized from any source.

    Sources fill every field they can. Unknown text fields are "" rather than None,
    so downstream code never has to null-check strings.
    """

    source: str  # source key, e.g. "remoteok", "wwr", "hn"
    url: str  # the source's own page for the posting (required, for attribution)
    title: str
    company: str
    location: str = ""  # raw location text exactly as the source gives it
    description: str = ""  # plain text, HTML already stripped
    posted_at: datetime | None = None  # timezone-aware UTC when the source provides it
    salary: str = ""  # human-readable, e.g. "$60k-$80k / year"; "" when not listed
    tags: tuple[str, ...] = ()  # source tags / skills, lowercased
    apply_url: str = ""  # direct application link if different from url
    # Structured eligibility data when the source has it (e.g. Himalayas country list,
    # WWR "region"). Empty tuple means "the source gave no structured restriction".
    location_restrictions: tuple[str, ...] = ()
    source_id: str = ""  # the source's own id, if any

    @property
    def id(self) -> str:
        """Stable id used for cross-run dedupe and as the Sheet's `id` column."""
        return job_id(self.url)


@dataclass(frozen=True)
class Verdict:
    """Outcome of the filter stage for one job."""

    keep: bool
    category: Category | None = None  # set when keep is True
    location_rule: str = ""  # why location passed, e.g. "worldwide", "asia", "unspecified"
    reason: str = ""  # why the job was dropped, e.g. "non-tech title", "US only"

    @classmethod
    def drop(cls, reason: str) -> Verdict:
        return cls(keep=False, reason=reason)


@dataclass(frozen=True)
class Assessment:
    """LLM output for one job. score is None when the job could not be scored this run."""

    job_id: str
    score: int | None
    reason: str = ""
    draft: str = ""


@dataclass(frozen=True)
class Candidate:
    """A job that passed the filters, with its filter verdict and (optional) assessment."""

    job: Job
    verdict: Verdict
    assessment: Assessment | None = None
    also_on: tuple[str, ...] = ()  # other sources that listed the same job this run

    @property
    def score(self) -> int | None:
        return self.assessment.score if self.assessment else None


# Persisted Sheet layout. Append-only: never reorder, only add new columns at the end.
SHEET_COLUMNS: tuple[str, ...] = (
    "date",
    "source",
    "company",
    "title",
    "link",
    "location rule",
    "salary",
    "score",
    "reason",
    "draft note",
    "status",
    "category",
    "id",
)


@dataclass(frozen=True)
class TrackerRow:
    """One row in the tracker Sheet, in SHEET_COLUMNS order."""

    date: date
    source: str
    company: str
    title: str
    link: str
    location_rule: str
    salary: str
    score: int | None
    reason: str
    draft_note: str
    status: str
    category: str
    id: str

    @classmethod
    def from_candidate(cls, c: Candidate, run_date: date) -> TrackerRow:
        a = c.assessment
        source = c.job.source if not c.also_on else f"{c.job.source} (+{', '.join(c.also_on)})"
        return cls(
            date=run_date,
            source=source,
            company=c.job.company,
            title=c.job.title,
            link=c.job.url,
            location_rule=c.verdict.location_rule,
            salary=c.job.salary,
            score=a.score if a else None,
            reason=a.reason if a else "",
            draft_note=a.draft if a else "",
            status="new",
            category=c.verdict.category.value if c.verdict.category else "",
            id=c.job.id,
        )

    def as_list(self) -> list[str | int]:
        """Values in SHEET_COLUMNS order, ready for a spreadsheet append."""
        return [
            self.date.isoformat(),
            self.source,
            self.company,
            self.title,
            self.link,
            self.location_rule,
            self.salary,
            "" if self.score is None else self.score,
            self.reason,
            self.draft_note,
            self.status,
            self.category,
            self.id,
        ]


@dataclass
class RunStats:
    """Counts reported at the end of a run. Safe to log publicly: no job text."""

    fetched: dict[str, int] = field(default_factory=dict)  # per source
    source_errors: dict[str, str] = field(default_factory=dict)  # source -> short error
    dropped: dict[str, int] = field(default_factory=dict)  # drop reason -> count
    kept: int = 0
    duplicates_in_run: int = 0
    already_seen: int = 0
    new: int = 0
    scored: int = 0
    unscored: int = 0
    drafted: int = 0
    written: int = 0

    @property
    def total_fetched(self) -> int:
        return sum(self.fetched.values())


# --- Job id -----------------------------------------------------------------------

# Query parameters that only track clicks and never identify a posting.
_TRACKING_PARAMS = frozenset(
    {"ref", "referrer", "source", "src", "gh_src", "fbclid", "gclid", "mc_cid", "mc_eid"}
)


def canonical_url(url: str) -> str:
    """Normalize a URL so the same posting always maps to the same string.

    Lowercases scheme and host, drops "www.", fragments, trailing slashes and
    tracking parameters (utm_*, ref, ...), and sorts the remaining query.
    """
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    if scheme == "http":
        scheme = "https"
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    )
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def job_id(url: str) -> str:
    """Short stable hash of the canonical URL (16 hex chars)."""
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()[:16]
