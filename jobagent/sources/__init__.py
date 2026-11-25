"""Job sources. Each module exposes one class implementing jobagent.interfaces.Source.

Order matters: in-run dedupe keeps the first source that lists a job, so put the
source with the richest structured data first.

Lane A (M1) adds: himalayas, wwr, remoteok, remotive, hn.
"""

from __future__ import annotations

from jobagent.interfaces import Source

ALL_SOURCES: list[Source] = []


def get_sources(names: list[str] | None = None) -> list[Source]:
    """All sources, or only the named ones (in registry order). Unknown names raise."""
    if not names:
        return list(ALL_SOURCES)
    known = {s.name: s for s in ALL_SOURCES}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(unknown)}; known: {', '.join(known) or 'none yet'}")
    return [s for s in ALL_SOURCES if s.name in names]
