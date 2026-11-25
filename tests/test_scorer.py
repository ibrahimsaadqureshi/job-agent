"""The LLM scorer: prompt building, output validation, batching and drafting (no network)."""

import json

import pytest

from fakes import make_job
from jobagent.llm import ProviderChain
from jobagent.llm.base import RateLimited
from jobagent.scorer import (
    REASON_MAX,
    DraftError,
    LLMScorer,
    build_draft_prompt,
    build_score_prompt,
    clean_draft,
    job_payload,
    load_prompt,
    parse_scores,
    truncate,
)

IDS = {"j1", "j2", "j3"}
PROFILE = "The candidate\nFull-stack developer. TypeScript, React, NestJS, MongoDB. Built a booking app."


# --- Validator --------------------------------------------------------------------------


def test_parses_a_clean_array():
    text = '[{"id": "j1", "score": 82, "reason": "Junior React role"}, {"id": "j2", "score": 10, "reason": "Asks 8 years"}]'
    assert parse_scores(text, IDS) == {"j1": (82, "Junior React role"), "j2": (10, "Asks 8 years")}


def test_strips_code_fences():
    text = '```json\n[{"id": "j1", "score": 70, "reason": "ok"}]\n```'
    assert parse_scores(text, IDS) == {"j1": (70, "ok")}


def test_ignores_prose_around_the_json():
    text = 'Here are the scores [as asked]:\n[{"id": "j3", "score": 55, "reason": "Stretch"}]\nHope this helps!'
    assert parse_scores(text, IDS) == {"j3": (55, "Stretch")}


def test_accepts_an_object_wrapping_the_array_or_a_single_object():
    assert parse_scores('{"scores": [{"id": "j1", "score": 1, "reason": "r"}]}', IDS) == {"j1": (1, "r")}
    assert parse_scores('{"id": "j2", "score": 2, "reason": "r"}', IDS) == {"j2": (2, "r")}


def test_drops_unknown_missing_and_duplicate_ids():
    text = json.dumps(
        [
            {"id": "j9", "score": 80, "reason": "not sent"},
            {"score": 80, "reason": "no id"},
            {"id": 1, "score": 80, "reason": "id not a string"},
            {"id": "j1", "score": 60, "reason": "first"},
            {"id": "j1", "score": 99, "reason": "duplicate"},
        ]
    )
    assert parse_scores(text, IDS) == {"j1": (60, "first")}


def test_drops_out_of_range_and_non_integer_scores():
    text = json.dumps(
        [
            {"id": "j1", "score": 101, "reason": "too high"},
            {"id": "j2", "score": -5, "reason": "negative"},
            {"id": "j3", "score": 72.5, "reason": "fraction"},
        ]
    )
    assert parse_scores(text, IDS) == {}
    assert parse_scores('[{"id": "j1", "score": true, "reason": "bool"}]', IDS) == {}
    assert parse_scores('[{"id": "j1", "score": null, "reason": "null"}]', IDS) == {}


def test_accepts_string_and_whole_float_scores():
    text = '[{"id": "j1", "score": "85", "reason": "a"}, {"id": "j2", "score": 40.0, "reason": "b"}]'
    assert parse_scores(text, IDS) == {"j1": (85, "a"), "j2": (40, "b")}
    assert parse_scores('[{"id": "j1", "score": "high", "reason": "a"}]', IDS) == {}


def test_drops_items_with_empty_or_missing_reason_and_trims_long_ones():
    text = json.dumps(
        [
            {"id": "j1", "score": 50, "reason": "  "},
            {"id": "j2", "score": 50},
            {"id": "j3", "score": 50, "reason": "word " * 60},
        ]
    )
    out = parse_scores(text, IDS)
    assert set(out) == {"j3"}
    assert len(out["j3"][1]) <= REASON_MAX


def test_salvages_complete_items_from_truncated_json():
    text = '[{"id": "j1", "score": 80, "reason": "good"}, {"id": "j2", "score": 30, "reason": "Asks 7 ye'
    assert parse_scores(text, IDS) == {"j1": (80, "good")}


