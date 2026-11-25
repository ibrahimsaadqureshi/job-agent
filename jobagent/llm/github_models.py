"""GitHub Models (models.github.ai), the free CI fallback.

In GitHub Actions the workflow's built-in GITHUB_TOKEN works when the job has
`permissions: models: read`. Locally, a fine-grained token with the `models:read`
permission works. OpenAI-style chat completions API.
"""

from __future__ import annotations

import time
from typing import Callable

import requests

from jobagent.llm.base import Pacer, ProviderError, post_json

ENDPOINT = "https://models.github.ai/inference/chat/completions"
# Free "low" tier models allow about 15 requests a minute; stay under it.
DEFAULT_INTERVAL = 7.0


class GitHubModelsProvider:
    name = "github"

    def __init__(
        self,
        token: str,
        model: str,
        session: requests.Session,
        *,
        pacer: Pacer | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not token:
            raise ValueError("GitHub token is empty")
        self._token = token
        self.model = model
        self.session = session
        self.pacer = pacer or Pacer(DEFAULT_INTERVAL)
        self.sleep = sleep

    def __repr__(self) -> str:
        return f"GitHubModelsProvider(model={self.model!r})"

    def generate(
        self, prompt: str, *, schema: dict | None = None, max_tokens: int = 2048, temperature: float = 0.2
    ) -> str:
        # The scoring output is a top-level JSON array, which OpenAI-style JSON modes
        # don't allow, so the prompt asks for JSON and the validator does the rest.
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        data = post_json(
            self.session,
            ENDPOINT,
            name=self.name,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            body=body,
            pacer=self.pacer,
            sleep=self.sleep,
        )
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("github: unexpected response shape") from exc
