"""In-run dedupe: the same posting listed on several boards (or twice on one) in one run.

Two jobs are the same when they share an id (same canonical URL) or a fingerprint:
normalized company + normalized title. Cross-run dedupe is not here: the pipeline
compares job ids with Tracker.seen_ids().
"""

from __future__ import annotations

import re
import unicodedata

from jobagent.models import Job

_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]|\{[^}]*\}")
_NON_WORD = re.compile(r"[^a-z0-9+#]+")
_COMPANY_SUFFIXES = frozenset(
    {
        "inc", "incorporated", "llc", "ltd", "limited", "plc", "corp", "corporation", "co", "company",
        "gmbh", "ag", "sa", "sas", "srl", "bv", "nv", "oy", "ab", "as", "pty", "pvt", "private",
        "lp", "llp", "kg", "spa", "sl", "group", "holdings", "technologies", "technology",
    }
)
_TITLE_NOISE = frozenset({"remote", "fully", "100", "anywhere", "worldwide", "hybrid", "wfh"})
_TITLE_ABBREVIATIONS = {"sr": "senior", "jr": "junior", "eng": "engineer", "dev": "developer", "fe": "frontend", "be": "backend"}


def _ascii_words(text: str) -> list[str]:
    """Lowercase ASCII words: accents folded, emoji and punctuation dropped."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("full-stack", "fullstack").replace("full stack", "fullstack")
    text = text.replace("front-end", "frontend").replace("front end", "frontend")
    text = text.replace("back-end", "backend").replace("back end", "backend")
    return [w for w in _NON_WORD.split(text) if w]


def normalize_company(company: str) -> str:
    words = _ascii_words(_BRACKETS.sub(" ", company))
    while len(words) > 1 and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words)


def normalize_title(title: str) -> str:
    # Drop bracketed notes ("(Remote)", "[Contract]") and anything after " - Remote" style dashes.
    title = _BRACKETS.sub(" ", title)
    words = [_TITLE_ABBREVIATIONS.get(w, w) for w in _ascii_words(title)]
    return " ".join(w for w in words if w not in _TITLE_NOISE)


def fingerprint(job: Job) -> str | None:
    """company|title key, or None when either part is missing (those match on id only)."""
    company, title = normalize_company(job.company), normalize_title(job.title)
    if not company or not title or job.title.strip() == "See post":
        return None
    return f"{company}|{title}"


def dedupe_in_run(jobs: list[Job]) -> list[tuple[Job, tuple[str, ...]]]:
    """Collapse duplicates, keeping the first occurrence (sources are fetched in priority order).

    Returns (kept_job, other_sources_that_listed_it) pairs, in input order.
    """
    kept: list[Job] = []
    also_on: list[list[str]] = []
    index: dict[str, int] = {}  # id or fingerprint -> position in kept
    for job in jobs:
        keys = [f"id:{job.id}"]
        fp = fingerprint(job)
        if fp:
            keys.append(f"fp:{fp}")
        hit = next((index[k] for k in keys if k in index), None)
        if hit is not None:
            if job.source != kept[hit].source and job.source not in also_on[hit]:
                also_on[hit].append(job.source)
            for k in keys:
                index.setdefault(k, hit)
            continue
        for k in keys:
            index[k] = len(kept)
        kept.append(job)
        also_on.append([])
    return [(job, tuple(others)) for job, others in zip(kept, also_on)]
