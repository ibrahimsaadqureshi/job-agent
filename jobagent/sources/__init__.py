"""Job sources. Each module exposes one class implementing jobagent.interfaces.Source.

Order matters: in-run dedupe keeps the first source that lists a job, so put the
source with the richest structured data first.

Each source module also exposes a pure `parse(payload) -> list[Job]`, so parsers
are tested against saved fixtures with no network.
"""

from __future__ import annotations

from jobagent.interfaces import Source
from jobagent.sources.himalayas import HimalayasSource
from jobagent.sources.hn import HnSource
from jobagent.sources.remoteok import RemoteOkSource
from jobagent.sources.remotive import RemotiveSource
from jobagent.sources.wwr import WwrSource

ALL_SOURCES: list[Source] = [HimalayasSource(), WwrSource(), RemoteOkSource(), RemotiveSource(), HnSource()]


def get_sources(names: list[str] | None = None) -> list[Source]:
    """All sources, or only the named ones (in registry order). Unknown names raise."""
    if not names:
        return list(ALL_SOURCES)
    known = {s.name: s for s in ALL_SOURCES}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(unknown)}; known: {', '.join(known) or 'none yet'}")
    return [s for s in ALL_SOURCES if s.name in names]
