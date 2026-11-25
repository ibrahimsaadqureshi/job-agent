"""We Work Remotely RSS feeds: the all-jobs feed plus the programming and DevOps categories.

Item titles are "Company: Role". `<region>` is the broad eligibility ("Anywhere in
the World", "USA Only"); `<country>` optionally lists the allowed countries with
flag emoji ("🇺🇸 United States of America and 🇨🇦 Canada").
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import requests

from jobagent.models import Job
from jobagent.sources._util import as_tags, clean, from_rfc822, html_to_text

log = logging.getLogger("jobagent.wwr")

FEEDS = (
    "https://weworkremotely.com/remote-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
)

_FLAGS = re.compile("[\U0001F1E6-\U0001F1FF]")
_SPLIT = re.compile(r",\s*(?:and\s+)?|\s+and\s+")


def _countries(text: str) -> tuple[str, ...]:
    text = _FLAGS.sub("", text)
    return tuple(c.strip() for c in _SPLIT.split(text) if c.strip())


def parse_item(item: ET.Element) -> Job | None:
    raw_title = clean(item.findtext("title"))
    link = clean(item.findtext("link")) or clean(item.findtext("guid"))
    if not raw_title or not link:
        return None
    company, sep, role = raw_title.partition(": ")
    if not sep:
        company, role = "", raw_title
    region = clean(item.findtext("region"))
    countries = _countries(clean(item.findtext("country")))
    location = region
    if countries:
        location = f"{region} ({', '.join(countries)})" if region else ", ".join(countries)
    tags = as_tags([clean(item.findtext("category")), *as_tags(clean(item.findtext("skills")))])
    return Job(
        source="wwr",
        url=link,
        title=role.strip(),
        company=company.strip(),
        location=location,
        description=html_to_text(item.findtext("description")),
        posted_at=from_rfc822(item.findtext("pubDate")),
        tags=tags,
        location_restrictions=countries,
        source_id=clean(item.findtext("guid")) or link,
    )


def parse(payload: str | bytes) -> list[Job]:
    """Jobs from one RSS document. Malformed items are skipped."""
    root = ET.fromstring(payload)
    jobs = []
    for item in root.iter("item"):
        try:
            job = parse_item(item)
        except Exception:
            job = None
        if job:
            jobs.append(job)
    return jobs


class WwrSource:
    name = "wwr"
    label = "We Work Remotely"

    def __init__(self, feeds: tuple[str, ...] = FEEDS):
        self.feeds = feeds

    def fetch(self, session: requests.Session) -> list[Job]:
        by_url: dict[str, Job] = {}
        ok = 0
        for feed in self.feeds:
            try:
                resp = session.get(feed)
                resp.raise_for_status()
                got = parse(resp.content)
            except Exception as exc:
                log.info("wwr feed %s failed: %s", feed, type(exc).__name__)
                continue
            ok += 1
            for job in got:
                by_url.setdefault(job.id, job)
        if ok == 0:
            raise RuntimeError("wwr: every feed failed")
        return list(by_url.values())
