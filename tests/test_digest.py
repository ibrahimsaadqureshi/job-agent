from fakes import make_job
from jobagent.digest import build_digest, render_text
from jobagent.models import Assessment, Candidate, Category, RunStats, Verdict


def cand(n, score, category=Category.STACK):
    job = make_job(n)
    return Candidate(
        job=job,
        verdict=Verdict(keep=True, category=category, location_rule="worldwide"),
        assessment=Assessment(job.id, score, f"reason {n}"),
    )


def test_sections_ordered_and_capped_across_all_sections():
    cands = [
        cand(1, 90, Category.TECH_ENTRY),
        cand(2, 80, Category.STACK),
        cand(3, 75, Category.AUTOMATION),
        cand(4, 72, Category.STACK),
        cand(5, 50, Category.STACK),
    ]
    d = build_digest(cands, RunStats(), run_date="2026-11-25", threshold=70, max_jobs=3)
    assert list(d.sections) == ["My stack", "Automation", "Starter tech roles"]
    titles = [c.job.title for cs in d.sections.values() for c in cs]
    assert titles == ["Software Engineer 2", "Software Engineer 3", "Software Engineer 1"]


def test_empty_digest_says_so_with_counts():
    stats = RunStats(fetched={"a": 10}, kept=4, new=2, scored=2)
    d = build_digest([cand(1, 40)], stats, run_date="2026-11-25", threshold=70, max_jobs=12)
    assert d.is_empty
    text = render_text(d)
    assert "Nothing new at 70+" in text
    assert "10 fetched" in text


def test_render_lists_job_reason_link_and_source_errors():
    stats = RunStats(fetched={"a": 1}, source_errors={"hn": "Timeout"})
    d = build_digest(
        [cand(1, 88)], stats, run_date="2026-11-25", threshold=70, max_jobs=12, sheet_url="https://sheet"
    )
    text = render_text(d)
    assert "[88] Software Engineer 1 at Company 1" in text
    assert "reason 1" in text
    assert "https://jobs.example.com/1" in text
    assert "Sources with errors: hn" in text
    assert "https://sheet" in text
