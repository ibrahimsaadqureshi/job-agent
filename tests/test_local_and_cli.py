import csv
from datetime import date

import pytest

from fakes import make_job
from jobagent import cli
from jobagent.local import LocalTracker
from jobagent.models import SHEET_COLUMNS, Candidate, Category, TrackerRow, Verdict


def row(n):
    c = Candidate(job=make_job(n), verdict=Verdict(keep=True, category=Category.STACK))
    return TrackerRow.from_candidate(c, date(2026, 11, 25))


def test_local_tracker_persists_rows_and_seen_ids(tmp_path):
    t = LocalTracker(tmp_path, persist=True, out=lambda _: None)
    t.append([row(1), row(2)])
    t.append([row(3)])
    assert t.seen_ids() == {row(1).id, row(2).id, row(3).id}
    with (tmp_path / "rows.csv").open(encoding="utf-8") as f:
        lines = list(csv.reader(f))
    assert tuple(lines[0]) == SHEET_COLUMNS
    assert len(lines) == 4


def test_dry_run_tracker_reads_but_never_writes(tmp_path):
    t = LocalTracker(tmp_path, persist=False, out=lambda _: None)
    t.append([row(1)])
    assert not (tmp_path / "rows.csv").exists()
    assert t.seen_ids() == set()


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "STATE_DIR", tmp_path)
    monkeypatch.setattr(cli, "load_settings", lambda: cli.Settings())


def test_cli_dry_run_with_no_sources(isolated_state, capsys, monkeypatch):
    monkeypatch.setattr(cli.source_registry, "ALL_SOURCES", [])  # no network in tests
    assert cli.main(["run", "--dry-run", "--no-llm"]) == 0
    out = capsys.readouterr().out
    assert "mode=dry-run sources=0 llm=off" in out
    assert "fetched=0" in out


def test_cli_production_mode_explains_what_is_missing(isolated_state, capsys):
    assert cli.main(["run", "--no-llm"]) == 2
    assert "M4" in capsys.readouterr().err


def test_cli_rejects_unknown_source(isolated_state, capsys):
    assert cli.main(["run", "--dry-run", "--no-llm", "--sources", "indeed"]) == 2
    assert "unknown source" in capsys.readouterr().err


def test_build_scorer_needs_a_provider():
    with pytest.raises(cli.SetupError, match="GEMINI_API_KEY"):
        cli.build_scorer(cli.Settings(), no_llm=False)
    assert cli.build_scorer(cli.Settings(), no_llm=True) is None
    scorer = cli.build_scorer(cli.Settings(gemini_api_key="k", github_token="t"), no_llm=False)
    assert scorer.chain.names == ["gemini", "github"]


def test_cli_run_without_profile_fails_before_fetching(isolated_state, capsys, monkeypatch):
    monkeypatch.setattr(cli, "load_settings", lambda: cli.Settings(gemini_api_key="k"))
    assert cli.main(["run", "--dry-run"]) == 2
    assert "CANDIDATE_PROFILE" in capsys.readouterr().err


def test_cli_dry_run_prints_scores_reasons_and_drafts(isolated_state, capsys, monkeypatch):
    from fakes import FakeScorer, FakeSource

    jobs = [make_job(n, title=f"Junior React Developer {n}") for n in range(1, 4)]
    scorer = FakeScorer({jobs[0].id: 88, jobs[1].id: 40, jobs[2].id: 75})
    monkeypatch.setattr(cli.source_registry, "get_sources", lambda names=None: [FakeSource("fake", jobs)])
    monkeypatch.setattr(cli, "build_scorer", lambda settings, no_llm: scorer)
    monkeypatch.setattr(cli, "load_profile", lambda settings, no_llm: "The candidate\nReact developer")
    assert cli.main(["run", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"reason {jobs[0].id}" in out
    assert "draft for Junior React Developer 1" in out
    assert "draft for Junior React Developer 2" not in out  # 40 is under the threshold
    assert sum(len(b) for b in scorer.scored_batches) == 3  # default limit (100) leaves all 3
