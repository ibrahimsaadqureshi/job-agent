"""Command line entry point: `python -m jobagent <command>`.

Run modes:
  run --dry-run   fetch, filter, dedupe against the local state, score; print rows and
                  digest; write nothing, send nothing.
  run --local     like dry-run, but records rows in ~/.config/job-agent/state/ so a second run dedupes.
  run             production: Google Sheet + Slack. A crash posts a short failure notice to
                  Slack (exception type only) and exits non-zero.
  setup-sheet     one-time look for the Sheet's Jobs tab (safe to run again).
  profile         print the contact-stripped profile, for the CANDIDATE_PROFILE secret.

Logs and printed output are counts only: in GitHub Actions they are public.
"""

from __future__ import annotations

import argparse
import logging
import sys

from jobagent import sources as source_registry
from jobagent.config import STATE_DIR, Settings, load_settings
from jobagent import profile as profile_mod
from jobagent.interfaces import Notifier, Scorer, Tracker
from jobagent.llm import ProviderChain, build_providers
from jobagent.local import ConsoleNotifier, LocalTracker
from jobagent.models import Candidate
from jobagent.net import make_session
from jobagent.pipeline import RunOptions, run
from jobagent.scorer import LLMScorer


class SetupError(RuntimeError):
    """A missing secret or unbuilt component. Message is safe to show and log."""


# Settings field -> the env var / GitHub secret the owner sets.
ENV_NAMES = {
    "google_service_account_json": "GOOGLE_SERVICE_ACCOUNT_JSON",
    "sheet_id": "SHEET_ID",
    "slack_webhook_url": "SLACK_WEBHOOK_URL",
}
SHEET_SETTINGS = ("google_service_account_json", "sheet_id")
PRODUCTION_SETTINGS = (*SHEET_SETTINGS, "slack_webhook_url")


def require(settings: Settings, names: tuple[str, ...], what: str) -> None:
    missing = [ENV_NAMES[n] for n in settings.missing(*names)]
    if missing:
        raise SetupError(
            f"Missing {', '.join(missing)} for {what}. Locally, put them in ~/.config/job-agent/.env; "
            "in GitHub Actions, add them as repository secrets."
        )


def build_scorer(settings: Settings, no_llm: bool) -> Scorer | None:
    if no_llm:
        return None
    providers = build_providers(settings, make_session())
    if not providers:
        raise SetupError(
            "No LLM configured: put GEMINI_API_KEY in ~/.config/job-agent/.env, or use --no-llm."
        )
    return LLMScorer(
        ProviderChain(providers),
        batch_size=settings.score_batch_size,
        description_chars=settings.description_chars,
    )


def build_tracker(settings: Settings, mode: str) -> Tracker:
    if mode in ("dry-run", "local"):
        return LocalTracker(STATE_DIR, persist=(mode == "local"))
    require(settings, SHEET_SETTINGS, "the Google Sheet")
    from jobagent.sheet import SheetError, SheetTracker

    try:
        return SheetTracker.from_settings(settings)
    except SheetError as exc:
        raise SetupError(str(exc)) from None


def build_notifier(settings: Settings, mode: str) -> Notifier:
    if mode in ("dry-run", "local"):
        return ConsoleNotifier()
    require(settings, ("slack_webhook_url",), "the Slack digest")
    from jobagent.slack import SlackNotifier

    labels = {s.name: s.label for s in source_registry.ALL_SOURCES}
    return SlackNotifier(settings.slack_webhook_url, labels=labels)


def notify_failure(notifier: Notifier | None, message: str) -> None:
    """Best effort: a broken Slack must not hide the original error."""
    if notifier is None:
        return
    try:
        notifier.send_failure(message)
    except Exception as exc:
        print(f"error: the failure notice could not be sent either ({type(exc).__name__})", file=sys.stderr)


def safe_detail(exc: BaseException) -> str:
    """Our own error types carry owner-friendly messages with no secrets; others don't."""
    from jobagent.slack import SlackError

    safe: tuple[type[BaseException], ...] = (SetupError, SlackError)
    try:
        from jobagent.sheet import SheetError

        safe = (*safe, SheetError)
    except ImportError:
        pass
    return f": {exc}" if isinstance(exc, safe) else ""


def load_profile(settings: Settings, no_llm: bool) -> str:
    """Contact-stripped profile text: CANDIDATE_PROFILE if set, else the resume PDF."""
    if no_llm:
        return ""
    try:
        return profile_mod.load_profile(settings)
    except profile_mod.ProfileError as exc:
        raise SetupError(str(exc)) from exc


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


