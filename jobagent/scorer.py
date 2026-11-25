"""LLM fit scoring and note drafting: the production `Scorer`.

- score(): jobs go out in batches of `batch_size`. Each job is sent as a short JSON object
  (short id, title, company, location + location rule, category, salary, years-asked hint,
  the start of the description). The reply must be [{id, score, reason}]; it is validated
  item by item, and bad items are dropped rather than failing the batch.
- draft(): one plain-text note per job.

Both go through a ProviderChain, so a provider that is down or out of quota falls back
to the next one, and a job nobody could score simply stays unscored until the next run.
Logs carry counts only.
"""

from __future__ import annotations

import json
import logging
import re
from importlib.resources import files

from jobagent import filters
from jobagent.llm import ProviderChain
from jobagent.llm.base import Provider
from jobagent.models import Job
from jobagent.profile import strip_contacts

log = logging.getLogger("jobagent.scorer")

REASON_MAX = 140
DRAFT_MIN_WORDS = 50
DRAFT_MAX_WORDS = 130  # the prompt asks for 80-120; trim anything longer at a sentence end

SCORE_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "score": {"type": "integer"},
            "reason": {"type": "string"},
        },
        "required": ["id", "score", "reason"],
    },
}


class DraftError(RuntimeError):
    """No provider produced a usable draft. The pipeline skips the note for that job."""


def load_prompt(name: str) -> str:
    return (files("jobagent") / "prompts" / f"{name}.txt").read_text(encoding="utf-8")


def fill(template: str, **values: str) -> str:
    """Replace {name} placeholders. Not str.format: the templates contain JSON braces."""
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


