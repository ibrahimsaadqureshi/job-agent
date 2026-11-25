"""Google Gemini over plain HTTPS (generativelanguage.googleapis.com), free tier.

The key goes in the x-goog-api-key header, never in the URL, so it can't end up in
logs or exception messages that print URLs.
"""

from __future__ import annotations

import time
from typing import Callable

import requests

from jobagent.llm.base import Pacer, ProviderError, post_json

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
# Free-tier limits for gemini-3.1-flash-lite, confirmed by the owner in AI Studio on
# 2026-11-25: 15 requests/minute, 250K tokens/minute, 500 requests/day. 6 s between calls
# is 10 a minute, safely under 15.
DEFAULT_INTERVAL = 6.0


def to_gemini_schema(schema: dict) -> dict:
    """Gemini's responseSchema uses OpenAPI-style upper-case type names."""
    out: dict = {}
    for key, value in schema.items():
        if key == "type" and isinstance(value, str):
            out[key] = value.upper()
        elif key == "properties" and isinstance(value, dict):
            out[key] = {k: to_gemini_schema(v) for k, v in value.items()}
        elif key == "items" and isinstance(value, dict):
            out[key] = to_gemini_schema(value)
        elif key in ("required", "description", "enum"):
            out[key] = value
    return out


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        session: requests.Session,
        *,
        pacer: Pacer | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is empty")
        self._api_key = api_key
        self.model = model
        self.session = session
        self.pacer = pacer or Pacer(DEFAULT_INTERVAL)
        self.sleep = sleep

    def __repr__(self) -> str:  # never show the key
        return f"GeminiProvider(model={self.model!r})"

    def _thinking(self) -> dict:
        # Keep thinking to a minimum: it costs output tokens and these tasks are simple.
        if self.model.startswith("gemini-2"):
            return {"thinkingBudget": 0}
        return {"thinkingLevel": "minimal"}

    def generate(
        self, prompt: str, *, schema: dict | None = None, max_tokens: int = 2048, temperature: float = 0.2
    ) -> str:
        config: dict = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "thinkingConfig": self._thinking(),
        }
        if schema is not None:
            config["responseMimeType"] = "application/json"
            config["responseSchema"] = to_gemini_schema(schema)
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": config}
        data = post_json(
            self.session,
            f"{API_ROOT}/models/{self.model}:generateContent",
            name=self.name,
            headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
            body=body,
            pacer=self.pacer,
            sleep=self.sleep,
        )
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise ProviderError(f"gemini: empty response ({reason})")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
