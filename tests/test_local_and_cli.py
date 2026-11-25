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
    err = capsys.readouterr().err
    for name in ("GOOGLE_SERVICE_ACCOUNT_JSON", "SHEET_ID", "SLACK_WEBHOOK_URL"):
        assert name in err


PROD = dict(google_service_account_json="{}", sheet_id="sheet123", slack_webhook_url="https://hooks.example/SECRET")


@pytest.fixture
def production(isolated_state, monkeypatch):
    """Production mode with every external piece faked."""
    from fakes import CapturingNotifier, FakeScorer, FakeSource, MemoryTracker

    jobs = [make_job(n, title=f"Junior React Developer {n}") for n in range(1, 4)]
    env = type("Env", (), {})()
    env.jobs = jobs
    env.notifier = CapturingNotifier()
    env.tracker = MemoryTracker()
    env.scorer = FakeScorer({j.id: 80 for j in jobs})
    monkeypatch.setattr(cli, "load_settings", lambda: cli.Settings(**PROD))
    monkeypatch.setattr(cli.source_registry, "get_sources", lambda names=None: [FakeSource("fake", jobs)])
    monkeypatch.setattr(cli, "build_scorer", lambda settings, no_llm: env.scorer)
    monkeypatch.setattr(cli, "load_profile", lambda settings, no_llm: "The candidate")
    monkeypatch.setattr(cli, "build_tracker", lambda settings, mode: env.tracker)
    monkeypatch.setattr(cli, "build_notifier", lambda settings, mode: env.notifier)
    return env


def test_production_run_tracks_and_sends_with_sheet_link(production, capsys):
    assert cli.main(["run"]) == 0
    assert len(production.tracker.rows) == 3
    (digest,) = production.notifier.digests
    assert digest.sheet_url == "https://docs.google.com/spreadsheets/d/sheet123"
    out = capsys.readouterr().out
    assert "written=3" in out
    assert "Junior React" not in out  # production prints counts only
    assert "sheet123" not in out


def test_production_crash_sends_type_only_failure_and_exits_nonzero(production, capsys):
    class Boom(Exception):
        pass

    def broken_append(rows):
        raise Boom("secret detail https://hooks.example/SECRET")

    production.tracker.append = broken_append
    assert cli.main(["run"]) == 1
    assert production.notifier.failures == ["Boom"]
    err = capsys.readouterr().err
    assert "run failed (Boom)" in err
    assert "SECRET" not in err


def test_production_setup_error_is_reported_to_slack(production, monkeypatch, capsys):
    def no_profile(settings, no_llm):
        raise cli.SetupError("No profile: set CANDIDATE_PROFILE")

    monkeypatch.setattr(cli, "load_profile", no_profile)
    assert cli.main(["run"]) == 2
    assert production.notifier.failures == ["SetupError"]


def test_broken_slack_does_not_hide_the_original_error(production, capsys):
    def broken_send(digest):
        raise RuntimeError("slack down")

    def broken_failure(message):
        raise RuntimeError("still down")

    production.notifier.send = broken_send
    production.notifier.send_failure = broken_failure
    assert cli.main(["run"]) == 1
    err = capsys.readouterr().err
    assert "run failed (RuntimeError)" in err
    assert "could not be sent either" in err


def test_build_production_pieces(monkeypatch):
    from jobagent.sheet import SheetTracker
    from jobagent.slack import SlackNotifier

    with pytest.raises(cli.SetupError, match="GOOGLE_SERVICE_ACCOUNT_JSON"):
        cli.build_tracker(cli.Settings(sheet_id="x"), "production")
    with pytest.raises(cli.SetupError, match="not valid JSON"):
        cli.build_tracker(cli.Settings(sheet_id="x", google_service_account_json="{"), "production")
    good = '{"type": "service_account", "private_key": "k"}'
    assert isinstance(cli.build_tracker(cli.Settings(sheet_id="x", google_service_account_json=good), "production"), SheetTracker)
    n = cli.build_notifier(cli.Settings(slack_webhook_url="https://hooks.example/x"), "production")
    assert isinstance(n, SlackNotifier)
    assert n.labels["remoteok"] == "Remote OK"


def test_setup_sheet_needs_its_settings(isolated_state, capsys):
    assert cli.main(["setup-sheet"]) == 2
    assert "SHEET_ID" in capsys.readouterr().err


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
    assert sum(len(b) for b in scorer.scored_batches) == 3  # default limit (200) leaves all 3
