#!/usr/bin/env python3
"""Run the regression evals in evals/cases/ against the headless agent (see evals/README.md).

Each case is one obstacle from docs/learnings/: seed savestate + stop condition + turn budget +
pass criteria on the lane's fitness.json. Deterministic per (state, genome); no LLM involved.
Results are appended to evals/results/<date>.md, dated like benchmarks/.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
AGENT = SCRIPT_DIR / "agent.py"
DEFAULT_CASES = WORKSPACE / "evals" / "cases"
DEFAULT_RESULTS = WORKSPACE / "evals" / "results"
DEFAULT_ROM = WORKSPACE / "rom" / "pokemon_red.gb"


def load_cases(cases_dir, only=None):
    cases = [json.loads(p.read_text()) for p in sorted(Path(cases_dir).glob("*.json"))]
    return [c for c in cases if only is None or c["name"] == only]


def build_cmd(rom, case, out_dir):
    out_dir = Path(out_dir)
    cmd = [
        "uv",
        "run",
        "python",
        str(AGENT),
        str(rom),
        "--strategy",
        "medium",
        "--max-turns",
        str(case["max_turns"]),
        "--load-state",
        str(case["seed_state"]),
        "--stop-on-map",
        str(case["stop_on_map"]),
        "--stop-state",
        str(out_dir / f"{case['name']}.stop.state"),
        "--output-json",
        str(out_dir / f"{case['name']}.fitness.json"),
        "--telemetry-dir",
        "",
        "--no-self-heal",
        "--no-in-run-heal",
        "--label",
        f"eval:{case['name']}",
    ]
    env = {}
    if case.get("genome"):
        env["EVOLVE_PARAMS"] = json.dumps(case["genome"])
    return cmd, env


def judge(case, fitness):
    crit = case.get("pass", {})
    ok = bool(fitness)
    if ok and "final_map_id" in crit:
        ok = fitness.get("final_map_id") == crit["final_map_id"]
    if ok and "min_lead_hp" in crit:
        ok = (fitness.get("lead_hp") or 0) >= crit["min_lead_hp"]
    if case.get("expected_fail"):
        return "XPASS" if ok else "XFAIL"
    return "PASS" if ok else "FAIL"


def _default_runner(cmd, env, cwd, timeout):
    try:
        return subprocess.run(cmd, env={**os.environ, **env}, cwd=cwd, timeout=timeout, check=False).returncode
    except subprocess.TimeoutExpired:
        return 124


def run_case(rom, case, out_dir, *, runner=_default_runner, timeout=900):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd, env = build_cmd(rom, case, out_dir)
    rc = runner(cmd, env, str(WORKSPACE), timeout)
    fit_path = out_dir / f"{case['name']}.fitness.json"
    fitness = json.loads(fit_path.read_text()) if fit_path.exists() else {}
    return {
        "name": case["name"],
        "category": case.get("category", ""),
        "verdict": judge(case, fitness),
        "rc": rc,
        "turns": fitness.get("turns"),
        "final_map_id": fitness.get("final_map_id"),
        "lead_hp": fitness.get("lead_hp"),
        "learning": case.get("learning", ""),
    }


def _append_results(results_dir, rows):
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = results_dir / f"{now:%Y-%m-%d}.md"
    lines = []
    if not path.exists():
        lines.append(f"# Eval results — {now:%Y-%m-%d}\n")
    lines.append(f"\n## {now:%H:%M}Z\n")
    lines.append("| case | category | verdict | turns | final map | lead hp | learning |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['category']} | {r['verdict']} | {r['turns']} | {r['final_map_id']} "
            f"| {r['lead_hp']} | {r['learning']} |"
        )
    with open(path, "a") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run docs/learnings-derived regression evals")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--case", default=None, help="run one case by name")
    parser.add_argument("--rom", default=str(DEFAULT_ROM))
    parser.add_argument("--out-dir", default=str(WORKSPACE / "data" / "evals"))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    parser.add_argument("--timeout", type=float, default=900.0, help="per-case wall clock (s)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cases = load_cases(args.cases, only=args.case)
    if args.dry_run:
        for c in cases:
            cmd, env = build_cmd(args.rom, c, args.out_dir)
            print(f"# {c['name']}")
            print(" ".join(f"{k}='{v}'" for k, v in env.items()) + " " + " ".join(cmd))
        return 0

    rows = [run_case(args.rom, c, args.out_dir, timeout=args.timeout) for c in cases]
    path = _append_results(args.results_dir, rows)
    for r in rows:
        print(f"[eval] {r['verdict']:5} {r['name']} turns={r['turns']} map={r['final_map_id']} hp={r['lead_hp']}")
    print(f"[eval] results appended to {path}")
    return 1 if any(r["verdict"] == "FAIL" for r in rows) else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