def print_assessments(candidates: list[Candidate], limit: int = 40) -> None:
    """Local preview only: reasons and drafts never go to logs."""
    scored = sorted((c for c in candidates if c.score is not None), key=lambda c: -(c.score or 0))
    if not scored:
        return
    print()
    print("Scores and reasons:")
    for c in scored[:limit]:
        print(f"  {c.score:>3}  {c.job.company[:28]} / {c.job.title[:60]}")
        print(f"       {c.assessment.reason}")
    drafted = [c for c in scored if c.assessment.draft]
    for c in drafted:
        print()
        print(f"Draft for {c.job.company} / {c.job.title} ({c.score}):")
        print(c.assessment.draft)


def cmd_run(args: argparse.Namespace) -> int:
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    mode = "dry-run" if args.dry_run else "local" if args.local else "production"
    notifier: Notifier | None = None
    try:
        if mode == "production":
            require(settings, PRODUCTION_SETTINGS, "a production run")
        notifier = build_notifier(settings, mode)
        sources = source_registry.get_sources(args.sources.split(",") if args.sources else None)
        scorer = build_scorer(settings, args.no_llm)
        tracker = build_tracker(settings, mode)
        profile = load_profile(settings, args.no_llm)
    except (SetupError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if mode == "production":
            notify_failure(notifier, type(exc).__name__)
        return 2

    llm = "off" if scorer is None else ">".join(getattr(getattr(scorer, "chain", None), "names", [settings.llm_provider]))
    limit = args.limit if args.limit is not None else (None if scorer is None else settings.max_scored_per_run)
    print(f"mode={mode} sources={len(sources)} llm={llm}")
    try:
        result = _run(args, settings, mode, sources, scorer, tracker, notifier, profile, limit)
    except Exception as exc:
        if mode != "production":
            raise  # local runs keep the traceback for debugging
        print(f"error: run failed ({type(exc).__name__}){safe_detail(exc)}", file=sys.stderr)
        notify_failure(notifier, type(exc).__name__)
        return 1
    report(result, mode)
    return 0


def _run(args, settings, mode, sources, scorer, tracker, notifier, profile, limit):
    return run(
        sources=sources,
        tracker=tracker,
        notifier=notifier,
        scorer=scorer,
        profile=profile,
        options=RunOptions(
            threshold=settings.score_threshold,
            digest_max_jobs=settings.digest_max_jobs,
            max_drafts=settings.max_drafts_per_run,
            limit=limit,
            sheet_url=settings.sheet_url if mode == "production" else "",
            track_unscored=(mode == "local" and scorer is None),
        ),
    )


def report(result, mode: str) -> None:
    if mode != "production":
        print_preview(result.candidates)
        print_assessments(result.candidates)
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


def cmd_setup_sheet(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        require(settings, SHEET_SETTINGS, "the Google Sheet")
        from jobagent import sheet
    except SetupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ImportError:
        print("error: the Sheet libraries aren't installed: pip install -e '.[sheets]'", file=sys.stderr)
        return 2
    try:
        spreadsheet = sheet.open_spreadsheet(settings.google_service_account_json, settings.sheet_id)
        sheet.setup_sheet(spreadsheet)
    except sheet.SheetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        detail = type(exc).__name__ + (f" {code}" if code else "")
        print(f"error: Google Sheets request failed ({detail})", file=sys.stderr)
        return 1
    print(
        f"The {sheet.TAB_NAME} tab is ready: bold frozen header, column widths, wrapped reason and "
        "draft note, hidden id column, score colours (70+ green, 50-69 yellow), a status dropdown "
        "and a filter row."
    )
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        text = profile_mod.load_profile(settings)
    except profile_mod.ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        "Contact details stripped. Read it once, then paste everything below into the "
        "CANDIDATE_PROFILE secret.",
        file=sys.stderr,
    )
    print(text)
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
    p_run.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="score at most N jobs this run (default MAX_SCORED_PER_RUN, 200)"
    )
    p_run.add_argument("--sources", default="", metavar="A,B", help="only these sources (comma-separated)")
    p_run.set_defaults(func=cmd_run)

    p_setup = sub.add_parser("setup-sheet", help="one-time formatting of the Sheet's Jobs tab (safe to repeat)")
    p_setup.set_defaults(func=cmd_setup_sheet)

    p_prof = sub.add_parser("profile", help="print the contact-stripped profile for the CANDIDATE_PROFILE secret")
    p_prof.set_defaults(func=cmd_profile)

    p_src = sub.add_parser("sources", help="list registered sources")
    p_src.set_defaults(func=cmd_sources)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # Third-party request logs can include URLs (webhook path, Sheet id): keep them quiet.
    for name in ("urllib3", "requests", "google", "gspread"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return args.func(args)
