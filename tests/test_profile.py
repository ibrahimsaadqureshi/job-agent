"""Contact stripping and profile loading. Synthetic resume only: no real personal data."""

import pytest

from jobagent import cli
from jobagent import profile as profile_mod
from jobagent.config import Settings
from jobagent.profile import ProfileError, load_profile, strip_contacts

SYNTHETIC_RESUME = """Jane Q Example
Full-Stack Developer · TypeScript, React, Node.js, Next.js
Springfield, Freedonia | jane.example@mail.test | +12-345-6789012 | linkedin.com/in/jane-example-123
Portfolio: https://jane.example.dev | github.com/janeexample
Summary
Full-stack developer at Acme Widgets (acmewidgets.com) since 2024. Built a booking platform with
NestJS, MongoDB and Socket.io for 3,000 users. Jane also ships n8n automations and ASP.NET fixes.
Experience
Acme Widgets — Full-Stack Developer, Jun 2025 - Present
Phone: (012) 345-6789 · Email: jane@acme.test
Education
BSc Computer Science, 2020 - 2024
"""


def test_strips_email_phone_urls_and_domains():
    out = strip_contacts(SYNTHETIC_RESUME)
    for secret in (
        "jane.example@mail.test",
        "jane@acme.test",
        "+12-345-6789012",
        "345-6789",
        "linkedin.com",
        "jane-example-123",
        "https://",
        "jane.example.dev",
        "github.com/janeexample",
        "acmewidgets.com",
    ):
        assert secret not in out, secret


def test_name_line_becomes_placeholder_and_later_mentions_too():
    out = strip_contacts(SYNTHETIC_RESUME)
    assert out.splitlines()[0] == "The candidate"
    assert "Jane" not in out
    assert "Example" not in out
    assert "The candidate also ships n8n automations" in out


def test_keeps_skills_dates_and_tech_names_that_look_like_domains():
    out = strip_contacts(SYNTHETIC_RESUME)
    for kept in ("Next.js", "Node.js", "Socket.io", "ASP.NET", "3,000 users", "2020 - 2024", "Jun 2025"):
        assert kept in out, kept
    assert "Springfield, Freedonia" in out


def test_lines_with_only_contact_details_disappear_and_separators_are_tidied():
    out = strip_contacts(SYNTHETIC_RESUME)
    assert "Portfolio" not in out
    assert "Phone" not in out and "Email" not in out
    assert not any(line.rstrip().endswith("|") for line in out.splitlines())


def test_strip_name_off_leaves_first_line_alone():
    text = "Senior Skills Summary\nWrite to me at someone@mail.test"
    out = strip_contacts(text, strip_name=False)
    assert out.splitlines()[0] == "Senior Skills Summary"
    assert "@" not in out


def test_first_line_that_is_not_a_name_is_kept():
    out = strip_contacts("Full-Stack Developer with 2 years of TypeScript\nMore text")
    assert out.splitlines()[0] == "Full-Stack Developer with 2 years of TypeScript"


def test_env_profile_wins_and_is_still_stripped():
    s = Settings(candidate_profile="The candidate\nReach me: a@b.test\nReact developer", resume_path="/nope.pdf")
    out = load_profile(s)
    assert "a@b.test" not in out
    assert "React developer" in out


def test_missing_profile_is_a_clear_error(tmp_path):
    with pytest.raises(ProfileError, match="CANDIDATE_PROFILE"):
        load_profile(Settings())
    with pytest.raises(ProfileError, match="does not exist"):
        load_profile(Settings(resume_path=str(tmp_path / "missing.pdf")))


def test_resume_pdf_path_goes_through_pdf_extraction_then_stripping(tmp_path, monkeypatch):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-fake")
    monkeypatch.setattr(profile_mod, "extract_pdf_text", lambda path: SYNTHETIC_RESUME * 2)
    out = load_profile(Settings(resume_path=str(pdf)))
    assert out.startswith("The candidate")
    assert "@" not in out


def test_profile_command_prints_stripped_profile(tmp_path, monkeypatch, capsys):
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF-fake")
    monkeypatch.setattr(profile_mod, "extract_pdf_text", lambda path: SYNTHETIC_RESUME)
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(resume_path=str(pdf)))
    assert cli.main(["profile"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("The candidate")
    assert "jane.example@mail.test" not in captured.out
    assert "NestJS" in captured.out
    assert "CANDIDATE_PROFILE" in captured.err  # instructions go to stderr, not into the paste


def test_profile_command_without_a_profile_fails_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_settings", lambda: Settings())
    assert cli.main(["profile"]) == 2
    assert "error:" in capsys.readouterr().err
