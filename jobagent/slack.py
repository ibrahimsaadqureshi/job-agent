"""Slack digest (M5): one incoming-webhook message per run.

- Block Kit layout: a header with the date and count, one section per category, each job
  with a linked title, company, score, salary, the one-line reason and "via <source>"
  (RemoteOK and Remotive require the credit), then a footer linking the Sheet.
- An empty day still sends a message, so silence always means the run broke.
- Job text is untrusted: &, < and > are escaped so it can't inject links or mentions, and
  every field is cut to fit Slack's limits (50 blocks, 3,000 characters per text field).
- The webhook URL is the secret. It is never logged, and network errors are re-raised
  without it (requests puts the URL in its exception messages).
"""

from __future__ import annotations

import logging
from typing import Callable
from urllib.parse import quote, urlsplit

import requests

from jobagent.digest import render_text
from jobagent.interfaces import Digest
from jobagent.models import Candidate

log = logging.getLogger("jobagent")

MAX_BLOCKS = 50
MAX_TEXT = 3000  # section / context text field
MAX_HEADER = 150  # header plain_text
MAX_FALLBACK = 3000
TIMEOUT_SECONDS = 20


class SlackError(RuntimeError):
    """Slack refused or couldn't be reached. The message never contains the webhook URL."""


def escape(text: str) -> str:
    """Escape the three characters Slack treats as control characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())  # one line, no stray newlines from job boards
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _safe_url(url: str) -> str:
    """An http(s) URL that can sit inside <url|text>, or "" if it isn't one."""
    url = url.strip()
    if urlsplit(url).scheme not in ("http", "https"):
        return ""
    url = quote(url, safe=":/?#[]@!$&'()*+,;=%~-._")  # encodes |, <, >, spaces, quotes
    return url.replace("&", "&amp;")


def _link(url: str, text: str) -> str:
    label = escape(text).replace("|", "¦")
    safe = _safe_url(url)
    return f"<{safe}|{label}>" if safe else label


def _mrkdwn(text: str) -> dict:
    return {"type": "mrkdwn", "text": text[:MAX_TEXT]}


def _section(text: str) -> dict:
    return {"type": "section", "text": _mrkdwn(text)}


def _context(text: str) -> dict:
    return {"type": "context", "elements": [_mrkdwn(text)]}


def _stats_line(digest: Digest) -> str:
    s = digest.stats
    return f"{s.total_fetched} fetched, {s.kept} passed filters, {s.new} new, {s.scored} scored"


def job_text(c: Candidate, labels: dict[str, str]) -> str:
    j = c.job
    title = _cut(j.title, 150) or "Untitled role"
    parts = [f"*{_link(j.url, title)}*"]
    line = [escape(_cut(j.company, 80)) or "Unknown company", f"*{c.score}*/100"]
    if j.salary:
        line.append(escape(_cut(j.salary, 60)))
    parts.append(" · ".join(line))
    if c.assessment and c.assessment.reason:
        parts.append(escape(_cut(c.assessment.reason, 300)))
    parts.append(f"_via {escape(labels.get(j.source, j.source))}_")
    return "\n".join(parts)


def build_blocks(digest: Digest, labels: dict[str, str]) -> list[dict]:
    count = sum(len(v) for v in digest.sections.values())
    if digest.is_empty:
        title = f"Job digest {digest.run_date}"
    else:
        title = f"Job digest {digest.run_date}: {count} new match{'es' if count != 1 else ''}"
    head: list[dict] = [{"type": "header", "text": {"type": "plain_text", "text": title[:MAX_HEADER]}}]

    body: list[dict] = []
    if digest.is_empty:
        body.append(_section(f"Nothing new at {digest.threshold}+ today ({_stats_line(digest)})."))
    else:
        head.append(_context(f"{_stats_line(digest)}. Showing jobs scoring {digest.threshold}+."))
        for section_title, cands in digest.sections.items():
            body.append({"type": "divider"})
            body.append(_section(f"*{escape(section_title)}* ({len(cands)})"))
            body.extend(_section(job_text(c, labels)) for c in cands)

    foot: list[dict] = []
    notes = []
    if digest.sheet_url:
        notes.append(f"{_link(digest.sheet_url, 'Open the job tracker Sheet')} for the draft notes and the full list.")
    if digest.stats.source_errors:
        notes.append("Sources with errors today: " + escape(", ".join(sorted(digest.stats.source_errors))) + ".")
    if notes:
        foot = [{"type": "divider"}, _context("\n".join(notes))]

    room = MAX_BLOCKS - len(head) - len(foot)
    if len(body) > room:
        body = body[: room - 1] + [_context("More jobs didn't fit in this message. See the Sheet.")]
    return head + body + foot


def build_payload(digest: Digest, labels: dict[str, str]) -> dict:
    return {"text": escape(render_text(digest))[:MAX_FALLBACK], "blocks": build_blocks(digest, labels)}


class SlackNotifier:
    """Posts the digest to a Slack incoming webhook."""

    def __init__(
        self,
        webhook_url: str,
        *,
        labels: dict[str, str] | None = None,
        post: Callable[..., requests.Response] | None = None,
    ):
        self._url = webhook_url
        self.labels = labels or {}
        # A plain session with no retry adapter: urllib3's retry warnings print the URL path,
        # which for a webhook is the secret.
        self._post = post or requests.Session().post

    def __repr__(self) -> str:  # never show the URL
        return "SlackNotifier(<webhook hidden>)"

    def _send(self, payload: dict) -> None:
        try:
            resp = self._post(self._url, json=payload, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise SlackError(f"Could not reach Slack ({type(exc).__name__}).") from None
        if resp.status_code != 200:
            detail = "".join(ch for ch in (resp.text or "")[:40] if ch.isalnum() or ch in "_- ")
            status = f"HTTP {resp.status_code}" + (f" {detail}" if detail else "")
            raise SlackError(f"Slack rejected the message ({status}).")

    def send(self, digest: Digest) -> None:
        payload = build_payload(digest, self.labels)
        self._send(payload)
        log.info("slack: digest sent (%d blocks)", len(payload["blocks"]))

    def send_failure(self, message: str) -> None:
        text = (
            f":warning: job-agent run failed ({escape(_cut(message, 200))}). "
            "Today's digest may be missing. Check the latest run log."
        )
        self._send({"text": text})
        log.info("slack: failure notice sent")
