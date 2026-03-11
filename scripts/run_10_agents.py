#!/usr/bin/env python3
"""Run 10 agent instances with parameter variants to reach Pokemon selection.

Launches agents in parallel (5 at a time) with different navigator parameter
combinations. Collects fitness from each and reports results.

Usage:
    uv run scripts/run_10_agents.py <rom>
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
AGENT_SCRIPT = SCRIPT_DIR / "agent.py"

# Re-use the canonical scoring function from evolve.py
from evolve import score  # noqa: E402

# 10 parameter variants to try — tuned for reaching rival battle
# Previous winner: door_cooldown=4 beat baseline for Pokemon selection
_BT_DEFAULTS = {
    "bt_max_snapshots": 8,
    "bt_restore_threshold": 15,
    "bt_max_attempts": 3,
    "bt_snapshot_interval": 50,
}

PARAM_VARIANTS = [
    # Baseline (previous winner door_cooldown=4)
    {
        "stuck_threshold": 8,
        "door_cooldown": 4,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "label": "baseline_4dc",
    },
    # Original defaults
    {
        "stuck_threshold": 8,
        "door_cooldown": 8,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "label": "original",
    },
    # Very short door cooldown
    {
        "stuck_threshold": 8,
        "door_cooldown": 2,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "label": "dc2",
    },
    # Low stuck + short door
    {
        "stuck_threshold": 4,
        "door_cooldown": 4,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "label": "low_stuck_dc4",
    },
    # High stuck + short door
    {
        "stuck_threshold": 12,
        "door_cooldown": 4,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "label": "high_stuck_dc4",
    },
    # Wide skip + short door
    {
        "stuck_threshold": 8,
        "door_cooldown": 4,
        "waypoint_skip_distance": 6,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "label": "wide_skip_dc4",
    },
    # Narrow skip + short door
    {
        "stuck_threshold": 8,
        "door_cooldown": 4,
        "waypoint_skip_distance": 1,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "label": "narrow_dc4",
    },
    # X-axis + short door
    {
        "stuck_threshold": 8,
        "door_cooldown": 4,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "x",
        **_BT_DEFAULTS,
        "label": "x_axis_dc4",
    },
    # Aggressive: low stuck + very short door + wide skip
    {
        "stuck_threshold": 3,
        "door_cooldown": 2,
        "waypoint_skip_distance": 5,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "label": "aggressive",
    },
    # Moderate: medium stuck + short door
    {
        "stuck_threshold": 6,
        "door_cooldown": 6,
        "waypoint_skip_distance": 4,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "label": "moderate",
    },
    # Aggressive backtracking: low restore threshold, high retries
    {
        "stuck_threshold": 8,
        "door_cooldown": 4,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "y",
        "bt_max_snapshots": 8,
        "bt_restore_threshold": 10,
        "bt_max_attempts": 5,
        "bt_snapshot_interval": 50,
        "label": "aggressive_bt",
    },
    # Backtracking disabled
    {
        "stuck_threshold": 8,
        "door_cooldown": 4,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "y",
        "bt_max_snapshots": 0,
        "bt_restore_threshold": 999,
        "bt_max_attempts": 3,
        "bt_snapshot_interval": 50,
        "label": "no_bt",
    },
    # Aggressive battle: fight longer before running/healing
    {
        "stuck_threshold": 8,
        "door_cooldown": 4,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "hp_run_threshold": 0.1,
        "hp_heal_threshold": 0.15,
        "label": "aggressive_battle",
    },
    # Cautious battle: heal early and run early
    {
        "stuck_threshold": 8,
        "door_cooldown": 4,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "hp_run_threshold": 0.35,
        "hp_heal_threshold": 0.4,
        "label": "cautious_battle",
    },
    # Status moves: higher priority for status moves
    {
        "stuck_threshold": 8,
        "door_cooldown": 4,
        "waypoint_skip_distance": 3,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "status_move_score": 5.0,
        "label": "status_moves",
    },
    # Full aggressive: aggressive nav + aggressive battle
    {
        "stuck_threshold": 3,
        "door_cooldown": 2,
        "waypoint_skip_distance": 5,
        "axis_preference_map_0": "y",
        **_BT_DEFAULTS,
        "hp_run_threshold": 0.1,
        "hp_heal_threshold": 0.15,
        "label": "full_aggressive",
    },
]

MAX_TURNS = 5000  # Intro + Pokemon selection + rival scripted sequence + battle + exit


def run_one_agent(rom_path: str, params: dict, agent_id: int) -> dict:
    """Run a single agent and return results."""
    label = params.get("label", f"agent_{agent_id}")
    output_file = tempfile.NamedTemporaryFile(suffix=".json", prefix=f"fitness_{label}_", delete=False)
    output_path = output_file.name
    output_file.close()

    env = os.environ.copy()
    # Remove label from params before passing to agent
    agent_params = {k: v for k, v in params.items() if k != "label"}
    env["EVOLVE_PARAMS"] = json.dumps(agent_params)

    cmd = [
        sys.executable,
        str(AGENT_SCRIPT),
        rom_path,
        "--max-turns",
        str(MAX_TURNS),
        "--output-json",
        output_path,
    ]

    start = time.time()
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
        elapsed = time.time() - start

        fitness = json.loads(Path(output_path).read_text())
        return {
            "agent_id": agent_id,
            "label": label,
            "params": agent_params,
            "fitness": fitness,
            "score": score(fitness),
            "elapsed": round(elapsed, 1),
            "returncode": result.returncode,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        elapsed = time.time() - start
        return {
            "agent_id": agent_id,
            "label": label,
            "params": agent_params,
            "fitness": {},
            "score": -999,
            "elapsed": round(elapsed, 1),
            "error": str(e),
        }
    finally:
        try:
            os.unlink(output_path)
        except OSError:
            pass


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run scripts/run_10_agents.py <rom>")
        sys.exit(1)

    rom_path = sys.argv[1]
    if not Path(rom_path).exists():
        print(f"ROM not found: {rom_path}")
        sys.exit(1)

    print(f"[run_10] Launching {len(PARAM_VARIANTS)} agents with {MAX_TURNS} max turns each")
    print(f"[run_10] ROM: {rom_path}")
    print("[run_10] Running 5 at a time...\n")

    all_results = []
    start_time = time.time()

    with ProcessPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(run_one_agent, rom_path, params, i): i for i, params in enumerate(PARAM_VARIANTS)}

        for future in as_completed(futures):
            result = future.result()
            label = result["label"]
            s = result["score"]
            elapsed = result["elapsed"]
            fitness = result.get("fitness", {})
            map_id = fitness.get("final_map_id", "?")
            party = fitness.get("party_size", "?")
            stuck = fitness.get("stuck_count", "?")

            status = "OK" if "error" not in result else "FAIL"
            print(
                f"  [{status}] Agent {result['agent_id']:2d} ({label:14s}) | "
                f"score={s:8.1f} | map={map_id} party={party} stuck={stuck} | "
                f"{elapsed}s"
            )
            all_results.append(result)

    total_time = time.time() - start_time

    # Sort by score
    all_results.sort(key=lambda r: r["score"], reverse=True)

    print(f"\n{'=' * 70}")
    print(f"[run_10] All {len(all_results)} agents complete in {total_time:.1f}s")
    print(f"{'=' * 70}\n")
    print(f"{'Rank':>4} {'Label':14s} {'Score':>8} {'Map':>4} {'Party':>5} {'Stuck':>5} {'Turns':>5} {'Time':>6}")
    print("-" * 60)

    for rank, r in enumerate(all_results, 1):
        f = r.get("fitness", {})
        print(
            f"{rank:4d} {r['label']:14s} {r['score']:8.1f} "
            f"{f.get('final_map_id', '?'):>4} {f.get('party_size', '?'):>5} "
            f"{f.get('stuck_count', '?'):>5} {f.get('turns', '?'):>5} "
            f"{r['elapsed']:5.1f}s"
        )

    # Show winner
    winner = all_results[0]
    print(f"\nWinner: {winner['label']} (score={winner['score']:.1f})")
    print(f"Params: {json.dumps(winner['params'], indent=2)}")

    # Save results
    results_path = SCRIPT_DIR.parent / "pokedex" / "evolve_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(all_results, indent=2) + "\n")
    print(f"\nFull results saved to: {results_path}")


if __name__ == "__main__":
    main()
