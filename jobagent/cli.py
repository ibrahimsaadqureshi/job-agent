"""Command line entry point: `python -m jobagent <command>`.

Run modes:
  run --dry-run   fetch, filter, dedupe against the local state, score; print rows and
                  digest; write nothing, send nothing.
  run --local     like dry-run, but records rows in ~/.config/job-agent/state/ so a second run dedupes.
  run             production: Google Sheet + Slack (needs secrets; arrives in M4/M5).
"""

from __future__ import annotations

import argparse
import logging
import sys

from jobagent import sources as source_registry
from jobagent.config import STATE_DIR, Settings, load_settings
from jobagent.interfaces import Notifier, Scorer, Tracker
from jobagent.local import ConsoleNotifier, LocalTracker
from jobagent.models import Candidate
from jobagent.pipeline import RunOptions, run


class SetupError(RuntimeError):
    """A missing secret or unbuilt component. Message is safe to show and log."""


def build_scorer(settings: Settings, no_llm: bool) -> Scorer | None:
    if no_llm:
        return None
    raise SetupError("LLM scoring is not built yet (milestone M3). Use --no-llm for now.")


def build_tracker(settings: Settings, mode: str) -> Tracker:
    if mode in ("dry-run", "local"):
        return LocalTracker(STATE_DIR, persist=(mode == "local"))
    raise SetupError("The Google Sheet tracker is not built yet (M4). Use --dry-run or --local.")


def build_notifier(settings: Settings, mode: str) -> Notifier:
    if mode in ("dry-run", "local"):
        return ConsoleNotifier()
    raise SetupError("The Slack notifier is not built yet (M5). Use --dry-run or --local.")


def load_profile(settings: Settings, no_llm: bool) -> str:
    """Contact-stripped profile text. Real loader (resume PDF / secret) arrives in M3."""
    return "" if no_llm else settings.candidate_profile


def print_preview(candidates: list[Candidate], limit: int = 40) -> None:
    if not candidates:
        print("No new jobs.")
        return
    print(f"{'score':>5}  {'category':<10}  {'location':<11}  {'source':<9}  company / title")
    shown = sorted(candidates, key=lambda c: (c.score is None, -(c.score or 0)))
    for c in shown[:limit]:
        score = "-" if c.score is None else str(c.score)
        category = c.verdict.category.value if c.verdict.category else ""
        print(
            f"{score:>5}  {category:<10}  {c.verdict.location_rule[:11]:<11}  "
            f"{c.job.source[:9]:<9}  {c.job.company[:28]} / {c.job.title[:60]}"
        )
    if len(shown) > limit:
        print(f"... and {len(shown) - limit} more")


def cmd_run(args: argparse.Namespace) -> int:
    settings = load_settings()
    mode = "dry-run" if args.dry_run else "local" if args.local else "production"
    try:
        sources = source_registry.get_sources(args.sources.split(",") if args.sources else None)
        scorer = build_scorer(settings, args.no_llm)
        tracker = build_tracker(settings, mode)
        notifier = build_notifier(settings, mode)
    except (SetupError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"mode={mode} sources={len(sources)} llm={'off' if scorer is None else settings.llm_provider}")
    result = run(
        sources=sources,
        tracker=tracker,
        notifier=notifier,
        scorer=scorer,
        profile=load_profile(settings, args.no_llm),
        options=RunOptions(
            threshold=settings.score_threshold,
            digest_max_jobs=settings.digest_max_jobs,
            max_drafts=settings.max_drafts_per_run,
            limit=args.limit,
            sheet_url=settings.sheet_url if mode == "production" else "",
            track_unscored=(mode == "local" and scorer is None),
        ),
    )
    if mode != "production":
        print_preview(result.candidates)
    s = result.stats
    if s.fetched:
        print("per source: " + ", ".join(f"{k}={v}" for k, v in s.fetched.items()))
    print(
        f"fetched={s.total_fetched} kept={s.kept} duplicates={s.duplicates_in_run} "
        f"already_seen={s.already_seen} new={s.new} scored={s.scored} drafted={s.drafted} written={s.written}"
    )
    if s.dropped:
        print("dropped: " + ", ".join(f"{k}={v}" for k, v in sorted(s.dropped.items(), key=lambda kv: -kv[1])))
    if s.source_errors:
        print("source errors: " + ", ".join(f"{k} ({v})" for k, v in s.source_errors.items()))
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    srcs = source_registry.get_sources()
    if not srcs:
        print("No sources registered yet (they arrive in M1).")
    for s in srcs:
        print(f"{s.name:<10} {s.label}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobagent", description="Daily remote-job pipeline.")
    parser.add_argument("-v", "--verbose", action="store_true", help="log progress to stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run the pipeline once")
    mode = p_run.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print rows and digest; write and send nothing")
    mode.add_argument("--local", action="store_true", help="record rows in local state instead of the Sheet")
    p_run.add_argument("--no-llm", action="store_true", help="skip scoring and drafting (zero LLM cost)")
    p_run.add_argument("--limit", type=int, default=None, metavar="N", help="score at most N jobs this run")
    p_run.add_argument("--sources", default="", metavar="A,B", help="only these sources (comma-separated)")
    p_run.set_defaults(func=cmd_run)

    p_src = sub.add_parser("sources", help="list registered sources")
    p_src.set_defaults(func=cmd_sources)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)
