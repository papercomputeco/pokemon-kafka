"""Draft the discovery-engine prompt for a recorded run — backs the HEAL button.

An operator arms an anomaly in the feed, writes what the agent got wrong, and
gets back the prompt `scripts/discovery.py` would hand its proposer — the same
text the unattended escalation path builds. Assembling it is string work over
files already on disk, so unlike a heal race this answers inline: no job table,
no background thread, no polling.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from viewer.heal import KNOWN_RULES, validate_run_target

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DISCOVERY_SCRIPT = _REPO_ROOT / "scripts" / "discovery.py"

# discovery.py's own default for a hand-raised problem with no rule attached —
# and a valid explicit choice here, unlike for a heal race.
FALLBACK_RULE = "manual"
ALLOWED_RULES = KNOWN_RULES | {FALLBACK_RULE}


def compose_detail(note: str, anomaly: str) -> str:
    """The human half of the prompt: what the operator saw, and where.

    Both halves are optional — a note with no armed anomaly still describes a
    real problem, and an anomaly with no note still points at a wedge.
    """
    parts = [p.strip() for p in (note, anomaly) if p and p.strip()]
    if len(parts) == 2:
        return f"{parts[0]} — selected anomaly: {parts[1]}"
    return parts[0] if parts else ""


class PromptDrafter:
    """Shells out to discovery.py prompt, with an injectable runner for tests."""

    def __init__(self, runs_dir, runner=subprocess.run, discovery_script=_DISCOVERY_SCRIPT):
        self.runs_dir = Path(runs_dir)
        self.runner = runner
        self.discovery_script = Path(discovery_script)

    def draft(self, run_id: str, rule: str | None = None, note: str = "", anomaly: str = "") -> dict:
        error = validate_run_target(self.runs_dir, run_id, rule, allowed=ALLOWED_RULES)
        if error:
            return {"error": error}

        summary_path = self.runs_dir / run_id / "summary.json"
        cmd = [
            sys.executable,
            str(self.discovery_script),
            "prompt",
            "--fitness",
            str(summary_path),
            "--rule",
            rule or FALLBACK_RULE,
            "--detail",
            compose_detail(note, anomaly),
            "--json",
            # Absolute paths: the viewer may be launched from anywhere, and the
            # queue read is what lets the UI report a real pending escalation.
            "--queue",
            str(_REPO_ROOT / "data" / "discovery_queue.json"),
            "--healer-state",
            str(_REPO_ROOT / "data" / "healer_state.json"),
        ]

        try:
            # cwd pins discovery.py's relative defaults (pokedex/memory/…,
            # references/…) to the repo, wherever the viewer was launched from.
            proc = self.runner(cmd, capture_output=True, text=True, cwd=_REPO_ROOT)
        except Exception as exc:
            return {"error": str(exc)}

        if proc.returncode != 0:
            return {"error": (proc.stderr or "").strip() or "discovery.py prompt failed"}
        try:
            payload = json.loads(proc.stdout)
        except (TypeError, json.JSONDecodeError):
            return {"error": "discovery.py prompt returned no JSON"}
        return {"prompt": payload.get("prompt", ""), "escalation": payload.get("escalation")}
