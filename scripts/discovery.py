"""Discovery engine — LLM capability healing (loop 3).

Heals what parameter tuning cannot. The healer escalates exhausted tuning
into data/discovery_queue.json; this engine hands the evidence to Claude
Code headless in an isolated git worktree, runs the gates itself (full
test suite, ruff, fitness eval vs baseline), and opens a PR with the
proof. A human merges — never auto-merge.

`prompt` is the same evidence bundle without the machinery: it prints the
prompt a human can paste into Claude Code themselves. That is what the viewer's
HEAL button calls, so the hand-driven and unattended paths share one prompt.

Usage:
    uv run scripts/discovery.py run --rom rom/pokemon_red.gb
    uv run scripts/discovery.py run --rom ROM --reason "forest wall glitch"
    uv run scripts/discovery.py prompt --fitness runs/<id>/summary.json \
        --rule navigation-thrash --detail "waypoint goes stale on backtrack"

`run` always exits 0 — safe to chain after healer checks or cron. `prompt`
exits non-zero on a bad fitness file, because something is waiting on it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from evolve import run_agent, score
from healer import decide, load_state, save_state

DISCOVERY_COOLDOWN_HOURS = 24.0
OBSERVATIONS_PATH = "pokedex/memory/observations.md"
OBSERVATIONS_TAIL_CHARS = 4000

# Which code a rule implicates — the proposer's starting map, not a fence.
# references/routes.json is the human-editable waypoint source the Navigator
# loads at startup; it is the cheapest lever for a nav wedge, so nav rules point
# at it too. terminal-wedge needs its own entry: healer.RULES escalates it, and
# without one it silently falls back to the "manual" map.
_NAV_CODE = [
    "scripts/pathfinding.py",
    "scripts/world_map.py",
    "scripts/agent.py",
    "references/routes.json",
]
RULE_CODE_MAP = {
    "navigation-thrash": _NAV_CODE,
    "terminal-wedge": _NAV_CODE,
    "no-progress": _NAV_CODE,
    "manual": ["scripts/agent.py"],
}

PROMPT_TEMPLATE = """You are the discovery engine for the pokemon-kafka agent. Parameter tuning \
has been exhausted for the problem below — the fix requires a code change.

## Problem
Rule fired: {rule} (escalation reason: {reason}{detail})
Fitness of the failing run: {fitness}

## Where the run actually wedged (counted from its own event log)
{evidence}

## Recent healer races (parameter tuning already tried)
{races}

## Recent observations
{observations}

## Where to look first
{code_map}

## Machinery already in this codebase — extend or fix it, don't reinvent it
- AlphaEvolve-style parameter evolution (scripts/evolve.py, arXiv 2506.13131): \
params-as-genome, raced headless by scripts/healer.py. This loop already ran and \
failed on this problem — that is why you were called. If your fix introduces a \
threshold, add it to DEFAULT_PARAMS/PARAM_BOUNDS so it becomes evolvable instead \
of hard-coding a magic number.
- FLE-style backtracking (BacktrackingAgent from the Factorio Learning \
Environment, arXiv 2503.09617): BacktrackManager in scripts/agent.py snapshots \
PyBoy state and restores on stuck streaks. Check whether it is enabled on the \
failing map before concluding it didn't help — some maps opt out.
- Persistent WorldMap occupancy grid + per-turn planner (scripts/world_map.py): \
plan_step replans from scratch every turn with no memory of prior plans; \
its unreachable-goal fallback steers toward "closest node seen".
- Hand-editable waypoint routes (references/routes.json), loaded by the \
Navigator at startup — note some maps bypass the Navigator entirely and use the \
WorldMap planner instead.

