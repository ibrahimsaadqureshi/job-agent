"""Choose what goes in the daily digest, and render it as plain text.

Channel-specific rendering (Slack Block Kit) lives with the notifier (Lane D, M5).
"""

from __future__ import annotations

from jobagent.interfaces import Digest
from jobagent.models import Candidate, Category, RunStats

SECTION_TITLES: dict[Category, str] = {
    Category.STACK: "My stack",
    Category.AUTOMATION: "Automation",
    Category.TECH_ENTRY: "Starter tech roles",
}


def build_digest(
    candidates: list[Candidate],
    stats: RunStats,
    *,
    run_date: str,
    threshold: int,
    max_jobs: int,
    sheet_url: str = "",
) -> Digest:
    """Top new jobs at or above the threshold, best first, grouped by category.

    max_jobs caps the whole digest, not each section.
    """
    eligible = [c for c in candidates if c.score is not None and c.score >= threshold]
    eligible.sort(key=lambda c: c.score or 0, reverse=True)
    chosen = eligible[:max_jobs]

    sections: dict[str, list[Candidate]] = {}
    for category, title in SECTION_TITLES.items():
        jobs = [c for c in chosen if c.verdict.category == category]
        if jobs:
            sections[title] = jobs
    return Digest(
        run_date=run_date,
        sections=sections,
        stats=stats,
        sheet_url=sheet_url,
        threshold=threshold,
    )


def render_text(digest: Digest) -> str:
    """Plain-text digest, used by the console notifier and as a Slack fallback."""
    s = digest.stats
    lines = [f"Job digest {digest.run_date}"]
    if digest.is_empty:
        lines.append(
            f"Nothing new at {digest.threshold}+ today "
            f"({s.total_fetched} fetched, {s.kept} passed filters, {s.new} new, {s.scored} scored)."
        )
    for title, cands in digest.sections.items():
        lines.append("")
        lines.append(f"== {title} ==")
        for c in cands:
            j = c.job
            salary = f" | {j.salary}" if j.salary else ""
            lines.append(f"[{c.score}] {j.title} at {j.company}{salary}")
            if c.assessment and c.assessment.reason:
                lines.append(f"     {c.assessment.reason}")
            lines.append(f"     via {j.source}: {j.url}")
    if not digest.is_empty:
        lines.append("")
        lines.append(f"{s.total_fetched} fetched, {s.kept} passed filters, {s.new} new, {s.scored} scored.")
    if s.source_errors:
        lines.append("Sources with errors: " + ", ".join(sorted(s.source_errors)))
    if digest.sheet_url:
        lines.append(f"Drafts and full list: {digest.sheet_url}")
    return "\n".join(lines)
