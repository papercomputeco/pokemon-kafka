#!/usr/bin/env python3
"""Role signals per operator session — the evidence behind docs/model-fit.md, extracted, not recalled.

Reads a Claude Code stream-json log (data/local_runs/<tag>.claude.jsonl) or a pi session
(~/.pi/agent/sessions/<cwd-slug>/*.jsonl) and prints, per session, the behaviours the four
operator characters leave in a transcript:

  Driver        relay calls, calls before the first relay, wall minutes
  Experimenter  single-lane agent.py probes, probes per relay
  Investigator  code reads before the first code edit, code files edited, tests touched,
                calls before the first code edit
  Reporter      learnings files written, commits (from the worktree), early-exit (ended by
                choice with budget left — wall vs. budget)

These are *signals*, not verdicts. A Driver is not a model with zero probes; it is a model that
re-races when a probe would have answered. Read the table next to the run's benchmark file.

    uv run python scripts/role_metrics.py data/local_runs/haiku-cc-brock-r4.claude.jsonl \
        ~/.pi/agent/sessions/*qwen38-27b-mtmoon*/*.jsonl --budget-min 120
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CODE_FILE = re.compile(
    r"scripts/(agent|relay|world_map|pathfinding|parcel_quest|sideloop|evolve|healer)\.py|references/routes\.json"
)
TEST_FILE = re.compile(r"tests/test_\w+\.py")
LEARNING = re.compile(r"docs/learnings/[\w\-]+\.md")
RELAY_CALL = re.compile(r"python3?\s+(\S*/)?scripts/relay\.py\s")  # an execution, not a grep of the file
PROBE_CALL = re.compile(r"python3?\s+(\S*/)?scripts/agent\.py\s")
READ_CMD = re.compile(r"^\s*(sed|grep|cat|head|tail|awk|rg|less|python3? -c|uv run python -c)\b")
EDIT_CMD = re.compile(r"(\bsed -i\b|apply_patch|\bcat >|\btee\b|>>|\bpython3? - <<|\bperl -pi)")


@dataclass
class Signals:
    label: str
    harness: str
    model: str = "?"
    calls: int = 0
    relay_calls: int = 0
    probe_calls: int = 0
    code_reads: int = 0
    code_reads_before_first_edit: int = 0
    calls_before_first_relay: int | None = None
    calls_before_first_edit: int | None = None
    code_files_edited: set = field(default_factory=set)
    tests_touched: set = field(default_factory=set)
    learnings_written: set = field(default_factory=set)
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    ended_by_choice: bool | None = None

    def note_tool(self, name: str, inp: dict):
        self.calls += 1
        text = " ".join(str(v) for v in inp.values() if isinstance(v, str))
        path = str(inp.get("file_path") or inp.get("path") or "")
        cmd = str(inp.get("command") or "")
        is_relay = bool(RELAY_CALL.search(cmd))
        is_probe = bool(PROBE_CALL.search(cmd)) and not is_relay and "--help" not in cmd
        is_code_read = (name in ("Read", "read", "Grep", "grep", "Glob") and CODE_FILE.search(path or text)) or (
            name in ("Bash", "bash") and READ_CMD.search(cmd) and CODE_FILE.search(cmd) and not EDIT_CMD.search(cmd)
        )
        is_edit = name in ("Edit", "Write", "MultiEdit", "edit", "write") or (
            name in ("Bash", "bash") and EDIT_CMD.search(cmd)
        )
        target = path or text
        if is_relay:
            self.relay_calls += 1
            if self.calls_before_first_relay is None:
                self.calls_before_first_relay = self.calls - 1
        if is_probe:
            self.probe_calls += 1
        if is_code_read:
            self.code_reads += 1
            if self.calls_before_first_edit is None:
                self.code_reads_before_first_edit += 1
        if is_edit:
            for m in CODE_FILE.finditer(target):
                self.code_files_edited.add(m.group(0))
                if self.calls_before_first_edit is None:
                    self.calls_before_first_edit = self.calls - 1
            for m in TEST_FILE.finditer(target):
                self.tests_touched.add(m.group(0))
            for m in LEARNING.finditer(target):
                self.learnings_written.add(m.group(0).split("/")[-1])

    def note_ts(self, ts: datetime):
        if self.first_ts is None or ts < self.first_ts:
            self.first_ts = ts
        if self.last_ts is None or ts > self.last_ts:
            self.last_ts = ts

    @property
    def wall_min(self) -> float:
        if not (self.first_ts and self.last_ts):
            return 0.0
        return (self.last_ts - self.first_ts).total_seconds() / 60


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_claude(path: Path) -> Signals:
    sig = Signals(label=path.stem.replace(".claude", ""), harness="claude-code")
    result = None
    for line in path.open():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = d.get("type")
        if t == "assistant":
            msg = d.get("message", {})
            sig.model = msg.get("model", sig.model)
            for c in msg.get("content", []):
                if c.get("type") == "tool_use":
                    sig.note_tool(c.get("name", ""), c.get("input", {}) or {})
        if t == "result":
            result = d
    if result:
        sig.ended_by_choice = result.get("subtype") == "success"
        ms = result.get("duration_ms")
        if ms:
            # stream-json carries no per-event timestamps; duration_ms is the harness's own clock
            sig.first_ts = datetime.fromtimestamp(0)
            sig.last_ts = datetime.fromtimestamp(ms / 1000)
    return sig


def parse_pi(path: Path) -> Signals:
    sig = Signals(label=path.parent.name.strip("-").split("pokemon-kafka-speedrun-")[-1], harness="pi")
    last_assistant_empty = False
    for line in path.open():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") == "model_change":
            sig.model = d.get("modelId", sig.model)
        if "timestamp" in d:
            try:
                sig.note_ts(_ts(d["timestamp"]))
            except ValueError:
                pass
        if d.get("type") != "message":
            continue
        msg = d.get("message", {})
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        tool_calls = [
            c for c in content if isinstance(c, dict) and c.get("type") in ("toolCall", "tool_use", "tool_call")
        ]
        text = any(isinstance(c, dict) and c.get("type") == "text" and c.get("text", "").strip() for c in content)
        last_assistant_empty = not tool_calls and not text
        for c in tool_calls:
            name = c.get("name") or c.get("toolName") or ""
            inp = c.get("arguments") or c.get("input") or c.get("args") or {}
            if isinstance(inp, str):
                try:
                    inp = json.loads(inp)
                except json.JSONDecodeError:
                    inp = {"command": inp}
            sig.note_tool(name, inp)
    sig.ended_by_choice = not last_assistant_empty  # a dead stream ends on an empty assistant turn
    return sig


def worktree_commits(label: str, repo: Path) -> int | None:
    for cand in (repo.parent / f"pokemon-kafka-speedrun-{label}", repo.parent / f"pokemon-kafka-speedrun-pi-{label}"):
        if cand.is_dir():
            try:
                out = subprocess.run(
                    ["git", "-C", str(cand), "log", "--oneline", "origin/main..HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                ).stdout
                return len([ln for ln in out.splitlines() if ln.strip()])
            except (OSError, subprocess.TimeoutExpired):
                return None
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sessions", nargs="+")
    ap.add_argument(
        "--budget-min", type=float, default=120.0, help="mission wall-clock budget, for the early-exit column"
    )
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = []
    for s in args.sessions:
        p = Path(s).expanduser()
        if not p.exists():
            print(f"[role_metrics] missing: {p}", file=sys.stderr)
            continue
        sig = parse_claude(p) if p.name.endswith(".claude.jsonl") else parse_pi(p)
        commits = worktree_commits(sig.label, Path(args.repo))
        wall = sig.wall_min
        early = sig.ended_by_choice and wall > 0 and wall < 0.75 * args.budget_min
        rows.append(
            {
                "label": sig.label,
                "harness": sig.harness,
                "model": sig.model,
                "wall_min": round(wall, 1),
                "calls": sig.calls,
                "relay": sig.relay_calls,
                "probes": sig.probe_calls,
                "probes_per_relay": round(sig.probe_calls / sig.relay_calls, 2) if sig.relay_calls else None,
                "calls_before_first_relay": sig.calls_before_first_relay,
                "code_reads_before_first_edit": sig.code_reads_before_first_edit,
                "calls_before_first_edit": sig.calls_before_first_edit,
                "code_files_edited": sorted(sig.code_files_edited),
                "tests_touched": len(sig.tests_touched),
                "learnings": len(sig.learnings_written),
                "commits": commits,
                "ended_by_choice": sig.ended_by_choice,
                "early_exit": early,
            }
        )
    if args.json:
        print(json.dumps(rows, indent=1))
        return 0
    hdr = [
        "run",
        "harness",
        "wall m",
        "calls",
        "relay",
        "probes",
        "probe/relay",
        "calls→1st relay",
        "code reads→1st edit",
        "calls→1st edit",
        "code files",
        "tests",
        "learnings",
        "commits",
        "early exit",
    ]
    print("| " + " | ".join(hdr) + " |")
    print("|" + "---|" * len(hdr))
    for r in rows:
        print(
            f"| {r['label']} | {r['harness']} | {r['wall_min']} | {r['calls']} | {r['relay']} | {r['probes']} | "
            f"{r['probes_per_relay'] if r['probes_per_relay'] is not None else '—'} | "
            f"{r['calls_before_first_relay'] if r['calls_before_first_relay'] is not None else '—'} | "
            f"{r['code_reads_before_first_edit']} | "
            f"{r['calls_before_first_edit'] if r['calls_before_first_edit'] is not None else '—'} | "
            f"{len(r['code_files_edited'])} | {r['tests_touched']} | {r['learnings']} | "
            f"{r['commits'] if r['commits'] is not None else '—'} | "
            f"{'yes' if r['early_exit'] else ('no' if r['ended_by_choice'] is not None else '—')} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
