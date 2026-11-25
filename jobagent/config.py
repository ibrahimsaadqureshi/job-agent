"""All configuration in one place.

Nothing personal lives in the repo. Everything local lives in one folder outside it,
JOBAGENT_HOME (default ~/.config/job-agent/), so it survives new clones and worktrees:

    ~/.config/job-agent/.env          secrets (same names as .env.example)
    ~/.config/job-agent/config.toml   local-only settings, e.g. resume_path
    ~/.config/job-agent/state/        --local / --dry-run run state

In GitHub Actions the same secrets arrive as environment variables. Real environment
variables always win over the .env file.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
USER_DIR = Path(os.environ.get("JOBAGENT_HOME", "~/.config/job-agent")).expanduser()
STATE_DIR = USER_DIR / "state"


@dataclass(frozen=True)
class Settings:
    # Secrets / credentials (empty string = not configured)
    gemini_api_key: str = ""
    google_service_account_json: str = ""
    sheet_id: str = ""
    slack_webhook_url: str = ""
    candidate_profile: str = ""
    github_token: str = ""  # GitHub Models fallback; CI passes the built-in GITHUB_TOKEN

    # Local-only
    resume_path: str = ""

    # Behaviour
    llm_provider: str = "gemini"  # gemini | github | ollama
    gemini_model: str = "gemini-3.1-flash-lite"  # cheapest current Flash-class model (2026-11-25)
    github_model: str = "openai/gpt-4.1-mini"
    ollama_model: str = "qwen2.5:7b"
    ollama_url: str = "http://127.0.0.1:11434"
    score_threshold: int = 70  # min score for a draft note and a digest slot
    digest_max_jobs: int = 12
    score_batch_size: int = 10  # jobs per scoring request
    max_drafts_per_run: int = 12
    description_chars: int = 1000  # description length sent to the scorer
    max_scored_per_run: int = 100  # default --limit, so a backfill spreads over several days

    @property
    def sheet_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}" if self.sheet_id else ""

    def missing(self, *names: str) -> list[str]:
        """Names of the given settings that are empty, e.g. missing("sheet_id")."""
        return [n for n in names if not getattr(self, n)]


def _int(env: dict[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc


def load_settings(
    env: dict[str, str] | None = None,
    local_config: Path | None = None,
    dotenv: Path | None = None,
) -> Settings:
    """Build Settings from the environment (+ USER_DIR/.env) and USER_DIR/config.toml.

    Real environment variables win over .env values, so CI secrets always apply.
    """
    if env is None:
        env = dict(os.environ)
        dotenv_path = dotenv if dotenv is not None else USER_DIR / ".env"
        if dotenv_path.exists():
            from dotenv import dotenv_values

            file_values = {k: v for k, v in dotenv_values(dotenv_path).items() if v is not None}
            env = {**file_values, **env}

    local_path = local_config if local_config is not None else USER_DIR / "config.toml"
    local: dict = {}
    if local_path.exists():
        local = tomllib.loads(local_path.read_text(encoding="utf-8"))

    return Settings(
        gemini_api_key=env.get("GEMINI_API_KEY", "").strip(),
        google_service_account_json=env.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip(),
        sheet_id=env.get("SHEET_ID", "").strip(),
        slack_webhook_url=env.get("SLACK_WEBHOOK_URL", "").strip(),
        candidate_profile=env.get("CANDIDATE_PROFILE", "").strip(),
        github_token=(env.get("GITHUB_MODELS_TOKEN", "") or env.get("GITHUB_TOKEN", "")).strip(),
        resume_path=str(local.get("resume_path", "")).strip(),
        llm_provider=env.get("LLM_PROVIDER", "gemini").strip().lower() or "gemini",
        gemini_model=env.get("GEMINI_MODEL", "").strip() or Settings.gemini_model,
        github_model=env.get("GITHUB_MODELS_MODEL", "").strip() or Settings.github_model,
        ollama_model=env.get("OLLAMA_MODEL", "").strip() or Settings.ollama_model,
        ollama_url=env.get("OLLAMA_URL", "").strip() or Settings.ollama_url,
        score_threshold=_int(env, "SCORE_THRESHOLD", 70),
        digest_max_jobs=_int(env, "DIGEST_MAX_JOBS", 12),
        score_batch_size=_int(env, "SCORE_BATCH_SIZE", 10),
        max_drafts_per_run=_int(env, "MAX_DRAFTS", 12),
        description_chars=_int(env, "DESCRIPTION_CHARS", 1000),
        max_scored_per_run=_int(env, "MAX_SCORED_PER_RUN", 100),
    )
