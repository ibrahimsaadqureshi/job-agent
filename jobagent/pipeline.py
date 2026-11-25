"""The daily run: fetch -> filter -> dedupe -> score -> draft -> track -> digest.

Pure orchestration. Every external system arrives as an argument (see interfaces.py),
so this module is tested with fakes and never touches the network itself except
through the sources it is given.

Logging rule: log counts and source names only. Never log job descriptions,
profile text, drafts or secrets: GitHub Actions logs are public for public repos.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone

import requests

from jobagent import dedupe, filters
from jobagent.digest import build_digest
from jobagent.interfaces import Notifier, Scorer, Source, Tracker
from jobagent.models import Assessment, Candidate, Job, RunStats, TrackerRow, Verdict
from jobagent.net import make_session

log = logging.getLogger("jobagent")


@dataclass(frozen=True)
class RunOptions:
    threshold: int = 70
    digest_max_jobs: int = 12
    max_drafts: int = 12
    limit: int | None = None  # max jobs sent to the scorer this run
    sheet_url: str = ""
    # Also track jobs that got no score. Only `--local --no-llm` sets this, so cross-run
    # dedupe can be checked without an LLM; real runs leave unscored jobs for a retry.
    track_unscored: bool = False


@dataclass
class RunResult:
    stats: RunStats
    candidates: list[Candidate]  # new jobs this run, scored or not


def _newest_first(job: Job) -> tuple[int, float]:
    # Jobs without a date sort after dated ones.
    if job.posted_at is None:
        return (1, 0.0)
    return (0, -job.posted_at.timestamp())


def fetch_all(sources: list[Source], session: requests.Session, stats: RunStats) -> list[Job]:
    jobs: list[Job] = []
    for source in sources:
        try:
            got = source.fetch(session)
        except Exception as exc:  # one broken source must not stop the run
            stats.source_errors[source.name] = type(exc).__name__
            log.warning("source %s failed: %s", source.name, type(exc).__name__)
            continue
        stats.fetched[source.name] = len(got)
        log.info("source %s: %d jobs", source.name, len(got))
        jobs.extend(got)
    return jobs


def run(
    *,
    sources: list[Source],
    tracker: Tracker,
    notifier: Notifier,
    scorer: Scorer | None,
    profile: str,
    options: RunOptions,
    today: date | None = None,
    session: requests.Session | None = None,
) -> RunResult:
    stats = RunStats()
    today = today or datetime.now(timezone.utc).date()
    session = session or make_session()

    # 1. Fetch
    jobs = fetch_all(sources, session, stats)

    # 2. Filter
    kept: list[tuple[Job, Verdict]] = []
    dropped: Counter[str] = Counter()
    for job in jobs:
        verdict = filters.evaluate(job)
        if verdict.keep:
            kept.append((job, verdict))
        else:
            dropped[verdict.reason or "unspecified"] += 1
    stats.dropped = dict(dropped)
    stats.kept = len(kept)
    verdicts = {job.id: verdict for job, verdict in kept}

    # 3. Dedupe: within this run, then against everything already tracked
    unique = dedupe.dedupe_in_run([job for job, _ in kept])
    stats.duplicates_in_run = len(kept) - len(unique)
    seen = tracker.seen_ids()
    fresh = [(job, also) for job, also in unique if job.id not in seen]
    stats.already_seen = len(unique) - len(fresh)
    stats.new = len(fresh)
    fresh.sort(key=lambda pair: _newest_first(pair[0]))

    # 4. Score (newest first, capped by --limit). Unscored jobs are not tracked,
    #    so they are retried on the next run.
    to_score = [job for job, _ in fresh]
    if options.limit is not None:
        to_score = to_score[: options.limit]
    scores: dict[str, tuple[int, str]] = {}
    if scorer is not None and to_score:
        try:
            scores = scorer.score(to_score, profile)
        except Exception as exc:
            log.warning("scoring failed: %s", type(exc).__name__)
            scores = {}

    # 5. Draft notes for the best jobs at or above the threshold
    drafts: dict[str, str] = {}
    if scorer is not None:
        jobs_by_id = {job.id: job for job, _ in fresh}
        best = sorted(
            (job_id for job_id, (score, _) in scores.items() if score >= options.threshold and job_id in jobs_by_id),
            key=lambda job_id: scores[job_id][0],
            reverse=True,
        )[: options.max_drafts]
        for job_id in best:
            try:
                drafts[job_id] = scorer.draft(jobs_by_id[job_id], profile, scores[job_id][1])
            except Exception as exc:
                log.warning("draft failed: %s", type(exc).__name__)
    stats.drafted = len(drafts)

    candidates: list[Candidate] = []
    for job, also in fresh:
        result = scores.get(job.id)
        assessment = Assessment(job.id, result[0], result[1], drafts.get(job.id, "")) if result else None
        candidates.append(Candidate(job=job, verdict=verdicts[job.id], assessment=assessment, also_on=also))
    stats.scored = sum(1 for c in candidates if c.score is not None)
    stats.unscored = len(candidates) - stats.scored

    # 6. Track scored jobs (append-only)
    rows = [
        TrackerRow.from_candidate(c, today)
        for c in candidates
        if c.score is not None or options.track_unscored
    ]
    if rows:
        tracker.append(rows)
    stats.written = len(rows)

    # 7. Digest
    digest = build_digest(
        candidates,
        stats,
        run_date=today.isoformat(),
        threshold=options.threshold,
        max_jobs=options.digest_max_jobs,
        sheet_url=options.sheet_url,
    )
    notifier.send(digest)

    log.info(
        "run done: fetched=%d kept=%d dup=%d seen=%d new=%d scored=%d drafted=%d written=%d",
        stats.total_fetched,
        stats.kept,
        stats.duplicates_in_run,
        stats.already_seen,
        stats.new,
        stats.scored,
        stats.drafted,
        stats.written,
    )
    return RunResult(stats=stats, candidates=candidates)
