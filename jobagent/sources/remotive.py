"""Remotive public API (remotive.com/api/remote-jobs).

Small feed (about 15 jobs, delayed 24h). Their terms ask for a link back and
credit, so `url` stays their job page and the label is "Remotive".
"""

from __future__ import annotations

import requests

from jobagent.models import Job
from jobagent.sources._util import as_tags, clean, from_iso, html_to_text

API = "https://remotive.com/api/remote-jobs"


def parse_job(item: dict) -> Job | None:
    title = clean(item.get("title"))
    url = clean(item.get("url"))
    if not title or not url:
        return None
    return Job(
        source="remotive",
        url=url,
        title=title,
        company=clean(item.get("company_name")),
        location=clean(item.get("candidate_required_location")),
        description=html_to_text(item.get("description")),
        posted_at=from_iso(item.get("publication_date")),
        salary=clean(item.get("salary")),
        tags=as_tags(item.get("tags") or []),
        source_id=clean(item.get("id")),
    )


def parse(payload: dict) -> list[Job]:
    items = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("remotive: response has no jobs list")
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            job = parse_job(item)
        except Exception:
            job = None
        if job:
            jobs.append(job)
    return jobs


class RemotiveSource:
    name = "remotive"
    label = "Remotive"

    def fetch(self, session: requests.Session) -> list[Job]:
        resp = session.get(API)
        resp.raise_for_status()
        return parse(resp.json())
