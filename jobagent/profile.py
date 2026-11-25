"""The candidate profile sent to the LLM: resume text with contact details stripped.

Locally the text comes from the resume PDF at `settings.resume_path` (outside the repo).
In CI it comes from the CANDIDATE_PROFILE secret, which is the output of
`python -m jobagent profile`. Either way, contact details are stripped before the text
goes anywhere else: emails, phone numbers, URLs and bare domains (LinkedIn, GitHub,
company sites), and the name line, which becomes "The candidate".
"""

from __future__ import annotations

import re
from pathlib import Path

from jobagent.config import Settings


class ProfileError(RuntimeError):
    """No usable profile. The message is safe to show: it never contains profile text."""


NAME_PLACEHOLDER = "The candidate"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
# Bare domains such as linkedin.com/in/someone or mycompany.pk. ".js" is not a TLD here,
# so Next.js and Node.js survive; the few tech names that look like domains are kept.
_DOMAIN = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|co|ai|app|me|pk|in|uk|us|xyz|tech|site|info|biz)\b(?:/\S*)?",
    re.IGNORECASE,
)
_TECH_NAMES = frozenset({"socket.io", "asp.net", "ado.net", "vb.net", "dot.net", "web.dev"})
# Phone numbers: 9+ digits with optional +, spaces, dots, dashes and brackets.
_PHONE = re.compile(r"(?<![\w])\+?\(?\d[\d\s().-]{7,}\d(?![\w])")
_LABELS = re.compile(
    r"\b(?:e-?mail|phone|mobile|cell|tel|whatsapp|linkedin|github|portfolio|website)\s*:\s*",
    re.IGNORECASE,
)
_LEFTOVER = re.compile(r"^[\s|•·,;:/\-–—]*$")


def _strip_phone(match: re.Match[str]) -> str:
    text = match.group(0)
    digits = sum(ch.isdigit() for ch in text)
    # Year ranges like "2023 - 2025" have 8 digits; real phone numbers have 9 or more.
    return "" if digits >= 9 else text


def _strip_domain(match: re.Match[str]) -> str:
    return match.group(0) if match.group(0).lower() in _TECH_NAMES else ""


def _looks_like_name(line: str) -> bool:
    words = line.split()
    if not 2 <= len(words) <= 4 or len(line) > 40:
        return False
    return all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", w) for w in words)


def strip_contacts(text: str, *, strip_name: bool = True) -> str:
    """Remove contact details from resume text.

    With strip_name, the first non-empty line is taken as the name if it looks like one
    (2-4 plain words); it becomes "The candidate", and later mentions of the full name or
    its parts are replaced too.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    name_parts: list[str] = []
    if strip_name:
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            candidate = _EMAIL.sub("", line).strip()
            if _looks_like_name(candidate):
                name_parts = candidate.split()
                lines[i] = NAME_PLACEHOLDER
            break

    out: list[str] = []
    for line in lines:
        cleaned = _EMAIL.sub("", line)
        cleaned = _URL.sub("", cleaned)
        cleaned = _DOMAIN.sub(_strip_domain, cleaned)
        cleaned = _PHONE.sub(_strip_phone, cleaned)
        cleaned = _LABELS.sub("", cleaned)
        if name_parts and cleaned != NAME_PLACEHOLDER:
            full = r"\s+".join(re.escape(p) for p in name_parts)
            cleaned = re.sub(rf"\b{full}\b", NAME_PLACEHOLDER, cleaned, flags=re.IGNORECASE)
            for part in name_parts:
                if len(part) >= 3:
                    cleaned = re.sub(rf"\b{re.escape(part)}\b", NAME_PLACEHOLDER, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\(\s*\)|\[\s*\]", "", cleaned)  # brackets that held a link
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
        # Separators left dangling where contact details were: "Lahore | | |" -> "Lahore"
        cleaned = re.sub(r"(?:\s*[|•·]\s*){2,}", " | ", cleaned).strip()
        cleaned = re.sub(r"^(?:[|•·,;]\s*)+|(?:\s*[|•·,;])+$", "", cleaned).strip()
        if line.strip() and _LEFTOVER.match(cleaned):
            continue  # a line that held only contact details
        out.append(cleaned)

    result = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", result).strip()


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise ProfileError("pypdf is not installed. Run: pip install -e '.[resume]'") from exc
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            # Layout mode keeps each visual line together; plain mode can emit one word per line.
            text = page.extract_text(extraction_mode="layout") or ""
        except Exception:
            text = page.extract_text() or ""
        pages.append(text)
    lines = (re.sub(r"\s{2,}", " ", line).strip() for line in "\n".join(pages).splitlines())
    return "\n".join(line for line in lines if line)


def load_profile(settings: Settings) -> str:
    """Contact-stripped profile text: CANDIDATE_PROFILE if set, else the resume PDF."""
    if settings.candidate_profile:
        # Already stripped by `jobagent profile`; strip contact details again just in case,
        # but leave the first line alone (it is no longer a name).
        return strip_contacts(settings.candidate_profile, strip_name=False)
    if not settings.resume_path:
        raise ProfileError(
            "No profile: set CANDIDATE_PROFILE, or resume_path in ~/.config/job-agent/config.toml."
        )
    path = Path(settings.resume_path).expanduser()
    if not path.exists():
        raise ProfileError("The resume_path in ~/.config/job-agent/config.toml does not exist.")
    profile = strip_contacts(extract_pdf_text(path))
    if len(profile) < 200:
        raise ProfileError("The resume PDF gave almost no text (is it a scanned image?).")
    return profile
