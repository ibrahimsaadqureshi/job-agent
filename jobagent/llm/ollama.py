"""Ollama on this machine (http://127.0.0.1:11434), optional. Select with LLM_PROVIDER=ollama."""

from __future__ import annotations

import time
from typing import Callable

import requests

from jobagent.llm.base import Pacer, ProviderError, post_json


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        model: str,
        session: requests.Session,
        *,
        base_url: str = "http://127.0.0.1:11434",
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model = model
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.pacer = Pacer(0.0)
        self.sleep = sleep

    def generate(
        self, prompt: str, *, schema: dict | None = None, max_tokens: int = 2048, temperature: float = 0.2
    ) -> str:
        body: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if schema is not None:
            body["format"] = schema
        data = post_json(
            self.session,
            f"{self.base_url}/api/chat",
            name=self.name,
            headers={"Content-Type": "application/json"},
            body=body,
            pacer=self.pacer,
            timeout=300,  # local 7B models are slow
            sleep=self.sleep,
        )
        try:
            return data["message"]["content"] or ""
        except (KeyError, TypeError) as exc:
            raise ProviderError("ollama: unexpected response shape") from exc
