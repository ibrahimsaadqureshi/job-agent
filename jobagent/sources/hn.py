"""Hacker News "Ask HN: Who is hiring?" monthly thread, via the Algolia HN API.

Each top-level comment is one post whose first line is, by convention,
`Company | Role | Location | ...`. Comments are free text, so parsing is best effort:
the role is the first segment that reads like a job title ("See post" if none), and
the location is every segment that mentions REMOTE / ONSITE / HYBRID or a timezone.
"""

from __future__ import annotations

import html
import re

import requests

from jobagent.models import Job
from jobagent.sources._util import clean, from_epoch, from_iso, html_to_text

SEARCH = "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=5"
ITEM = "https://hn.algolia.com/api/v1/items/{id}"
THREAD_PREFIX = "Ask HN: Who is hiring?"
NO_ROLE = "See post"

_PARAGRAPH = re.compile(r"<p>|\n", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_HREF = re.compile(r'href="([^"]+)"', re.IGNORECASE)

_LOCATION_SEG = re.compile(
    r"\b(remote|onsite|on-site|on site|hybrid|in[- ]person|in[- ]office|wfh|utc|gmt|time ?zones?)\b",
    re.IGNORECASE,
)
_TYPE_SEG = re.compile(
    r"^\W*(full[- ]?time|part[- ]?time|contract(or)?|freelance|permanent|internships?|ft|pt|seed|"
    r"series [a-e]|visa( sponsorship)?|[\w\s,+&-]*\b(full[- ]?time|part[- ]?time)\b[\w\s,+&()/-]*)\W*$",
    re.IGNORECASE,
)
_URL_SEG = re.compile(r"https?://|www\.|\.(com|ai|io|co|dev|so|org|net)\b", re.IGNORECASE)
_SALARY_SEG = re.compile(r"[$€£]|\b\d+\s?k\b|\bsalary\b|\bequity\b", re.IGNORECASE)
_ROLE_WORDS = re.compile(
    r"\b(engineers?|engineering|developers?|programmers?|designers?|scientists?|architects?|analysts?|"
    r"admins?|administrators?|sre|devops|researchers?|consultants?|interns?|leads?|managers?|pms?|"
    r"directors?|head|cto|ciso|officer|specialists?|technicians?|writers?|support|qa|testers?|"
    r"positions|roles|openings|staff|founding|product|sales|marketing|account|recruiters?|ae|"
    r"operations|ops|associate|data|ml|ai)\b",
    re.IGNORECASE,
)


def _strip(fragment: str) -> str:
    return clean(_TAG.sub("", html.unescape(fragment)))


def header_line(text: str) -> str:
    """The `Company | Role | ...` line: the first of the first three paragraphs with a pipe."""
    paragraphs = [p for p in (_strip(p) for p in _PARAGRAPH.split(text)) if p]
    for p in paragraphs[:3]:
        if "|" in p:
            return p
    return paragraphs[0] if paragraphs else ""


def _short(segment: str, limit: int = 80) -> str:
    """A header segment cut before any run-on post text (some posts have no line break)."""
    if len(segment) <= limit:
        return segment
    close = segment.find(")")
    if 0 < close < limit:
        return segment[: close + 1]
    return segment[:limit].rsplit(" ", 1)[0]


def parse_header(line: str) -> tuple[str, str, str]:
    """(company, role, location) from a header line."""
    segments = [s.strip() for s in line.split("|") if s.strip()]
    if not segments:
        return "", NO_ROLE, ""
    if len(segments) == 1:
        company = re.split(r"\s+-\s+|\s+is\s+|,|\(", segments[0], maxsplit=1)[0].strip()[:60]
        return company, NO_ROLE, ""
    company = segments[0][:80]
    location = "; ".join(_short(s) for s in segments[1:] if _LOCATION_SEG.search(s))
    role = NO_ROLE
    for seg in segments[1:]:
        if _LOCATION_SEG.search(seg) or _TYPE_SEG.match(seg) or _URL_SEG.search(seg) or _SALARY_SEG.search(seg):
            continue
        if _ROLE_WORDS.search(seg):
            role = seg[:120]
            break
    return company, role, location


def parse_comment(comment: dict) -> Job | None:
    text = comment.get("text")
    cid = comment.get("id")
    if not text or not cid or comment.get("deleted") or comment.get("dead") or not comment.get("author"):
        return None
    company, role, location = parse_header(header_line(text))
    if not company:
        return None
    links = _HREF.findall(text)
    return Job(
        source="hn",
        url=f"https://news.ycombinator.com/item?id={cid}",
        title=role,
        company=company,
        location=location,
        description=html_to_text(text),
        posted_at=from_epoch(comment.get("created_at_i")) or from_iso(comment.get("created_at")),
        apply_url=html.unescape(links[0]) if links else "",
        source_id=str(cid),
    )


def pick_thread(search: dict) -> int | None:
    """Id of the newest "Who is hiring?" story in an Algolia search response."""
    hits = [h for h in search.get("hits", []) if str(h.get("title", "")).startswith(THREAD_PREFIX)]
    if not hits:
        return None
    newest = max(hits, key=lambda h: int(h.get("created_at_i") or 0))
    return int(newest.get("story_id") or newest["objectID"])


def parse(payload: dict) -> list[Job]:
    """Jobs from an Algolia items/<id> response: one per top-level comment."""
    children = payload.get("children") if isinstance(payload, dict) else None
    if not isinstance(children, list):
        raise ValueError("hn: thread has no children list")
    jobs = []
    for comment in children:
        if not isinstance(comment, dict):
            continue
        try:
            job = parse_comment(comment)
        except Exception:
            job = None
        if job:
            jobs.append(job)
    return jobs


class HnSource:
    name = "hn"
    label = "HN Who is hiring"

    def fetch(self, session: requests.Session) -> list[Job]:
        resp = session.get(SEARCH)
        resp.raise_for_status()
        thread = pick_thread(resp.json())
        if thread is None:
            raise RuntimeError("hn: no Who is hiring thread found")
        resp = session.get(ITEM.format(id=thread))
        resp.raise_for_status()
        return parse(resp.json())