## Constraints
- Diagnose the root cause before editing; explain the diagnosis in your commit message.
- Make the smallest code change that fixes the root cause. Minimal diff.
- Do not delete or weaken tests. Add a test that captures the failure mode.
- Run the focused tests for what you change (`uv run pytest tests/... -q`).
- Commit your change when done.
"""


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


def load_queue(path) -> list[dict]:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return []


def pick_entry(entries: list[dict], manual_reason: str | None) -> tuple[dict | None, int | None]:
    """Oldest unhandled queue entry, or a synthetic entry for a manual reason."""
    if manual_reason:
        return {"rule": "manual", "reason": "manual", "detail": manual_reason, "fitness": {}}, None
    pending = [(i, e) for i, e in enumerate(entries) if not e.get("handled")]
    if not pending:
        return None, None
    idx, entry = min(pending, key=lambda pair: pair[1].get("at", 0))
    return entry, idx


def mark_handled(path, idx: int) -> None:
    entries = load_queue(path)
    entries[idx]["handled"] = True
    Path(path).write_text(json.dumps(entries, indent=2))


# ---------------------------------------------------------------------------
# Context bundle + prompt
# ---------------------------------------------------------------------------


def build_bundle(entry: dict, races: list[dict], observations: str, evidence: dict | None = None) -> dict:
    return {
        "rule": entry["rule"],
        "reason": entry.get("reason", ""),
        "detail": entry.get("detail", ""),
        "fitness": entry.get("fitness", {}),
        "races": races,
        "observations": observations,
        "evidence": evidence or {},
        "code_map": RULE_CODE_MAP.get(entry["rule"], RULE_CODE_MAP["manual"]),
    }


def build_prompt(bundle: dict) -> str:
    detail = f" — {bundle['detail']}" if bundle["detail"] else ""
    return PROMPT_TEMPLATE.format(
        rule=bundle["rule"],
        reason=bundle["reason"],
        detail=detail,
        fitness=json.dumps(bundle["fitness"]),
        evidence=format_evidence(bundle.get("evidence")),
        races=json.dumps(bundle["races"], indent=2) or "none",
        observations=bundle["observations"] or "none",
        code_map="\n".join(f"- {p}" for p in bundle["code_map"]),
    )


def branch_name(rule: str, date_str: str) -> str:
    return f"discovery/{rule}-{date_str}"


def recent_races(healer_state_path, n: int = 5) -> list[dict]:
    return load_state(healer_state_path).get("races", [])[-n:]


# Fitness keys that identify a run. The healer records escalations by fitness
# alone — it never sees a run_id — so matching a viewer run to its queue entry
# means comparing the metrics that make a run unique.
_RUN_IDENTITY_KEYS = ("turns", "stuck_count", "max_stuck_streak", "final_x", "final_y", "final_map_id")


def pending_escalation(queue_path, fitness: dict) -> dict | None:
    """The unhandled queue entry this run's fitness matches, with queue depth.

    Lets a UI say "the healer already escalated this run" as a fact rather than
    a claim. Returns None when the run never tripped the automatic path.
    """
    pending = [e for e in load_queue(queue_path) if not e.get("handled")]
    for position, entry in enumerate(pending, start=1):
        entry_fitness = entry.get("fitness") or {}
        if all(k in entry_fitness and entry_fitness[k] == fitness.get(k) for k in _RUN_IDENTITY_KEYS):
            return {
                "rule": entry.get("rule", ""),
                "reason": entry.get("reason", ""),
                "position": position,
                "pending": len(pending),
            }
    return None


# Decisions log position inside the reason string ("map 51 (6,2) stuck=3 | …"),
# not as structured data — parse it back out for the loop signature.
_DECISION_POS_RE = re.compile(r"map (\d+) \((-?\d+),(-?\d+)\)")


def events_for_fitness(fitness: dict | None, runs_dir="runs") -> Path | None:
    """The recorded event log for an escalated run, if one exists.

    Queue entries carry only fitness, but agent.py stamps run_id into it for
    recorded runs — enough to find runs/<id>/events.jsonl so the unattended
    path gets the same measured evidence the viewer's composer does.
    """
    run_id = (fitness or {}).get("run_id")
    if not run_id:
        return None
    path = Path(runs_dir) / str(run_id) / "events.jsonl"
    return path if path.is_file() else None


def run_evidence(events_path, top: int = 5, trace_len: int = 12) -> dict:
    """Where a recorded run actually wedged, measured from its own event log.

    A human describing a replay names the wedge they happened to click; the
    counts name the one that burned the run. On 20260810-185357-7f79 those
    differ by two orders of magnitude (498 events at (6,2) vs 4 at the clicked
    (25,17)), which is enough to send a proposer at the wrong module — so the
    prompt carries the measurement, not just the story.

    Counts alone locate the wedge; the trace shows its mechanism. The same
    run's counts said "stuck at (6,2)" while the decision trace showed the
    real shape — a two-tile up/down limit cycle — so both ship.
    """
    positions: dict[tuple, dict] = {}
    loops: dict[tuple, int] = {}
    tail: list[dict] = []
    total = 0
    try:
        with open(events_path) as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a live run's last line can be a partial write
                data = event.get("data") or {}
                turn = event.get("turn", 0)
                if event.get("event_type") == "decision":
                    match = _DECISION_POS_RE.search(data.get("reason") or "")
                    where = f"map {match.group(1)} ({match.group(2)},{match.group(3)})" if match else "?"
                    buttons = "+".join(data.get("buttons") or []) or "wait"
                    loops[(where, buttons)] = loops.get((where, buttons), 0) + 1
                    tail.append({"turn": turn, "where": where, "buttons": buttons})
                    del tail[:-trace_len]
                    continue
                if event.get("event_type") != "stuck":
                    continue
                pos = data.get("position") or {}
                key = (pos.get("x"), pos.get("y"))
                total += 1
                seen = positions.setdefault(key, {"count": 0, "first_turn": turn, "last_turn": turn})
                seen["count"] += 1
                seen["first_turn"] = min(seen["first_turn"], turn)
                seen["last_turn"] = max(seen["last_turn"], turn)
    except OSError:
        return {}
    if not positions and not loops:
        return {}

    ranked = sorted(positions.items(), key=lambda kv: kv[1]["count"], reverse=True)[:top]
    signature = sorted(loops.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return {
        "stuck_total": total,
        "events_path": str(events_path),
        "top_positions": [{"position": list(key), **stats} for key, stats in ranked],
        "loop_signature": [{"where": where, "buttons": buttons, "count": n} for (where, buttons), n in signature],
        "final_decisions": tail,
    }


def format_evidence(evidence: dict | None) -> str:
    # The measurement-outranks-the-note instruction may only appear when a
    # measurement was actually taken. Rendering it over empty evidence told
    # proposers to trust "no log exists" over a correct operator note — the
    # exact misdirection this section exists to prevent.
    if not evidence or not (evidence.get("top_positions") or evidence.get("loop_signature")):
        return (
            "not measured — no event log was found for this run. If it was recorded, "
            "read runs/<run_id>/events.jsonl yourself before theorising."
        )
    lines = []
    if evidence.get("top_positions"):
        lines.append(f"{evidence['stuck_total']} stuck events in {evidence['events_path']}, by position:")
        for entry in evidence["top_positions"]:
            x, y = entry["position"]
            lines.append(f"- ({x},{y}) — {entry['count']} events, turns {entry['first_turn']}–{entry['last_turn']}")
    if evidence.get("loop_signature"):
        lines.append("Decision loop signature — (position → buttons), by count:")
        for entry in evidence["loop_signature"]:
            lines.append(f"- {entry['where']} → {entry['buttons']}: {entry['count']}×")
    if evidence.get("final_decisions"):
        lines.append(f"Final {len(evidence['final_decisions'])} decisions before the run ended:")
        for d in evidence["final_decisions"]:
            lines.append(f"- T{d['turn']} {d['where']} → {d['buttons']}")
    lines.append("Read that log directly before theorising; it holds every decision the agent made.")
    lines.append(
        "The problem note in ## Problem is a hypothesis — often a human describing a replay. "
        "This section is measured. Where they disagree, trust the measurement and say so in "
        "your diagnosis instead of chasing the note."
    )
    return "\n".join(lines)


def read_observations_tail(path=OBSERVATIONS_PATH, chars: int = OBSERVATIONS_TAIL_CHARS) -> str:
    try:
        return Path(path).read_text()[-chars:]
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Impure edges: subprocesses, worktree, gates, PR
# ---------------------------------------------------------------------------


def sh(cmd: list[str], cwd=None, timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def worktree_add(repo_root: Path, branch: str) -> tuple[Path, str]:
    """Create the isolated worktree; returns (path, starting HEAD sha)."""
    wt = Path(repo_root) / ".discovery" / branch.replace("/", "-")
    result = sh(["git", "worktree", "add", str(wt), "-b", branch], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(f"worktree add failed: {result.stderr.strip()}")
    return wt, sh(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip()


def cleanup(repo_root: Path, worktree: Path, branch: str) -> None:
    sh(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo_root)
    sh(["git", "branch", "-D", branch], cwd=repo_root)


def propose(worktree: Path, prompt: str, max_turns: int) -> str:
    result = sh(
        ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--max-turns", str(max_turns)],
        cwd=worktree,
        timeout=3600,
    )
    return result.stdout


def has_changes(worktree: Path, start_sha: str) -> bool:
    dirty = sh(["git", "status", "--porcelain"], cwd=worktree).stdout.strip() != ""
    head = sh(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip()
    return dirty or head != start_sha


def eval_candidate(worktree: Path, rom: str, runs: int, turns: int) -> list[float]:
    """Score the WORKTREE's agent (candidate code) over *runs* headless runs."""
    # cwd is the worktree, which has no ROM (rom/* is gitignored) — a relative
    # rom path would resolve to a missing file and every run would score -inf.
    rom = str(Path(rom).resolve())
    scores = []
    for _ in range(runs):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out = Path(f.name)
        try:
            sh(
                [
                    sys.executable,
                    str(Path(worktree) / "scripts" / "agent.py"),
                    rom,
                    "--max-turns",
                    str(turns),
                    "--output-json",
                    str(out),
                ],
                cwd=worktree,
                timeout=1200,
            )
            try:
                scores.append(score(json.loads(out.read_text())))
            except (OSError, json.JSONDecodeError):
                scores.append(float("-inf"))
        finally:
            out.unlink(missing_ok=True)
    return scores


