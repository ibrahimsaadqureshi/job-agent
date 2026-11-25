"""Small helpers shared by the source adapters: HTML to text, dates, salaries."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

_BLANK_LINES = re.compile(r"\n\s*\n+")
_SPACES = re.compile(r"[ \t ]+")


def html_to_text(markup: str | None) -> str:
    """Plain text from an HTML fragment, one paragraph per line."""
    if not markup:
        return ""
    soup = BeautifulSoup(markup, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n")
    text = html.unescape(text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.splitlines()]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def clean(text: object) -> str:
    """A single-line string: unescaped, whitespace collapsed, mojibake repaired."""
    if text is None:
        return ""
    s = fix_mojibake(html.unescape(str(text)))
    return _SPACES.sub(" ", s.replace("\n", " ")).strip()


def fix_mojibake(s: str) -> str:
    """Repair UTF-8 text that was decoded as Latin-1 (e.g. "MÃ¼nchen" -> "München")."""
    if "Ã" not in s and "â€" not in s:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def from_epoch(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def from_iso(value: object) -> datetime | None:
    """ISO 8601 to aware UTC. Naive timestamps are taken as UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def from_rfc822(value: object) -> datetime | None:
    """RSS pubDate ("Wed, 25 Nov 2026 06:03:11 +0000") to aware UTC."""
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}
_PERIODS = {"annual": "year", "yearly": "year", "year": "year", "monthly": "month", "month": "month",
            "weekly": "week", "week": "week", "daily": "day", "day": "day", "hourly": "hour", "hour": "hour"}


def _amount(n: float, symbol: str) -> str:
    if n >= 1000:
        k = n / 1000
        return f"{symbol}{k:.0f}k" if k == int(k) or k >= 10 else f"{symbol}{k:.1f}k"
    return f"{symbol}{n:g}"


def format_salary(low: object, high: object, currency: object = "USD", period: object = "") -> str:
    """"$60k-$80k / year" style text. Zero, missing or unparseable amounts give ""."""

    def num(v: object) -> float:
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0

    lo, hi = num(low), num(high)
    if lo <= 0 and hi <= 0:
        return ""
    code = str(currency or "USD").upper()
    symbol = _SYMBOLS.get(code, f"{code} ")
    if lo > 0 and hi > 0 and lo != hi:
        text = f"{_amount(lo, symbol)}-{_amount(hi, symbol)}"
    else:
        text = _amount(max(lo, hi), symbol)
    unit = _PERIODS.get(str(period or "").lower())
    return f"{text} / {unit}" if unit else text


def as_tags(values: object) -> tuple[str, ...]:
    """Lowercased, de-duplicated tags from a list (or a comma-separated string)."""
    if isinstance(values, str):
        values = re.split(r",|\band\b", values)
    if not isinstance(values, (list, tuple)):
        return ()
    out: list[str] = []
    for v in values:
        t = clean(v).lower().replace("-", " ") if isinstance(v, str) else ""
        if t and t not in out:
            out.append(t)
    return tuple(out)
