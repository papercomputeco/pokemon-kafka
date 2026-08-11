"""Run healer.py check on a recorded run — backs the viewer's HEAL button.

A run folder already holds everything a heal needs: summary.json is the run's
fitness (healer ignores the extra params/run_id keys) and names the ROM in
params.rom. Races take minutes of emulation, so jobs run on a daemon thread
and the UI polls for the verdict.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

_HEALER_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "healer.py"

# Mirror of healer.py's RULES names; kept literal so the viewer never imports
# the emulator-heavy scripts package. tests/test_viewer_heal.py exercises the
# round trip, so a rename over there fails loudly here.
KNOWN_RULES = frozenset({"navigation-thrash", "terminal-wedge", "no-progress"})


def validate_run_target(runs_dir, run_id: str, rule: str | None, allowed=KNOWN_RULES) -> str | None:
    """Shared precondition check for anything that acts on a recorded run.

    Returns the error message, or None when the target is usable. One home for
    the rule and summary.json checks so HealJobs and PromptDrafter can't drift.
    """
    if rule is not None and rule not in allowed:
        return f"unknown rule: {rule}"
    if not (Path(runs_dir) / run_id / "summary.json").is_file():
        return "run has no summary.json yet (still live?)"
    return None


class HealJobs:
    """One healer subprocess per run_id, with an injectable runner for tests."""

    def __init__(self, runs_dir, runner=subprocess.run, healer_script=_HEALER_SCRIPT, background=True):
        self.runs_dir = Path(runs_dir)
        self.runner = runner
        self.healer_script = Path(healer_script)
        self.background = background
        self.jobs: dict[str, dict] = {}

    def status(self, run_id: str) -> dict:
        return self.jobs.get(run_id, {"state": "idle", "verdict": None})

    def start(self, run_id: str, force: bool = False, rule: str | None = None) -> dict:
        if self.jobs.get(run_id, {}).get("state") == "running":
            return self.jobs[run_id]

        error = validate_run_target(self.runs_dir, run_id, rule)
        if error:
            self.jobs[run_id] = {"state": "error", "verdict": error}
            return self.jobs[run_id]

        summary_path = self.runs_dir / run_id / "summary.json"
        rom = (json.loads(summary_path.read_text()).get("params") or {}).get("rom")
        if not rom or not Path(rom).exists():
            self.jobs[run_id] = {"state": "error", "verdict": f"rom not found: {rom}"}
            return self.jobs[run_id]

        cmd = [
            sys.executable,
            str(self.healer_script),
            "check",
            "--fitness",
            str(summary_path),
            "--rom",
            str(rom),
        ]
        if force:
            cmd += ["--cooldown-hours", "0"]
        if rule:
            cmd += ["--rule", rule]

        job = {"state": "running", "verdict": None}
        if rule:
            job["rule"] = rule
        self.jobs[run_id] = job
        if self.background:
            threading.Thread(target=self._work, args=(run_id, cmd), daemon=True).start()
        else:
            self._work(run_id, cmd)
        return self.jobs[run_id]

    def _work(self, run_id: str, cmd: list[str]) -> None:
        rule = self.jobs.get(run_id, {}).get("rule")
        try:
            proc = self.runner(cmd, capture_output=True, text=True)
            lines = [ln.split("[healer]", 1)[1].strip() for ln in (proc.stdout or "").splitlines() if "[healer]" in ln]
            # The accept/keep decision is the verdict; escalation prints after it
            # and would otherwise mask the decision as the last line.
            decision = next((ln for ln in lines if ln.startswith(("accepted:", "kept current genome"))), None)
            verdict = decision or (lines[-1] if lines else "no healer output")
            if decision and any(ln.startswith("escalating") for ln in lines):
                verdict += " · escalated to the discovery engine"
            job = {"state": "done", "verdict": verdict}
        except Exception as exc:
            job = {"state": "error", "verdict": str(exc)}
        if rule:
            job["rule"] = rule
        self.jobs[run_id] = job
