"""Himalayas (himalayas.app) public search API.

The API filters eligibility server-side: `country=Pakistan` returns jobs whose
location restrictions include Pakistan or are empty, and `worldwide=true` returns
jobs with no restriction. We run a short list of queries in both modes, two pages
each, and dedupe by guid.
"""

from __future__ import annotations

import logging
import time

import requests

from jobagent.models import Job
from jobagent.sources._util import as_tags, clean, format_salary, from_epoch, html_to_text

log = logging.getLogger("jobagent.himalayas")

API = "https://himalayas.app/jobs/api/search"
QUERIES = ("developer", "engineer", "junior", "automation", "QA", "support engineer", "react", "python")
SCOPES = ({"country": "Pakistan"}, {"worldwide": "true"})
PAGES = 2
PAGE_SIZE = 20
PAUSE = 0.3  # seconds between requests, to be polite


def _location(restrictions: tuple[str, ...]) -> str:
    if not restrictions:
        return "Worldwide"
    if len(restrictions) <= 3:
        return ", ".join(restrictions)
    if "Pakistan" in restrictions:
        return f"{len(restrictions)} countries incl. Pakistan"
    return f"{len(restrictions)} countries"


def parse_job(item: dict) -> Job | None:
    title = clean(item.get("title"))
    company = clean(item.get("companyName"))
    guid = clean(item.get("guid"))
    if not title or not guid:
        return None
    raw = item.get("locationRestrictions") or []
    restrictions = tuple(clean(r) for r in raw if isinstance(r, str) and r.strip())
    seniority = item.get("seniority") or []
    categories = item.get("categories") or []
    tags = as_tags([*(s for s in seniority if isinstance(s, str)), *(c for c in categories if isinstance(c, str))])
    description = html_to_text(item.get("description")) or clean(item.get("excerpt"))
    return Job(
        source="himalayas",
        url=guid,
        title=title,
        company=company,
        location=_location(restrictions),
        description=description,
        posted_at=from_epoch(item.get("pubDate")),
        salary=format_salary(item.get("minSalary"), item.get("maxSalary"), item.get("currency"), item.get("salaryPeriod")),
        tags=tags,
        apply_url=clean(item.get("applicationLink")),
        location_restrictions=restrictions,
        source_id=guid,
    )


def parse(payload: dict) -> list[Job]:
    """Jobs from one search response page. Malformed items are skipped."""
    items = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("himalayas: response has no jobs list")
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            job = parse_job(item)
        except Exception:  # one odd item must not sink the page
            job = None
        if job:
            jobs.append(job)
    return jobs


class HimalayasSource:
    name = "himalayas"
    label = "Himalayas"

    def __init__(self, queries: tuple[str, ...] = QUERIES, pages: int = PAGES, pause: float = PAUSE):
        self.queries = queries
        self.pages = pages
        self.pause = pause

    def fetch(self, session: requests.Session) -> list[Job]:
        by_guid: dict[str, Job] = {}
        ok = failed = 0
        for query in self.queries:
            for scope in SCOPES:
                for page in range(1, self.pages + 1):
                    params = {"q": query, **scope}
                    if page > 1:
                        params["page"] = str(page)
                    try:
                        resp = session.get(API, params=params)
                        resp.raise_for_status()
                        got = parse(resp.json())
                    except Exception as exc:
                        failed += 1
                        log.info("himalayas q=%s page=%d failed: %s", query, page, type(exc).__name__)
                        break
                    ok += 1
                    for job in got:
                        by_guid.setdefault(job.source_id, job)
                    if self.pause:
                        time.sleep(self.pause)
                    if len(got) < PAGE_SIZE:
                        break
        if ok == 0 and failed:
            raise RuntimeError("himalayas: every request failed")
        return list(by_guid.values())
