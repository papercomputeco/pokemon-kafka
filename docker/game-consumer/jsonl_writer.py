"""Append-only JSONL writer with date-partitioned files."""

import json
from datetime import datetime, timezone
from pathlib import Path


class JSONLWriter:
    """Writes JSON events as newline-delimited JSON to date-partitioned files.

    Files are named YYYY-MM-DD.jsonl under the given base directory.
    """

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._current_date: str | None = None
        self._file = None

    def _rotate_if_needed(self, today: str):
        if today != self._current_date:
            self.close()
            path = self.base_dir / f"{today}.jsonl"
            self._file = open(path, "a", encoding="utf-8")
            self._current_date = today

    def write(self, event: dict):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._rotate_if_needed(today)
        self._file.write(json.dumps(event, separators=(",", ":")) + "\n")
        self._file.flush()

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None
            self._current_date = None
