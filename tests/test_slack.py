import json
import logging

import pytest
import requests

from fakes import make_job
from jobagent.digest import build_digest
from jobagent.models import Assessment, Candidate, Category, RunStats, Verdict
from jobagent.slack import MAX_BLOCKS, MAX_TEXT, SlackError, SlackNotifier, build_blocks, escape

HOOK = "https://hooks.slack.com/services/T000/B000/SECRETTOKEN"
LABELS = {"remoteok": "Remote OK", "himalayas": "Himalayas"}


class FakeResponse:
    def __init__(self, status=200, text="ok"):
        self.status_code = status
        self.text = text


class FakePost:
    def __init__(self, response=None, error=None):
        self.calls = []
        self.response = response or FakeResponse()
        self.error = error

    def __call__(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


def cand(n, score, category=Category.STACK, **job):
    j = make_job(n, **job)
    return Candidate(
        job=j,
        verdict=Verdict(keep=True, category=category, location_rule="worldwide"),
        assessment=Assessment(j.id, score, f"reason {n}", "draft"),
    )


def stats(**kw):
    s = RunStats(fetched={"remoteok": 100, "himalayas": 300}, kept=120, new=40, scored=20)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def digest(cands, **kw):
    return build_digest(
        cands, kw.pop("stats", stats()), run_date="2026-11-25", threshold=70, max_jobs=12,
        sheet_url=kw.pop("sheet_url", "https://docs.google.com/spreadsheets/d/abc"),
    )


def all_text(blocks):
    return json.dumps(blocks)


def test_digest_layout():
    d = digest([
        cand(1, 85, source="remoteok", salary="$60k-$80k"),
        cand(2, 75, Category.AUTOMATION, source="himalayas"),
        cand(3, 72, Category.TECH_ENTRY, source="hn"),
        cand(4, 40),  # below threshold: not shown
    ])
    blocks = build_blocks(d, LABELS)
    assert blocks[0]["type"] == "header"
    assert blocks[0]["text"]["text"] == "Job digest 2026-11-25: 3 new matches"
    text = all_text(blocks)
    assert "400 fetched, 120 passed filters, 40 new, 20 scored" in text
    for title in ("*My stack* (1)", "*Automation* (1)", "*Starter tech roles* (1)"):
        assert title in text
    job1 = next(b["text"]["text"] for b in blocks if "Software Engineer 1" in str(b))
    assert job1.startswith("*<https://jobs.example.com/1|Software Engineer 1>*")
    assert "Company 1 · *85*/100 · $60k-$80k" in job1
    assert "reason 1" in job1
    assert "_via Remote OK_" in job1
    assert "_via Himalayas_" in text
    assert "_via hn_" in text  # unknown label falls back to the source key
    assert "Software Engineer 4" not in text
    assert "<https://docs.google.com/spreadsheets/d/abc|Open the job tracker Sheet>" in blocks[-1]["elements"][0]["text"]


def test_empty_day_still_sends_counts():
    d = digest([cand(1, 40)])
    blocks = build_blocks(d, LABELS)
    assert blocks[0]["text"]["text"] == "Job digest 2026-11-25"
    assert "Nothing new at 70+ today (400 fetched, 120 passed filters, 40 new, 20 scored)." in all_text(blocks)


def test_source_errors_are_named_in_the_footer():
    d = digest([], stats=stats(source_errors={"hn": "Timeout"}))
    assert "Sources with errors today: hn." in all_text(build_blocks(d, LABELS))


def test_job_text_is_escaped_and_cannot_inject_links_or_mentions():
    c = cand(1, 90, title="Dev <!channel> & <https://evil.example|click> | x", company="A&B <Corp>")
    text = next(b["text"]["text"] for b in build_blocks(digest([c]), LABELS) if "Dev" in str(b))
    assert "<!channel>" not in text and "evil.example|" not in text
    assert "&lt;!channel&gt; &amp; &lt;https://evil.example¦click&gt; ¦ x" in text
    assert "A&amp;B &lt;Corp&gt;" in text


def test_unsafe_urls_are_not_linked():
    c = cand(1, 90, url="javascript:alert(1)")
    text = next(b["text"]["text"] for b in build_blocks(digest([c]), LABELS) if "Software" in str(b))
    assert "javascript" not in text
    assert text.startswith("*Software Engineer 1*")


def test_url_special_characters_are_encoded():
    c = cand(1, 90, url="https://x.example/job?a=1&b=2|3")
    text = next(b["text"]["text"] for b in build_blocks(digest([c]), LABELS) if "Software" in str(b))
    assert "<https://x.example/job?a=1&amp;b=2%7C3|Software Engineer 1>" in text


def test_long_fields_fit_slack_limits():
    c = cand(1, 90, title="T" * 5000, company="C" * 5000, salary="S" * 5000)
    blocks = build_blocks(digest([c]), LABELS)
    for b in blocks:
        t = b.get("text", {}).get("text", "")
        assert len(t) <= (150 if b["type"] == "header" else MAX_TEXT)


def test_block_count_is_capped():
    from jobagent.interfaces import Digest

    d = Digest(run_date="2026-11-25", sections={"My stack": [cand(i, 90) for i in range(80)]}, stats=stats(), sheet_url="https://s")
    blocks = build_blocks(d, LABELS)
    assert len(blocks) == MAX_BLOCKS
    assert "didn't fit" in all_text(blocks)
    assert blocks[-1]["type"] == "context" and "Sheet" in all_text(blocks[-1])


def test_send_posts_blocks_with_escaped_text_fallback():
    post = FakePost()
    SlackNotifier(HOOK, labels=LABELS, post=post).send(digest([cand(1, 85, title="A <b> & c")]))
    (call,) = post.calls
    assert call["url"] == HOOK and call["timeout"]
    payload = call["json"]
    assert payload["blocks"][0]["type"] == "header"
    assert payload["text"].startswith("Job digest 2026-11-25")
    assert "A &lt;b&gt; &amp; c" in payload["text"]


def test_send_failure_is_short_and_has_no_job_text():
    post = FakePost()
    SlackNotifier(HOOK, post=post).send_failure("ConnectionError")
    (call,) = post.calls
    assert set(call["json"]) == {"text"}
    assert "run failed (ConnectionError)" in call["json"]["text"]


def test_network_errors_never_leak_the_webhook_url(caplog):
    caplog.set_level(logging.DEBUG)
    post = FakePost(error=requests.ConnectionError(f"Max retries exceeded with url: {HOOK}"))
    n = SlackNotifier(HOOK, post=post)
    with pytest.raises(SlackError) as err:
        n.send_failure("X")
    assert "SECRETTOKEN" not in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__
    assert "SECRETTOKEN" not in caplog.text
    assert "SECRETTOKEN" not in repr(n)


def test_slack_rejection_raises_with_status_only():
    post = FakePost(response=FakeResponse(400, "invalid_blocks"))
    with pytest.raises(SlackError, match=r"HTTP 400 invalid_blocks"):
        SlackNotifier(HOOK, post=post).send(digest([]))


def test_escape():
    assert escape("a & <b>") == "a &amp; &lt;b&gt;"
