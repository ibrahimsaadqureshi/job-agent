"""In-run dedupe: same id, or same normalized company + title."""

from __future__ import annotations

import pytest

from jobagent.dedupe import dedupe_in_run, fingerprint, normalize_company, normalize_title
from fakes import make_job


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Hivex", "hivex"),
        ("Gusto, Inc.", "gusto"),
        ("EdgeQ Technologies Private Limited", "edgeq"),
        ("Motu Novu LLC", "motu novu"),
        ("MixRank (YC S11)", "mixrank"),
        ("Lemon.io", "lemon io"),
        ("Proxify AB", "proxify"),
        ("Société Générale", "societe generale"),
        ("Group", "group"),  # never strip a name down to nothing
    ],
)
def test_normalize_company(raw, expected):
    assert normalize_company(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Senior Full-Stack Developer", "senior fullstack developer"),
        ("Sr. Full Stack Developer (Remote)", "senior fullstack developer"),
        ("Senior Fullstack Developer - REMOTE", "senior fullstack developer"),
        ("🌍 Front-End Developer [Contract]", "frontend developer"),
        ("Front End Developer (Flex-Time) (Remote/Global)", "frontend developer"),
        ("C++ Systems Engineer", "c++ systems engineer"),
        ("Back-end Engineer", "backend engineer"),
    ],
)
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


def test_fingerprint_needs_company_and_real_title():
    assert fingerprint(make_job(company="Acme", title="Dev")) == "acme|developer"
    assert fingerprint(make_job(company="", title="Developer")) is None
    assert fingerprint(make_job(company="Acme", title="See post")) is None


def test_cross_source_duplicate_first_source_wins():
    him = make_job(1, source="himalayas", company="Elvoro Ltd", title="AI Creative Engineer (Social Media)")
    wwr = make_job(2, source="wwr", company="Elvoro", title="AI Creative Engineer")
    rok = make_job(3, source="remoteok", company="ELVORO", title="AI Creative Engineer - Remote")
    out = dedupe_in_run([him, wwr, rok])
    assert out == [(him, ("wwr", "remoteok"))]


def test_same_url_collapses_even_with_different_titles():
    a = make_job(1, source="wwr", title="Backend Engineer")
    b = make_job(1, source="remoteok", title="Back-end Engineer II")
    assert dedupe_in_run([a, b]) == [(a, ("remoteok",))]


def test_same_source_repost_collapses_without_also_on():
    a = make_job(1, source="wwr", company="Wrike", title="Staff Software Engineer")
    b = make_job(2, source="wwr", company="Wrike", title="Staff Software Engineer")
    assert dedupe_in_run([a, b]) == [(a, ())]


def test_different_jobs_stay_apart_in_input_order():
    jobs = [
        make_job(1, company="Acme", title="Frontend Engineer"),
        make_job(2, company="Acme", title="Backend Engineer"),
        make_job(3, company="Other", title="Frontend Engineer"),
        make_job(4, company="", title="Frontend Engineer"),
        make_job(5, company="", title="Frontend Engineer"),  # no company: matched on id only
    ]
    out = dedupe_in_run(jobs)
    assert [j.url for j, _ in out] == [j.url for j in jobs]
    assert all(also == () for _, also in out)


def test_chain_by_id_then_fingerprint():
    # b shares a's URL; c shares b's fingerprint but neither of a's keys: still one job.
    a = make_job(1, source="himalayas", company="Acme", title="Developer")
    b = make_job(1, source="wwr", company="Acme Inc", title="Python Developer")
    c = make_job(9, source="remoteok", company="Acme", title="Python Developer")
    assert dedupe_in_run([a, b, c]) == [(a, ("wwr", "remoteok"))]
