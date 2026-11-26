"""LLM providers and the fallback chain, against a fake HTTP layer (no network)."""

import pytest
import requests

from jobagent.config import Settings
from jobagent.llm import ProviderChain, build_providers
from jobagent.llm.base import Pacer, ProviderError, ProviderUnavailable, RateLimited, post_json
from jobagent.llm.gemini import GeminiProvider, to_gemini_schema
from jobagent.llm.github_models import GitHubModelsProvider
from jobagent.llm.ollama import OllamaProvider

KEY = "test-key-not-real-123"


class FakeResponse:
    def __init__(self, status: int, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self):
        if isinstance(self._body, (dict, list)):
            return self._body
        raise ValueError("not json")


class FakeSession:
    """Returns queued responses (or raises queued exceptions) and records every call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def gemini_ok(text: str) -> FakeResponse:
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


def no_pace() -> Pacer:
    return Pacer(0.0, sleep=lambda s: None)


def gemini(session, sleeps=None) -> GeminiProvider:
    sleeps = sleeps if sleeps is not None else []
    return GeminiProvider(KEY, "gemini-test-flash", session, pacer=no_pace(), sleep=sleeps.append)


# --- Gemini request shape ---------------------------------------------------------------


def test_gemini_sends_key_in_header_never_in_url():
    session = FakeSession(gemini_ok("[]"))
    gemini(session).generate("hello", schema={"type": "array", "items": {"type": "object"}})
    call = session.calls[0]
    assert call["headers"]["x-goog-api-key"] == KEY
    assert KEY not in call["url"]
    assert call["url"].endswith("/models/gemini-test-flash:generateContent")
    config = call["json"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseSchema"] == {"type": "ARRAY", "items": {"type": "OBJECT"}}


def test_gemini_repr_and_errors_never_show_the_key():
    session = FakeSession(FakeResponse(400, {"error": {"message": f"bad key {KEY}"}}))
    provider = gemini(session)
    assert KEY not in repr(provider)
    with pytest.raises(ProviderError) as info:
        provider.generate("hello")
    assert KEY not in str(info.value)


def test_gemini_plain_text_mode_has_no_schema_and_skips_thought_parts():
    body = {"candidates": [{"content": {"parts": [{"text": "thinking", "thought": True}, {"text": "note"}]}}]}
    session = FakeSession(FakeResponse(200, body))
    assert gemini(session).generate("hello") == "note"
    assert "responseSchema" not in session.calls[0]["json"]["generationConfig"]


def test_gemini_blocked_prompt_is_a_provider_error():
    session = FakeSession(FakeResponse(200, {"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(ProviderError, match="SAFETY"):
        gemini(session).generate("hello")


def test_to_gemini_schema_uppercases_nested_types():
    schema = {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}
    assert to_gemini_schema(schema) == {
        "type": "ARRAY",
        "items": {"type": "OBJECT", "properties": {"id": {"type": "STRING"}}, "required": ["id"]},
    }


# --- 429 / 5xx handling -----------------------------------------------------------------


def test_429_then_success_retries_once_after_server_delay():
    retry_info = {"error": {"details": [{"@type": "RetryInfo", "retryDelay": "3s"}]}}
    session = FakeSession(FakeResponse(429, retry_info), gemini_ok("ok"))
    sleeps = []
    assert gemini(session, sleeps).generate("hello") == "ok"
    assert len(session.calls) == 2
    assert sleeps == [3.0]


def test_429_twice_gives_up_as_rate_limited():
    session = FakeSession(FakeResponse(429, {}), FakeResponse(429, {}), gemini_ok("never reached"))
    with pytest.raises(RateLimited):
        gemini(session).generate("hello")
    assert len(session.calls) == 2  # at most one retry


def test_429_with_a_long_delay_gives_up_at_once():
    # Gemini says "retry in 40 minutes" when the daily quota is gone: don't wait for it.
    retry_info = {"error": {"details": [{"retryDelay": "2400s"}]}}
    session = FakeSession(FakeResponse(429, retry_info), gemini_ok("never reached"))
    sleeps = []
    with pytest.raises(RateLimited):
        gemini(session, sleeps).generate("hello")
    assert len(session.calls) == 1
    assert sleeps == []


def test_retry_after_header_is_used():
    session = FakeSession(FakeResponse(503, None, {"Retry-After": "2"}), gemini_ok("ok"))
    sleeps = []
    gemini(session, sleeps).generate("hello")
    assert sleeps == [2.0]


def test_5xx_twice_is_unavailable_but_not_rate_limited():
    session = FakeSession(FakeResponse(500), FakeResponse(502))
    with pytest.raises(ProviderUnavailable) as info:
        gemini(session).generate("hello")
    assert not isinstance(info.value, RateLimited)


def test_network_error_is_retried_once():
    session = FakeSession(requests.ConnectionError("down"), gemini_ok("ok"))
    assert gemini(session).generate("hello") == "ok"


def test_400_is_not_retried():
    session = FakeSession(FakeResponse(400, {}), gemini_ok("never"))
    with pytest.raises(ProviderError):
        gemini(session).generate("hello")
    assert len(session.calls) == 1


def test_non_json_success_is_a_provider_error():
    session = FakeSession(FakeResponse(200, "OK"))
    with pytest.raises(ProviderError, match="not JSON"):
        post_json(session, "https://x.test", name="x", headers={}, body={}, pacer=no_pace())


# --- Pacing -----------------------------------------------------------------------------


def test_pacer_spaces_requests():
    now = [100.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    pacer = Pacer(6.0, clock=lambda: now[0], sleep=sleep)
    pacer.wait()  # first call: no wait
    now[0] += 1.0
    pacer.wait()  # 1 s later: waits the other 5 s
    now[0] += 10.0
    pacer.wait()  # 10 s later: no wait
    assert sleeps == [5.0]


# --- Other providers --------------------------------------------------------------------


def test_github_models_request_and_response():
    body = {"choices": [{"message": {"content": "[1]"}}]}
    session = FakeSession(FakeResponse(200, body))
    provider = GitHubModelsProvider("gh-token", "openai/gpt-4.1-mini", session, pacer=no_pace())
    assert provider.generate("hello") == "[1]"
    call = session.calls[0]
    assert call["url"] == "https://models.github.ai/inference/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer gh-token"
    assert call["json"]["model"] == "openai/gpt-4.1-mini"
    assert "gh-token" not in repr(provider)


def test_ollama_request_and_response():
    session = FakeSession(FakeResponse(200, {"message": {"content": "hi"}}))
    provider = OllamaProvider("qwen2.5:7b", session)
    schema = {"type": "array"}
    assert provider.generate("hello", schema=schema) == "hi"
    call = session.calls[0]
    assert call["url"] == "http://127.0.0.1:11434/api/chat"
    assert call["json"]["format"] == schema
    assert call["json"]["stream"] is False


# --- Building the chain -----------------------------------------------------------------


def names(settings):
    return [p.name for p in build_providers(settings, FakeSession())]


def test_chain_order_from_settings():
    assert names(Settings(gemini_api_key="k", github_token="t")) == ["gemini", "gemini-backup", "github"]
    assert names(Settings(gemini_api_key="k", github_token="t", llm_provider="github")) == [
        "github",
        "gemini",
        "gemini-backup",
    ]
    assert names(Settings(gemini_api_key="k", llm_provider="ollama")) == ["ollama", "gemini", "gemini-backup"]
    assert names(Settings(gemini_api_key="k")) == ["gemini", "gemini-backup"]
    assert names(Settings(github_token="t")) == ["github"]  # no Gemini key: GitHub alone
    assert names(Settings()) == []


def test_backup_gemini_uses_its_own_model_and_can_be_turned_off():
    providers = build_providers(Settings(gemini_api_key="k"), FakeSession())
    assert [p.model for p in providers] == ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    assert names(Settings(gemini_api_key="k", gemini_backup_model="")) == ["gemini"]
    # A backup that is the same model as the main one would share its quota: skipped.
    same = Settings(gemini_api_key="k", gemini_model="m", gemini_backup_model="m")
    assert names(same) == ["gemini"]


def test_overloaded_main_model_falls_back_to_the_backup_model():
    # Main model: 503, then 503 again on its one retry. Backup model: answers.
    session = FakeSession(FakeResponse(503), FakeResponse(503), gemini_ok("from backup"))
    main = GeminiProvider(KEY, "main-model", session, pacer=no_pace(), sleep=lambda s: None)
    backup = GeminiProvider(KEY, "backup-model", session, name="gemini-backup", pacer=no_pace(), sleep=lambda s: None)
    chain = ProviderChain([main, backup])
    assert run_text(chain) == "from backup"
    assert [c["url"].rsplit("/", 1)[-1] for c in session.calls] == [
        "main-model:generateContent",
        "main-model:generateContent",
        "backup-model:generateContent",
    ]
    assert chain.disabled == set()  # a 503 is temporary: the main model is tried again next batch


def test_unknown_provider_is_a_clear_error():
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        build_providers(Settings(llm_provider="openai"), FakeSession())


# --- ProviderChain ----------------------------------------------------------------------


class ScriptedProvider:
    """Each generate() call pops the next item: text to return, or an exception to raise."""

    def __init__(self, name, *script):
        self.name = name
        self.script = list(script)
        self.calls = 0

    def generate(self, prompt, *, schema=None, max_tokens=2048, temperature=0.2):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def run_text(chain):
    return chain.run(lambda p: p.generate("x") or None)


def test_chain_uses_first_provider_when_it_works():
    a, b = ScriptedProvider("a", "from a"), ScriptedProvider("b", "from b")
    assert run_text(ProviderChain([a, b])) == "from a"
    assert b.calls == 0


def test_chain_falls_back_on_rate_limit_and_skips_that_provider_afterwards():
    a = ScriptedProvider("a", RateLimited("a: 429"))
    b = ScriptedProvider("b", "b1", "b2")
    chain = ProviderChain([a, b])
    assert run_text(chain) == "b1"
    assert run_text(chain) == "b2"
    assert a.calls == 1  # not retried on the second task


def test_chain_falls_back_on_5xx_but_tries_that_provider_again_next_time():
    a = ScriptedProvider("a", ProviderUnavailable("a: 503"), "a2")
    b = ScriptedProvider("b", "b1")
    chain = ProviderChain([a, b])
    assert run_text(chain) == "b1"
    assert run_text(chain) == "a2"


def test_chain_falls_back_on_unusable_output():
    a, b = ScriptedProvider("a", ""), ScriptedProvider("b", "good")
    assert run_text(ProviderChain([a, b])) == "good"


def test_chain_returns_none_when_every_provider_fails():
    a = ScriptedProvider("a", RateLimited("a"))
    b = ScriptedProvider("b", ProviderError("b: HTTP 401"))
    chain = ProviderChain([a, b])
    assert run_text(chain) is None
    assert chain.disabled == {"a", "b"}
    assert run_text(chain) is None  # nothing left to try, and no more calls made
    assert a.calls == 1 and b.calls == 1


def test_chain_needs_at_least_one_provider():
    with pytest.raises(ValueError):
        ProviderChain([])

