"""Local stand-ins for the Sheet and Slack, used by --dry-run and --local runs.

- LocalTracker keeps seen ids in .state/seen.json and rows in .state/rows.csv,
  so cross-run dedupe can be exercised before any Google account exists.
- ConsoleNotifier prints the digest instead of posting it.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Callable

from jobagent.digest import render_text
from jobagent.interfaces import Digest
from jobagent.models import SHEET_COLUMNS, TrackerRow


class LocalTracker:
    """File-backed tracker. With persist=False (dry-run) it reads but never writes."""

    def __init__(self, state_dir: Path, *, persist: bool, out: Callable[[str], None] = print):
        self.state_dir = state_dir
        self.persist = persist
        self.out = out
        self.seen_path = state_dir / "seen.json"
        self.rows_path = state_dir / "rows.csv"

    def seen_ids(self) -> set[str]:
        if not self.seen_path.exists():
            return set()
        return set(json.loads(self.seen_path.read_text(encoding="utf-8")))

    def append(self, rows: list[TrackerRow]) -> None:
        if not self.persist:
            self.out(f"[dry-run] would append {len(rows)} row(s) to the tracker")
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        new_file = not self.rows_path.exists()
        with self.rows_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow(SHEET_COLUMNS)
            for row in rows:
                writer.writerow(row.as_list())
        seen = self.seen_ids() | {r.id for r in rows}
        self.seen_path.write_text(json.dumps(sorted(seen), indent=0), encoding="utf-8")
        self.out(f"[local] appended {len(rows)} row(s) to {self.rows_path}")


class ConsoleNotifier:
    def __init__(self, out: Callable[[str], None] = print):
        self.out = out

    def send(self, digest: Digest) -> None:
        self.out("-" * 60)
        self.out(render_text(digest))
        self.out("-" * 60)

    def send_failure(self, message: str) -> None:
        self.out(f"[failure notice] {message}")