def run_gates(worktree: Path, rom: str, eval_runs: int, race_turns: int) -> tuple[bool, str]:
    """Engine-run gates; the proposer's own claims are never trusted."""
    report = []

    tests = sh(["uv", "run", "pytest", "-q"], cwd=worktree)
    report.append(f"pytest: {'pass' if tests.returncode == 0 else 'FAIL'}\n{tests.stdout[-2000:]}")
    if tests.returncode != 0:
        return False, "\n".join(report)

    lint = sh(["uv", "run", "ruff", "check", "."], cwd=worktree)
    report.append(f"ruff: {'pass' if lint.returncode == 0 else 'FAIL'}\n{lint.stdout[-500:]}")
    if lint.returncode != 0:
        return False, "\n".join(report)

    if eval_runs <= 0:
        report.append("fitness eval skipped (--eval-runs 0)")
        return True, "\n".join(report)

    candidate_scores = eval_candidate(worktree, rom, eval_runs, race_turns)
    baseline_scores = [score(run_agent(rom, race_turns, {})) for _ in range(eval_runs)]
    candidate_mean = sum(candidate_scores) / len(candidate_scores)
    baseline_mean = sum(baseline_scores) / len(baseline_scores)
    passed = decide(baseline_mean, candidate_mean)
    report.append(
        f"fitness eval: baseline mean {baseline_mean:.0f}, candidate mean {candidate_mean:.0f} "
        f"-> {'pass' if passed else 'FAIL'}"
    )
    return passed, "\n".join(report)