def truncate(text: str, limit: int) -> str:
    """Collapse whitespace and cut to at most `limit` characters at a word boundary."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:.-") + "…"


# --- Score prompt ----------------------------------------------------------------------


def job_payload(job: Job, key: str, description_chars: int) -> dict:
    verdict = filters.evaluate(job)
    years = filters.required_years(job.description)
    return {
        "id": key,
        "title": job.title,
        "company": job.company,
        "location": job.location or "not stated",
        "location_rule": verdict.location_rule or "unspecified",
        "category": verdict.category.value if verdict.category else "",
        "salary": job.salary or "not listed",
        "required_years": years if years is not None else "not stated",
        "description": truncate(job.description, description_chars),
    }


def build_score_prompt(template: str, profile: str, payloads: list[dict]) -> str:
    jobs = "\n".join(json.dumps(p, ensure_ascii=False) for p in payloads)
    return fill(template, profile=profile.strip(), jobs=jobs)


# --- Output validation -----------------------------------------------------------------

_FENCE = re.compile(r"```(?:json|JSON)?\s*|```")


def _decode_items(text: str) -> list:
    """Pull a list of JSON objects out of model text: fences, prose and truncation allowed."""
    text = _FENCE.sub("", text).strip()
    if not text:
        return []
    decoder = json.JSONDecoder()
    for start, ch in enumerate(text):
        if ch not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text, start)
        except ValueError:
            break  # truncated or broken: salvage the complete objects below
        if isinstance(value, list) and any(isinstance(v, dict) for v in value):
            return value
        if isinstance(value, dict):
            if "id" in value:
                return [value]
            for inner in value.values():  # {"scores": [...]} or similar
                if isinstance(inner, list):
                    return inner
        # Something like "[1]" in the prose: keep looking.
    items = []
    pos = text.find("{")
    while pos != -1:
        try:
            value, end = decoder.raw_decode(text, pos)
        except ValueError:
            pos = text.find("{", pos + 1)
            continue
        if isinstance(value, dict):
            items.append(value)
        pos = text.find("{", end)
    return items


def _as_score(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        score = value
    elif isinstance(value, float) and value.is_integer():
        score = int(value)
    elif isinstance(value, str) and re.fullmatch(r"\s*\d{1,3}\s*", value):
        score = int(value)
    else:
        return None
    return score if 0 <= score <= 100 else None


def parse_scores(text: str, allowed_ids: set[str]) -> dict[str, tuple[int, str]]:
    """Validated {id: (score, reason)} from a model reply. Bad or unknown items are dropped."""
    out: dict[str, tuple[int, str]] = {}
    for item in _decode_items(text):
        if not isinstance(item, dict):
            continue
        key = item.get("id")
        if not isinstance(key, str) or key.strip() not in allowed_ids or key.strip() in out:
            continue
        score = _as_score(item.get("score"))
        reason = item.get("reason")
        if score is None or not isinstance(reason, str) or not reason.strip():
            continue
        out[key.strip()] = (score, truncate(reason, REASON_MAX))
    return out


# --- Draft -----------------------------------------------------------------------------

_SIGN_OFF = re.compile(r"^(best|regards|kind regards|thanks|thank you|sincerely|cheers)\b.*$", re.I)
_GREETING = re.compile(r"^(dear|hi|hello)\b[^\n]*[,:]?\s*$", re.I)


def build_draft_prompt(template: str, job: Job, profile: str, reason: str, description_chars: int) -> str:
    return fill(
        template,
        profile=profile.strip(),
        title=job.title,
        company=job.company,
        location=job.location or "not stated",
        description=truncate(job.description, description_chars),
        reason=reason or "not given",
    )


def clean_draft(text: str) -> str:
    """Plain-text note, contact details removed, trimmed to the word limit. "" if unusable."""
    text = _FENCE.sub("", text).strip().strip('"').strip()
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line and not line.lower().startswith("subject:")]
    while lines and _GREETING.match(lines[0]):
        lines.pop(0)
    while lines and (_SIGN_OFF.match(lines[-1]) or lines[-1].lower().strip(".,") == "the candidate"):
        lines.pop()
    text = "\n".join(lines)
    text = re.sub(r"\[[^\]]{1,40}\]", "", text)  # [Name], [Company] placeholders
    text = re.sub(r"[*_#`]+", "", text)  # stray markdown
    text = strip_contacts(text, strip_name=False)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text).strip()

    words = text.split()
    if len(words) < DRAFT_MIN_WORDS:
        return ""
    if len(words) > DRAFT_MAX_WORDS:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        kept: list[str] = []
        for sentence in sentences:
            if len(" ".join(kept + [sentence]).split()) > DRAFT_MAX_WORDS:
                break
            kept.append(sentence)
        text = " ".join(kept).strip()
        if len(text.split()) < DRAFT_MIN_WORDS:
            return ""
    return text


# --- The scorer ------------------------------------------------------------------------


class LLMScorer:
    """Implements interfaces.Scorer on top of a ProviderChain."""

    def __init__(
        self,
        chain: ProviderChain,
        *,
        batch_size: int = 10,
        description_chars: int = 1000,
        draft_description_chars: int = 2500,
        score_template: str | None = None,
        draft_template: str | None = None,
    ):
        self.chain = chain
        self.batch_size = max(1, batch_size)
        self.description_chars = description_chars
        self.draft_description_chars = draft_description_chars
        self.score_template = score_template or load_prompt("score")
        self.draft_template = draft_template or load_prompt("draft")

    def score(self, jobs: list[Job], profile: str) -> dict[str, tuple[int, str]]:
        results: dict[str, tuple[int, str]] = {}
        batches = [jobs[i : i + self.batch_size] for i in range(0, len(jobs), self.batch_size)]
        for n, batch in enumerate(batches, 1):
            by_key = {f"j{i}": job for i, job in enumerate(batch, 1)}
            prompt = build_score_prompt(
                self.score_template,
                profile,
                [job_payload(job, key, self.description_chars) for key, job in by_key.items()],
            )

            def task(provider: Provider) -> dict[str, tuple[int, str]] | None:
                # Unusable output gets one retry on the same provider, then the next provider.
                for _ in range(2):
                    text = provider.generate(prompt, schema=SCORE_SCHEMA, max_tokens=200 * len(batch) + 200)
                    parsed = parse_scores(text, set(by_key))
                    if parsed:
                        return parsed
                return None

            parsed = self.chain.run(task) or {}
            for key, value in parsed.items():
                results[by_key[key].id] = value
            log.info("score batch %d/%d: %d of %d scored", n, len(batches), len(parsed), len(batch))
        return results

    def draft(self, job: Job, profile: str, reason: str) -> str:
        prompt = build_draft_prompt(self.draft_template, job, profile, reason, self.draft_description_chars)

        def task(provider: Provider) -> str | None:
            for _ in range(2):
                note = clean_draft(provider.generate(prompt, max_tokens=500, temperature=0.4))
                if note:
                    return note
            return None

        note = self.chain.run(task)
        if note is None:
            raise DraftError("no provider produced a usable draft")
        return note
