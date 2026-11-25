from datetime import date

import pytest

from fakes import make_job
from jobagent.models import (
    SHEET_COLUMNS,
    Assessment,
    Candidate,
    Category,
    TrackerRow,
    Verdict,
    canonical_url,
    job_id,
)


@pytest.mark.parametrize(
    "a, b",
    [
        ("https://remoteok.com/remote-jobs/123", "http://www.RemoteOK.com/remote-jobs/123/"),
        ("https://x.io/jobs/1?utm_source=feed&utm_medium=rss", "https://x.io/jobs/1"),
        ("https://x.io/jobs/1?ref=hn#apply", "https://x.io/jobs/1"),
        ("https://x.io/jobs?b=2&a=1", "https://x.io/jobs?a=1&b=2"),
    ],
)
def test_canonical_url_equivalent(a, b):
    assert canonical_url(a) == canonical_url(b)
    assert job_id(a) == job_id(b)


def test_canonical_url_keeps_identifying_query():
    # HN comment links identify the posting by ?id=
    assert canonical_url("https://news.ycombinator.com/item?id=1") != canonical_url(
        "https://news.ycombinator.com/item?id=2"
    )


def test_job_id_is_short_and_stable():
    jid = job_id("https://jobs.example.com/1")
    assert len(jid) == 16
    assert jid == make_job(1).id


def test_tracker_row_matches_sheet_columns():
    job = make_job(1, salary="$50k")
    cand = Candidate(
        job=job,
        verdict=Verdict(keep=True, category=Category.STACK, location_rule="worldwide"),
        assessment=Assessment(job.id, 82, "strong React match", "Hi, ..."),
        also_on=("wwr",),
    )
    row = TrackerRow.from_candidate(cand, date(2026, 11, 25))
    values = row.as_list()
    assert len(values) == len(SHEET_COLUMNS)
    as_dict = dict(zip(SHEET_COLUMNS, values))
    assert as_dict["date"] == "2026-11-25"
    assert as_dict["source"] == "fake (+wwr)"
    assert as_dict["score"] == 82
    assert as_dict["status"] == "new"
    assert as_dict["category"] == "stack"
    assert as_dict["id"] == job.id


def test_tracker_row_unscored_has_blank_score():
    job = make_job(1)
    cand = Candidate(job=job, verdict=Verdict(keep=True, category=Category.TECH_ENTRY))
    values = dict(zip(SHEET_COLUMNS, TrackerRow.from_candidate(cand, date(2026, 11, 25)).as_list()))
    assert values["score"] == ""
    assert values["draft note"] == ""
