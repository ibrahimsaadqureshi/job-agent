"""Remote OK public API (remoteok.com/api).

Element 0 of the response is a legal notice, not a job. Their terms ask for a
link back and credit: `url` stays their job page, and the label is "Remote OK".
"""

from __future__ import annotations

import requests

from jobagent.models import Job
from jobagent.sources._util import as_tags, clean, format_salary, from_epoch, from_iso, html_to_text

API = "https://remoteok.com/api"


def parse_job(item: dict) -> Job | None:
    title = clean(item.get("position"))
    url = clean(item.get("url"))
    if not title or not url:
        return None
    return Job(
        source="remoteok",
        url=url,
        title=title,
        company=clean(item.get("company")),
        location=clean(item.get("location")),
        description=html_to_text(item.get("description")),
        posted_at=from_iso(item.get("date")) or from_epoch(item.get("epoch")),
        salary=format_salary(item.get("salary_min"), item.get("salary_max"), "USD", "year"),
        tags=as_tags(item.get("tags") or []),
        apply_url=clean(item.get("apply_url")),
        source_id=clean(item.get("id")),
    )


def parse(payload: list) -> list[Job]:
    """Jobs from the API response. The legal notice and malformed items are skipped."""
    if not isinstance(payload, list):
        raise ValueError("remoteok: response is not a list")
    jobs = []
    for item in payload:
        if not isinstance(item, dict) or "legal" in item:
            continue
        try:
            job = parse_job(item)
        except Exception:
            job = None
        if job:
            jobs.append(job)
    return jobs


class RemoteOkSource:
    name = "remoteok"
    label = "Remote OK"

    def fetch(self, session: requests.Session) -> list[Job]:
        resp = session.get(API)
        resp.raise_for_status()
        return parse(resp.json())
