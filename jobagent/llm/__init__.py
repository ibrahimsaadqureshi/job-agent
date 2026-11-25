"""LLM providers and the fallback chain.

Chain order: the configured provider (LLM_PROVIDER), then the other hosted one that has
credentials (Gemini <-> GitHub Models), then nothing: jobs nobody could score stay
unscored and are retried on the next run.
"""

from __future__ import annotations

import logging
from typing import Callable, TypeVar

import requests

from jobagent.config import Settings
from jobagent.llm.base import Provider, ProviderError, ProviderUnavailable, RateLimited
from jobagent.llm.gemini import GeminiProvider
from jobagent.llm.github_models import GitHubModelsProvider
from jobagent.llm.ollama import OllamaProvider

log = logging.getLogger("jobagent.llm")

T = TypeVar("T")

PROVIDERS = ("gemini", "github", "ollama")

__all__ = [
    "Provider",
    "ProviderChain",
    "ProviderError",
    "ProviderUnavailable",
    "RateLimited",
    "build_providers",
]


class ProviderChain:
    """Tries each provider in order until one gives a usable result.

    `task(provider)` returns a result, or None when the output was unusable. A provider
    that is out of quota or misconfigured is skipped for the rest of the run, so later
    batches don't waste time on it.
    """

    def __init__(self, providers: list[Provider]):
        if not providers:
            raise ValueError("no LLM provider configured")
        self.providers = list(providers)
        self.disabled: set[str] = set()

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.providers]

    def run(self, task: Callable[[Provider], T | None]) -> T | None:
        for provider in self.providers:
            if provider.name in self.disabled:
                continue
            try:
                result = task(provider)
            except RateLimited as exc:
                log.warning("%s; skipping it for the rest of this run", exc)
                self.disabled.add(provider.name)
                continue
            except ProviderUnavailable as exc:
                log.warning("%s; trying the next provider", exc)
                continue
            except ProviderError as exc:
                log.warning("%s; skipping it for the rest of this run", exc)
                self.disabled.add(provider.name)
                continue
            if result is not None:
                return result
            log.warning("%s gave unusable output; trying the next provider", provider.name)
        return None


def build_providers(settings: Settings, session: requests.Session) -> list[Provider]:
    """Providers in fallback order. Empty if nothing is configured."""
    configured = settings.llm_provider
    if configured not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER must be one of {', '.join(PROVIDERS)}, got {configured!r}")

    def make(name: str) -> Provider | None:
        if name == "gemini" and settings.gemini_api_key:
            return GeminiProvider(settings.gemini_api_key, settings.gemini_model, session)
        if name == "github" and settings.github_token:
            return GitHubModelsProvider(settings.github_token, settings.github_model, session)
        if name == "ollama":
            return OllamaProvider(settings.ollama_model, session, base_url=settings.ollama_url)
        return None

    order = [configured] + [n for n in ("gemini", "github") if n != configured]
    providers = [p for p in (make(n) for n in order) if p is not None]
    if providers and providers[0].name != configured:
        log.warning("LLM_PROVIDER=%s has no credentials; using %s", configured, providers[0].name)
    return providers