def commit_if_needed(worktree: Path, message: str) -> None:
    if sh(["git", "status", "--porcelain"], cwd=worktree).stdout.strip():
        sh(["git", "add", "-A"], cwd=worktree)
        sh(["git", "commit", "-m", message], cwd=worktree)


def push_and_pr(worktree: Path, branch: str, title: str, body: str) -> str:
    push = sh(["git", "push", "-u", "origin", branch], cwd=worktree)
    if push.returncode != 0:
        raise RuntimeError(f"push failed: {push.stderr.strip()}")
    pr = sh(["gh", "pr", "create", "--title", title, "--body", body], cwd=worktree)
    if pr.returncode != 0:
        raise RuntimeError(f"gh pr create failed: {pr.stderr.strip()}")
    return pr.stdout.strip()


# ---------------------------------------------------------------------------
# run flow
# ---------------------------------------------------------------------------


def _run(args) -> None:
    entries = load_queue(args.queue)
    entry, idx = pick_entry(entries, args.reason)
    if entry is None:
        print("[discovery] nothing to discover — queue is empty")
        return

    state = load_state(args.state)
    now_ts = time.time()
    last = state.get("last_attempt_at")
    if last is not None and (now_ts - last) < args.cooldown_hours * 3600:
        print("[discovery] cooldown active — skipping attempt")
        return

    events = events_for_fitness(entry.get("fitness"))
    bundle = build_bundle(
        entry,
        recent_races(args.healer_state),
        read_observations_tail(),
        run_evidence(events) if events else {},
    )
    if args.dry_run:
        print(f"[discovery] dry-run: would attempt {bundle['rule']} ({bundle['reason']}) via {bundle['code_map']}")
        return

    repo_root = Path.cwd()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    branch = branch_name(entry["rule"], date_str)
    worktree, start_sha = worktree_add(repo_root, branch)
    outcome = "no-proposal"
    try:
        propose(worktree, build_prompt(bundle), args.max_claude_turns)
        if not has_changes(worktree, start_sha):
            print("[discovery] proposer made no changes — discarding attempt")
            cleanup(repo_root, worktree, branch)
        else:
            passed, report = run_gates(worktree, args.rom, args.eval_runs, args.race_turns)
            if passed:
                commit_if_needed(worktree, f"discovery: proposed fix for {entry['rule']}")
                pending = " [eval pending]" if args.eval_runs <= 0 else ""
                title = f"discovery: {entry['rule']} — unattended capability fix{pending}"
                body = (
                    f"Escalation: {entry.get('reason', 'manual')}\n\n"
                    f"Fitness that triggered it: `{json.dumps(entry.get('fitness', {}))}`\n\n"
                    f"## Gates (engine-run)\n\n```\n{report}\n```\n"
                )
                url = push_and_pr(worktree, branch, title, body)
                outcome = "pr-opened"
                print(f"[discovery] PR opened: {url}")
            else:
                outcome = "gates-failed"
                print(f"[discovery] gates failed — discarding attempt\n{report}")
                cleanup(repo_root, worktree, branch)
    finally:
        if idx is not None:
            mark_handled(args.queue, idx)  # one attempt per entry, whatever the outcome
        state.setdefault("attempts", []).append(
            {"at": now_ts, "rule": entry["rule"], "branch": branch, "outcome": outcome}
        )
        state["last_attempt_at"] = now_ts
        save_state(args.state, state)


