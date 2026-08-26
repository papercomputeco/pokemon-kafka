"""Read-only index over the runs/ directory."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class RunSummary:
    run_id: str
    status: str
    turns: int
    battles_won: int
    maps_visited: int
    badges: int
    frame_count: int
    thumbnail: str | None
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _is_run_dir(path: Path) -> bool:
    """Playable runs only — what `recorder.start` lays down before turn 1.

    Other things live in a runs dir: the fan-out writes fitness JSONs to
    runs/fanout-proof/, and demo-runs/ carries a states/ dir. Listing those put
    a frameless, turn-0 entry at the top of the gallery whose feed was nothing
    but the global alerts tail, since `build_feed` had no events to merge.
    """
    return (path / "events.jsonl").exists() or (path / "frames").is_dir()


def _natural_key(name: str) -> list:
    """Digit-aware sort, so beat10 lands above beat9 rather than beside beat1.

    `re.split` on a capturing digit group always alternates text/number and
    always starts with text, so two keys compare type-for-type at every index.
    """
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


class RunStore:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = Path(runs_dir)

    def _run_dirs(self) -> list[Path]:
        if not self.runs_dir.is_dir():
            return []
        return sorted(
            (p for p in self.runs_dir.iterdir() if p.is_dir() and _is_run_dir(p)),
            key=lambda p: _natural_key(p.name),
            reverse=True,
        )

    def get_summary(self, run_id: str) -> dict:
        path = self.runs_dir / run_id / "summary.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}

    def frame_names(self, run_id: str) -> list[str]:
        frames = self.runs_dir / run_id / "frames"
        if not frames.is_dir():
            return []
        return sorted(p.name for p in frames.glob("*.png"))

    def load_events(self, run_id: str) -> list[dict]:
        path = self.runs_dir / run_id / "events.jsonl"
        if not path.exists():
            return []
        out: list[dict] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def get_meta(self, run_id: str) -> dict:
        path = self.runs_dir / run_id / "meta.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}

    def _summary_for(self, run_id: str) -> RunSummary:
        summary = self.get_summary(run_id)
        frames = self.frame_names(run_id)
        status = "done" if (self.runs_dir / run_id / "summary.json").exists() else "live"
        label = self.get_meta(run_id).get("label") or summary.get("params", {}).get("label", "")
        return RunSummary(
            run_id=run_id,
            status=status,
            turns=int(summary.get("turns", 0)),
            battles_won=int(summary.get("battles_won", 0)),
            maps_visited=int(summary.get("maps_visited", 0)),
            badges=int(summary.get("badges", 0)),
            frame_count=len(frames),
            thumbnail=frames[-1] if frames else None,
            label=str(label or ""),
        )

    def list_runs(self) -> list[RunSummary]:
        return [self._summary_for(p.name) for p in self._run_dirs()]
