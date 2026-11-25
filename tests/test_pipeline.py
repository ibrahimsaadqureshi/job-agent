from datetime import date

from fakes import CapturingNotifier, FakeScorer, FakeSource, MemoryTracker, make_job
from jobagent.pipeline import RunOptions, run

TODAY = date(2026, 11, 25)


def go(sources, *, tracker=None, scorer=None, **opts):
    tracker = tracker or MemoryTracker()
    notifier = CapturingNotifier()
    result = run(
        sources=sources,
        tracker=tracker,
        notifier=notifier,
        scorer=scorer,
        profile="profile",
        options=RunOptions(**opts),
        today=TODAY,
        session=object(),  # fakes never use it; no network in tests
    )
    return result, tracker, notifier


def test_no_sources_runs_clean_and_sends_one_digest():
    result, tracker, notifier = go([])
    assert result.stats.total_fetched == 0
    assert tracker.rows == []
    assert len(notifier.digests) == 1
    assert notifier.digests[0].is_empty


def test_failing_source_does_not_stop_the_run():
    good = FakeSource("good", [make_job(1)])
    bad = FakeSource("bad", error=ConnectionError("boom"))
    result, _, _ = go([bad, good])
    assert result.stats.fetched == {"good": 1}
    assert result.stats.source_errors == {"bad": "ConnectionError"}
    assert result.stats.new == 1


def test_in_run_duplicates_keep_first_source():
    job = make_job(1)
    a = FakeSource("himalayas", [make_job(1, source="himalayas")])
    b = FakeSource("wwr", [make_job(1, source="wwr")])
    result, _, _ = go([a, b], scorer=FakeScorer({job.id: 80}))
    assert result.stats.duplicates_in_run == 1
    assert len(result.candidates) == 1
    assert result.candidates[0].job.source == "himalayas"
    assert result.candidates[0].also_on == ("wwr",)


def test_already_tracked_jobs_are_skipped():
    j1, j2 = make_job(1), make_job(2)
    tracker = MemoryTracker(seen={j1.id})
    scorer = FakeScorer({j1.id: 90, j2.id: 90})
    result, tracker, _ = go([FakeSource("s", [j1, j2])], tracker=tracker, scorer=scorer)
    assert result.stats.already_seen == 1
    assert scorer.scored_batches == [[j2.id]]
    assert [r.id for r in tracker.rows] == [j2.id]


def test_second_run_adds_no_duplicate_rows():
    jobs = [make_job(1), make_job(2)]
    scorer = FakeScorer({j.id: 75 for j in jobs})
    tracker = MemoryTracker()
    go([FakeSource("s", jobs)], tracker=tracker, scorer=scorer)
    result, tracker, _ = go([FakeSource("s", jobs)], tracker=tracker, scorer=scorer)
    assert len(tracker.rows) == 2
    assert result.stats.new == 0


def test_no_llm_writes_nothing_so_jobs_are_retried():
    result, tracker, _ = go([FakeSource("s", [make_job(1)])], scorer=None)
    assert result.stats.unscored == 1
    assert tracker.rows == []


def test_track_unscored_records_jobs_so_a_second_run_sees_them():
    # `--local --no-llm`: no scores, but rows are kept so cross-run dedupe can be checked.
    jobs = [make_job(1), make_job(2)]
    tracker = MemoryTracker()
    first, tracker, _ = go([FakeSource("s", jobs)], tracker=tracker, scorer=None, track_unscored=True)
    assert first.stats.written == 2 and tracker.rows[0].score is None
    second, tracker, _ = go([FakeSource("s", jobs)], tracker=tracker, scorer=None, track_unscored=True)
    assert second.stats.already_seen == 2 and second.stats.new == 0
    assert len(tracker.rows) == 2


def test_limit_scores_newest_first_and_leaves_rest_for_next_run():
    old, new = make_job(1, day=1), make_job(2, day=20)
    scorer = FakeScorer({old.id: 80, new.id: 80})
    result, tracker, _ = go([FakeSource("s", [old, new])], scorer=scorer, limit=1)
    assert scorer.scored_batches == [[new.id]]
    assert [r.id for r in tracker.rows] == [new.id]
    assert result.stats.unscored == 1


def test_drafts_only_at_or_above_threshold_and_capped():
    jobs = [make_job(i) for i in range(1, 5)]
    scores = {jobs[0].id: 95, jobs[1].id: 70, jobs[2].id: 69, jobs[3].id: 88}
    scorer = FakeScorer(scores)
    result, tracker, _ = go([FakeSource("s", jobs)], scorer=scorer, threshold=70, max_drafts=2)
    assert scorer.drafted == [jobs[0].id, jobs[3].id]  # best two, highest first
    drafts = {r.id: r.draft_note for r in tracker.rows}
    assert drafts[jobs[0].id].startswith("draft for")
    assert drafts[jobs[1].id] == ""  # at threshold but over the cap
    assert drafts[jobs[2].id] == ""  # below threshold
    assert result.stats.drafted == 2


def test_failed_draft_still_tracks_the_scored_job():
    job = make_job(1)
    scorer = FakeScorer({job.id: 90}, fail_draft_ids={job.id})
    result, tracker, _ = go([FakeSource("s", [job])], scorer=scorer)
    assert tracker.rows[0].score == 90
    assert tracker.rows[0].draft_note == ""
    assert result.stats.drafted == 0


def test_scorer_failure_leaves_everything_unscored():
    job = make_job(1)
    result, tracker, notifier = go([FakeSource("s", [job])], scorer=FakeScorer({}, fail_score=True))
    assert result.stats.unscored == 1
    assert tracker.rows == []
    assert notifier.digests[0].is_empty


def test_digest_contains_only_jobs_at_threshold():
    hi, lo = make_job(1), make_job(2)
    scorer = FakeScorer({hi.id: 85, lo.id: 40})
    _, _, notifier = go([FakeSource("s", [hi, lo])], scorer=scorer, threshold=70)
    digest = notifier.digests[0]
    listed = [c.job.id for cands in digest.sections.values() for c in cands]
    assert listed == [hi.id]
