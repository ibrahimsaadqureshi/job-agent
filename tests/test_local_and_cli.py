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