def test_garbage_gives_nothing():
    for text in ("", "Sorry, I can't help with that.", "[1, 2, 3]", "{not json", "```\n```"):
        assert parse_scores(text, IDS) == {}


# --- Prompt building --------------------------------------------------------------------


def test_truncate_cuts_at_a_word_boundary_and_collapses_whitespace():
    assert truncate("a  b\n\nc", 100) == "a b c"
    out = truncate("alpha beta gamma delta epsilon", 17)
    assert len(out) <= 17
    assert out.endswith("…")
    assert out == "alpha beta gamma…"
    assert truncate("alpha beta gamma delta", 14) == "alpha beta…"


def test_job_payload_carries_hints_and_truncated_description():
    job = make_job(
        1,
        title="Junior React Developer",
        location="Worldwide",
        salary="$30k",
        description="We need 3+ years of experience with React. " + "x" * 3000,
    )
    payload = job_payload(job, "j1", 200)
    assert payload["id"] == "j1"
    assert payload["title"] == "Junior React Developer"
    assert payload["location_rule"] == "worldwide"
    assert payload["category"] == "stack"
    assert payload["salary"] == "$30k"
    assert payload["required_years"] == 3
    assert len(payload["description"]) <= 200
    assert job.id not in json.dumps(payload)  # the real id never goes to the LLM


def test_job_payload_marks_missing_fields():
    payload = job_payload(make_job(1, location="", salary="", description="React work"), "j1", 100)
    assert payload["location"] == "not stated"
    assert payload["salary"] == "not listed"
    assert payload["required_years"] == "not stated"


def test_score_prompt_contains_profile_rubric_and_one_line_per_job():
    payloads = [job_payload(make_job(n), f"j{n}", 100) for n in (1, 2)]
    prompt = build_score_prompt(load_prompt("score"), PROFILE, payloads)
    assert PROFILE.strip() in prompt
    assert "{profile}" not in prompt and "{jobs}" not in prompt
    assert "Hivex" in prompt and "required_years" in prompt
    job_lines = [line for line in prompt.splitlines() if line.startswith('{"id": "j')]
    assert len(job_lines) == 2


def test_draft_prompt_fills_every_placeholder_and_truncates():
    job = make_job(1, description="y " * 5000)
    prompt = build_draft_prompt(load_prompt("draft"), job, PROFILE, "Junior React role", 300)
    assert job.title in prompt and job.company in prompt and "Junior React role" in prompt
    assert "{" + "title}" not in prompt and "{" + "description}" not in prompt
    assert "y " * 200 not in prompt


# --- Batching and the scorer ------------------------------------------------------------


class EchoProvider:
    """Scores every job it is sent with a fixed score, and records each prompt."""

    def __init__(self, name="echo", score=75, fail_with=None):
        self.name = name
        self.score = score
        self.fail_with = fail_with
        self.prompts = []

    def generate(self, prompt, *, schema=None, max_tokens=2048, temperature=0.2):
        self.prompts.append(prompt)
        if self.fail_with:
            raise self.fail_with
        keys = [json.loads(line)["id"] for line in prompt.splitlines() if line.startswith('{"id": "j')]
        return json.dumps([{"id": k, "score": self.score, "reason": f"reason {k}"} for k in keys])


def scorer_with(*providers, batch_size=10):
    return LLMScorer(ProviderChain(list(providers)), batch_size=batch_size, description_chars=200)


def test_score_batches_jobs_and_maps_results_back_to_real_ids():
    jobs = [make_job(n) for n in range(1, 24)]
    provider = EchoProvider()
    out = scorer_with(provider, batch_size=10).score(jobs, PROFILE)
    assert len(provider.prompts) == 3  # 10 + 10 + 3
    assert set(out) == {j.id for j in jobs}
    assert all(score == 75 for score, _ in out.values())


def test_score_with_no_jobs_makes_no_calls():
    provider = EchoProvider()
    assert scorer_with(provider).score([], PROFILE) == {}
    assert provider.prompts == []


