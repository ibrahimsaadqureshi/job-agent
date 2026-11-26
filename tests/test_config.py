import pytest

from jobagent.config import load_settings


def test_defaults_with_empty_env(tmp_path):
    s = load_settings(env={}, local_config=tmp_path / "missing.toml")
    assert s.score_threshold == 70
    assert s.llm_provider == "gemini"
    assert s.sheet_url == ""
    assert s.missing("sheet_id", "slack_webhook_url") == ["sheet_id", "slack_webhook_url"]


def test_env_values_and_local_config(tmp_path):
    local = tmp_path / "config.toml"
    local.write_text('resume_path = "/tmp/resume.pdf"\n', encoding="utf-8")
    s = load_settings(
        env={"SHEET_ID": " abc ", "SCORE_THRESHOLD": "80", "LLM_PROVIDER": "Ollama"},
        local_config=local,
    )
    assert s.sheet_id == "abc"
    assert s.sheet_url.endswith("/abc")
    assert s.score_threshold == 80
    assert s.llm_provider == "ollama"
    assert s.resume_path == "/tmp/resume.pdf"


def test_bad_integer_is_a_clear_error(tmp_path):
    with pytest.raises(ValueError, match="SCORE_THRESHOLD"):
        load_settings(env={"SCORE_THRESHOLD": "high"}, local_config=tmp_path / "x.toml")


def test_real_env_wins_over_dotenv(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("SHEET_ID=from-file\nSLACK_WEBHOOK_URL=hook-from-file\n", encoding="utf-8")
    monkeypatch.setenv("SHEET_ID", "from-env")
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    s = load_settings(dotenv=dotenv, local_config=tmp_path / "x.toml")
    assert s.sheet_id == "from-env"
    assert s.slack_webhook_url == "hook-from-file"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", "gemini-3.5-flash-lite"),  # blank: the default backup
        ("gemini-x-lite", "gemini-x-lite"),
        ("none", ""),
        ("OFF", ""),
        ("false", ""),
    ],
)
def test_gemini_backup_model_setting(tmp_path, raw, expected):
    s = load_settings(env={"GEMINI_BACKUP_MODEL": raw}, local_config=tmp_path / "x.toml")
    assert s.gemini_backup_model == expected
