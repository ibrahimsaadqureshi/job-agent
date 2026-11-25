"""Each source's pure parser against a trimmed real response saved on 2026-11-25. No network."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jobagent import sources
from jobagent.interfaces import Source
from jobagent.sources import himalayas, hn, remoteok, remotive, wwr
from jobagent.sources._util import fix_mojibake, format_salary, html_to_text

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def by_title(jobs, title):
    return next(j for j in jobs if j.title == title)


# --- registry -----------------------------------------------------------------------


def test_registry_order_and_protocol():
    assert [s.name for s in sources.ALL_SOURCES] == ["himalayas", "wwr", "remoteok", "remotive", "hn"]
    for s in sources.ALL_SOURCES:
        assert isinstance(s, Source)
        assert s.label
    assert [s.name for s in sources.get_sources(["hn", "wwr"])] == ["wwr", "hn"]


# --- Himalayas ------------------------------------------------------------------------


def test_himalayas_parse():
    jobs = himalayas.parse(load_json("himalayas.json"))
    assert len(jobs) == 8
    assert all(j.source == "himalayas" and j.url.startswith("https://himalayas.app/") for j in jobs)

    pk = by_title(jobs, "Senior React Native & React Engineer PK")
    assert pk.company == "Wizdaa"
    assert pk.location == "Pakistan"
    assert pk.location_restrictions == ("Pakistan",)
    assert pk.posted_at == datetime(2026, 11, 19, 18, 7, 3, tzinfo=timezone.utc)
    assert "senior" in pk.tags
    assert "<" not in pk.description and pk.description

    many = next(j for j in jobs if j.company.startswith("PradeepIT"))
    assert many.location.endswith("countries incl. Pakistan")
    assert "Pakistan" in many.location_restrictions

    canonical = next(j for j in jobs if j.company == "Canonical")
    assert canonical.location == "Worldwide"
    assert canonical.location_restrictions == ()
    assert canonical.salary == "$48k-$70k / year"
    assert canonical.apply_url

    hourly = next(j for j in jobs if j.company == "Motu Novu LLC")
    assert hourly.salary == "$35-$50 / hour"


def test_himalayas_skips_malformed_and_rejects_bad_payload():
    payload = {"jobs": [{"title": "", "guid": "x"}, "junk", {"title": "Dev", "companyName": "A", "guid": "https://h/1"}]}
    assert [j.title for j in himalayas.parse(payload)] == ["Dev"]
    with pytest.raises(ValueError):
        himalayas.parse({"error": "nope"})


class _Resp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class _Session:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _Resp(self.data)


def test_himalayas_fetch_dedupes_by_guid_and_stops_on_short_page():
    session = _Session(load_json("himalayas.json"))  # 8 jobs: a short page, so one page per query
    src = himalayas.HimalayasSource(queries=("react", "python"), pause=0)
    jobs = src.fetch(session)
    assert len(jobs) == 8  # the same 8 every time, deduped
    assert len(session.calls) == 4  # 2 queries x 2 scopes, no second page
    assert {tuple(sorted(p)) for _, p in session.calls} == {("country", "q"), ("q", "worldwide")}


# --- We Work Remotely -----------------------------------------------------------------


def test_wwr_parse():
    jobs = wwr.parse((FIXTURES / "wwr.rss").read_bytes())
    assert len(jobs) == 11  # the empty item at the end is skipped
    first = jobs[0]
    assert (first.company, first.title, first.location) == ("GitLab", "Senior TA Operations Specialist", "USA Only")
    assert first.posted_at == datetime(2026, 11, 24, 17, 1, 17, tzinfo=timezone.utc)
    assert first.url.startswith("https://weworkremotely.com/remote-jobs/")

    poland = by_title(jobs, "Backend Engineer, Trusted Agentic Development")
    assert poland.location == "Anywhere in the World (Poland)"
    assert poland.location_restrictions == ("Poland",)

    cockroach = by_title(jobs, "Member of Technical Staff (Storage)")
    assert cockroach.location_restrictions == ("United States of America", "Canada")

    customer_io = next(j for j in jobs if j.company == "Customer.io")
    assert customer_io.title == "Senior Software Engineer, Backend"
    assert customer_io.tags == ("full stack programming",)
    assert "Headquarters" in customer_io.description and "&lt;" not in customer_io.description


# --- Remote OK ------------------------------------------------------------------------


def test_remoteok_parse_skips_legal_notice():
    jobs = remoteok.parse(load_json("remoteok.json"))
    assert len(jobs) == 10
    gitlab = jobs[0]
    assert gitlab.title == "Senior Manager, Enterprise Application Development Engineering"
    assert gitlab.location == "US Only"
    assert gitlab.url.startswith("https://remoteOK.com/remote-jobs/")  # link back to Remote OK
    assert gitlab.salary == ""  # 0/0 means not listed
    assert gitlab.tags == ("devops",)
    assert gitlab.source_id == "1138079"

    thrive = next(j for j in jobs if j.company == "Thrive")
    assert thrive.location == ""
    assert thrive.salary == "$128k / year"

    munich = next(j for j in jobs if j.company == "Wemolo")
    assert munich.location == "München"  # mojibake repaired


def test_remoteok_label_credits_them():
    assert remoteok.RemoteOkSource.label == "Remote OK"
    with pytest.raises(ValueError):
        remoteok.parse({"not": "a list"})


# --- Remotive -------------------------------------------------------------------------


def test_remotive_parse():
    jobs = remotive.parse(load_json("remotive.json"))
    assert len(jobs) == 8
    rails = by_title(jobs, "Tech Lead Full-Stack Rails Engineer")
    assert rails.company == "Mitre Media"
    assert rails.location == "USA, Canada, USA timezones"
    assert rails.salary == "$170k - $200k"
    assert rails.posted_at == datetime(2026, 11, 14, 20, 33, 53, tzinfo=timezone.utc)
    assert rails.url.startswith("https://remotive.com/")
    assert "docker" in rails.tags
    assert remotive.RemotiveSource.label == "Remotive"


# --- HN Who is hiring -----------------------------------------------------------------


def test_hn_pick_thread():
    assert hn.pick_thread(load_json("hn_search.json")) == 50338728
    assert hn.pick_thread({"hits": [{"title": "Ask HN: Who wants to be hired?", "objectID": "1"}]}) is None


def test_hn_parse():
    jobs = hn.parse(load_json("hn_thread.json"))
    assert len(jobs) == 14  # the deleted comment is skipped
    sa = jobs[0]
    assert sa.company == "Simple Analytics"
    assert sa.title == "DevOps Engineer"
    assert sa.location == "REMOTE (worldwide, any timezone)"
    assert sa.url == "https://news.ycombinator.com/item?id=50338732"
    assert sa.apply_url == "https://www.simpleanalytics.com/jobs/devops"
    assert sa.description.startswith("Simple Analytics | DevOps Engineer")

    shepherd = next(j for j in jobs if j.company.startswith("Shepherd"))
    assert shepherd.title == hn.NO_ROLE
    assert shepherd.location == "ONSITE"

    posthog = next(j for j in jobs if j.company == "PostHog")
    assert posthog.location == "REMOTE (all remote); Hiring GMT-8 to GMT+2"

    mixrank = next(j for j in jobs if j.company.startswith("MixRank"))
    assert mixrank.location.startswith("100% Remote (Global)")
    assert len(mixrank.location) < 120  # run-on post text is cut off


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Acme | Senior Backend Engineer | REMOTE (Worldwide) | Full-time", ("Acme", "Senior Backend Engineer", "REMOTE (Worldwide)")),
        ("Voluntas | Remote | Full Time | Software Engineer", ("Voluntas", "Software Engineer", "Remote")),
        ("Pond AI | San Francisco | Onsite | https://joinpond.ai", ("Pond AI", "See post", "Onsite")),
        ("DuckDuckGo - we are hiring", ("DuckDuckGo", "See post", "")),
        ("Fredrin | GTM Engineer | REMOTE (US) | Full-time | $130k + equity", ("Fredrin", "GTM Engineer", "REMOTE (US)")),
    ],
)
def test_hn_parse_header(line, expected):
    assert hn.parse_header(line) == expected


def test_hn_header_skips_update_paragraph():
    text = "UPDATE: roles filled.<p>Bridge | AI Consultant | REMOTE (US)<p>More text"
    assert hn.header_line(text) == "Bridge | AI Consultant | REMOTE (US)"


# --- helpers --------------------------------------------------------------------------


def test_helpers():
    text = html_to_text("<p>Hello <b>world</b></p><p>Line&#x2F;two<br>three</p>")
    assert "<" not in text and "world" in text and "Line/two" in text and "three" in text
    assert html_to_text(None) == ""
    assert fix_mojibake("MÃ¼nchen") == "München"
    assert fix_mojibake("plain") == "plain"
    assert format_salary(0, 0) == ""
    assert format_salary(None, None, None, None) == ""
    assert format_salary(60000, 80000, "USD", "annual") == "$60k-$80k / year"
    assert format_salary(5000, 5000, "EUR", "monthly") == "€5k / month"
    assert format_salary(2500, 0, "PKR", "") == "PKR 2.5k"
