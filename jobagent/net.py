"""Shared HTTP session for all sources: honest User-Agent, timeout and one retry."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "job-agent/2.0 (personal job search; +https://github.com/ibrahimsaadqureshi/job-agent)"
DEFAULT_TIMEOUT = 30  # seconds


class _TimeoutSession(requests.Session):
    """A Session that applies DEFAULT_TIMEOUT unless a call sets its own."""

    def request(self, method, url, **kwargs):  # type: ignore[override]
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        return super().request(method, url, **kwargs)


def make_session() -> requests.Session:
    session = _TimeoutSession()
    session.headers["User-Agent"] = USER_AGENT
    retry = Retry(
        total=1,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