def test_score_falls_back_to_the_next_provider_on_rate_limit():
    primary = EchoProvider("gemini", fail_with=RateLimited("gemini: 429"))
    fallback = EchoProvider("github", score=60)
    jobs = [make_job(n) for n in range(1, 16)]
    out = scorer_with(primary, fallback, batch_size=10).score(jobs, PROFILE)
    assert len(out) == 15 and all(s == 60 for s, _ in out.values())
    assert len(primary.prompts) == 1  # skipped for the second batch
    assert len(fallback.prompts) == 2


def test_score_leaves_jobs_unscored_when_every_provider_fails():
    a = EchoProvider("a", fail_with=RateLimited("a"))
    b = EchoProvider("b", fail_with=RateLimited("b"))
    assert scorer_with(a, b).score([make_job(1), make_job(2)], PROFILE) == {}


class SequenceProvider:
    def __init__(self, *replies, name="seq"):
        self.name = name
        self.replies = list(replies)
        self.calls = 0

    def generate(self, prompt, *, schema=None, max_tokens=2048, temperature=0.2):
        self.calls += 1
        return self.replies.pop(0)


def test_bad_output_is_retried_once_then_falls_back():
    bad = SequenceProvider("not json", "still not json", name="bad")
    good = EchoProvider("good", score=42)
    out = scorer_with(bad, good).score([make_job(1)], PROFILE)
    assert bad.calls == 2
    assert list(out.values()) == [(42, "reason j1")]


def test_partial_batch_keeps_the_valid_items():
    reply = '[{"id": "j1", "score": 90, "reason": "great"}, {"id": "j2", "score": 900, "reason": "bad"}]'
    jobs = [make_job(1), make_job(2)]
    out = scorer_with(SequenceProvider(reply)).score(jobs, PROFILE)
    assert out == {jobs[0].id: (90, "great")}


# --- Drafts -----------------------------------------------------------------------------

NOTE = (
    "I build full-stack TypeScript apps with React and NestJS, and your team's focus on a fast "
    "booking flow matches what I ship today. At my current company I built a booking platform on "
    "NestJS and MongoDB, from the data model to the React screens, and I keep it running in "
    "production. Your stack is close to mine, so I could take on real tickets in the first weeks. "
    "Go is new to me, but I learn by building, and I would use the mentoring your posting "
    "describes to close that gap quickly while shipping on the parts I know."
)


def test_clean_draft_keeps_a_good_note():
    assert clean_draft(NOTE) == NOTE


def test_clean_draft_removes_fences_greeting_sign_off_markdown_and_contacts():
    text = f"```\nDear Hiring Team,\n\n**{NOTE}** Reach me at x@y.test or https://me.test\n\nBest regards,\nThe candidate\n```"
    out = clean_draft(text)
    assert not out.startswith("Dear")
    assert "Best regards" not in out and "The candidate" not in out
    assert "**" not in out and "x@y.test" not in out and "https://" not in out
    assert out.startswith("I build full-stack")


def test_clean_draft_removes_placeholders():
    assert "[Your Name]" not in clean_draft(NOTE + " [Your Name]")


def test_clean_draft_trims_long_notes_at_a_sentence_end():
    out = clean_draft(NOTE + " " + NOTE)
    assert len(out.split()) <= 130
    assert out.endswith(".")


def test_clean_draft_rejects_too_short_output():
    assert clean_draft("Too short to be a note.") == ""


def test_draft_returns_cleaned_note_and_falls_back():
    bad = SequenceProvider("", "", name="bad")
    good = SequenceProvider(NOTE, name="good")
    note = scorer_with(bad, good).draft(make_job(1), PROFILE, "Junior React role")
    assert note == NOTE


def test_draft_raises_when_no_provider_produces_a_note():
    failing = EchoProvider("a", fail_with=RateLimited("a"))
    with pytest.raises(DraftError):
        scorer_with(failing).draft(make_job(1), PROFILE, "reason")
