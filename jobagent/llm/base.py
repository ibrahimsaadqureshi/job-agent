"""Shared plumbing for LLM providers: errors, request pacing, and one-retry POSTs.

Logging rule: status codes and provider names only. Never the request body (it holds
the profile), the response text, or the API key.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, Protocol, runtime_checkable

import requests

log = logging.getLogger("jobagent.llm")

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_BACKOFF = 20.0  # seconds; a longer wait means a daily quota, so give up instead


class ProviderError(RuntimeError):
    """A call failed in a way that will repeat (bad key, bad request). Safe message."""


class ProviderUnavailable(ProviderError):
    """Rate-limited or server error, still failing after one retry."""


class RateLimited(ProviderUnavailable):
    """HTTP 429 after one retry: the quota is spent for now."""


@runtime_checkable
class Provider(Protocol):
    name: str

    def generate(
        self, prompt: str, *, schema: dict | None = None, max_tokens: int = 2048, temperature: float = 0.2
    ) -> str:
        """Return the model's text. `schema` (JSON Schema) asks for JSON output when supported."""
        ...


class Pacer:
    """Keeps at least `min_interval` seconds between requests (free-tier per-minute limits)."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.min_interval = min_interval
        self.clock = clock
        self.sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            remaining = self.min_interval - (self.clock() - self._last)
            if remaining > 0:
                self.sleep(remaining)
        self._last = self.clock()


def _retry_delay(response: requests.Response | None, default: float) -> float:
    """Seconds to wait before the one retry: Retry-After, Gemini's RetryInfo, or default."""
    if response is None:
        return default
    header = response.headers.get("Retry-After", "")
    if header.strip().isdigit():
        return float(header)
    try:
        for detail in response.json().get("error", {}).get("details", []):
            delay = detail.get("retryDelay")
            if isinstance(delay, str):
                m = re.fullmatch(r"(\d+(?:\.\d+)?)s", delay.strip())
                if m:
                    return float(m.group(1))
    except (ValueError, AttributeError):
        pass
    return default


def post_json(
    session: requests.Session,
    url: str,
    *,
    name: str,
    headers: dict[str, str],
    body: dict,
    pacer: Pacer,
    timeout: float = 90,
    sleep: Callable[[float], None] = time.sleep,
    backoff: float = 5.0,
) -> dict:
    """POST JSON with pacing and at most one retry on 429 / 5xx / network errors."""
    for attempt in (1, 2):
        pacer.wait()
        response: requests.Response | None = None
        try:
            response = session.post(url, headers=headers, json=body, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            status = type(exc).__name__
        else:
            if response.status_code < 300:
                try:
                    return response.json()
                except ValueError as exc:
                    raise ProviderError(f"{name}: response was not JSON") from exc
            status = str(response.status_code)
            if response.status_code not in RETRY_STATUSES:
                raise ProviderError(f"{name}: HTTP {status}")

        if attempt == 2:
            if status == "429":
                raise RateLimited(f"{name}: HTTP 429 after one retry")
            raise ProviderUnavailable(f"{name}: {status} after one retry")
        delay = _retry_delay(response, backoff)
        if delay > MAX_BACKOFF:
            # A long retry delay means the per-day quota is gone; don't burn the run waiting.
            if status == "429":
                raise RateLimited(f"{name}: HTTP 429, retry in {delay:.0f}s")
            delay = MAX_BACKOFF
        log.info("%s: %s, retrying once in %.0fs", name, status, delay)
        sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