# ---------------------------------------------------------------------------
# prompt flow — build the prompt, hand it to a human, touch nothing
# ---------------------------------------------------------------------------


def _prompt(args) -> int:
    """Print the prompt `run` would hand the proposer. No worktree, no LLM, no state.

    Backs the viewer's HEAL composer: an operator points at an anomaly, writes
    what went wrong, and gets the same prompt the unattended path would build.
    """
    try:
        fitness = json.loads(Path(args.fitness).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[discovery] unreadable fitness file {args.fitness}: {exc}", file=sys.stderr)
        return 1

    entry = {"rule": args.rule, "reason": args.reason, "detail": args.detail, "fitness": fitness}
    # events.jsonl sits beside summary.json in a recorded run folder.
    events = args.events or (Path(args.fitness).parent / "events.jsonl")
    bundle = build_bundle(entry, recent_races(args.healer_state), read_observations_tail(), run_evidence(events))
    prompt = build_prompt(bundle)

    if args.json:
        print(json.dumps({"prompt": prompt, "escalation": pending_escalation(args.queue, fitness)}))
    else:
        print(prompt)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Discovery engine — LLM capability healing")
    sub = parser.add_subparsers(dest="command", required=True)

    prompt = sub.add_parser("prompt", help="print the proposer prompt for a run without running anything")
    prompt.add_argument("--fitness", required=True, help="fitness JSON (a run's summary.json works)")
    prompt.add_argument("--rule", default="manual", help="rule naming the failure mode (picks the code map)")
    prompt.add_argument("--detail", default="", help="what the operator saw — the human half of the prompt")
    prompt.add_argument("--reason", default="operator", help="why this was raised (default: hand-raised)")
    prompt.add_argument("--json", action="store_true", help='emit {"prompt", "escalation"} for a UI')
    prompt.add_argument("--events", default=None, help="event log to count wedges from (default: beside --fitness)")
    prompt.add_argument("--queue", default="data/discovery_queue.json", help="queue checked for a matching escalation")
    prompt.add_argument("--healer-state", default="data/healer_state.json", help="healer race history for context")

    run = sub.add_parser("run", help="attempt one discovery from the escalation queue")
    run.add_argument("--rom", required=True, help="ROM path for fitness eval runs")
    run.add_argument("--queue", default="data/discovery_queue.json", help="escalation queue from the healer")
    run.add_argument("--reason", default=None, help="manual trigger: describe the problem instead of using the queue")
    run.add_argument("--eval-runs", type=int, default=3, help="fitness eval runs per side (0 skips, PR marked)")
    run.add_argument("--race-turns", type=int, default=800, help="turns per eval run")
    run.add_argument("--dry-run", action="store_true", help="print the plan without a worktree or LLM call")
    run.add_argument("--state", default="data/discovery_state.json", help="attempt history + cooldown")
    run.add_argument("--healer-state", default="data/healer_state.json", help="healer race history for context")
    run.add_argument("--max-claude-turns", type=int, default=40, help="proposer turn budget")
    run.add_argument("--cooldown-hours", type=float, default=DISCOVERY_COOLDOWN_HOURS)
    args = parser.parse_args()

    # `prompt` is interactive — a viewer or a human is waiting on the output, so
    # failures surface as a non-zero exit instead of the swallow `run` needs.
    if args.command == "prompt":
        return _prompt(args)

    try:
        _run(args)
    except Exception as exc:  # discovery must never fail a wrapper or cron
        print(f"[discovery] discovery error: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
