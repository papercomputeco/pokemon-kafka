#!/usr/bin/env python3
"""Divide-and-conquer relay: parallel decision variants per journey segment, save-state batons between.

Each segment fans out N agent.py processes from the same baton (state + worldmap + genome), each
with a different decision variant. The first to satisfy the segment's stop condition self-terminates
via --stop-on-map/--stop-on-badge; the healthiest winner's artifacts seed the next segment.

Children are plain subprocesses (never `paper start claude`) with self-healing disabled, so the
only variable per lane is the decision variant.
"""

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
WORKSPACE = SCRIPT_DIR.parent

# Pokemon Red internal map ids (pret/pokered), as used across the repo.
MAPS = {"PEWTER_CITY": 2, "VIRIDIAN_FOREST": 51, "PEWTER_GYM": 54, "MT_MOON_1F": 59}

# The live-tuned genome from notes.md is the base; variants override single decisions.
BASE_GENOME = {
    "stuck_threshold": 13,
    "door_cooldown": 5,
    "waypoint_skip_distance": 8,
    "axis_preference_map_0": "y",
    "bt_max_snapshots": 8,
    "bt_restore_threshold": 27,
    "bt_max_attempts": 3,
    "bt_snapshot_interval": 50,
    "hp_run_threshold": 0.2,
    "hp_heal_threshold": 0.25,
    "unknown_move_score": 10.0,
    "status_move_score": 1.0,
}

NAV_SPREAD = (
    {"label": "base"},
    {"label": "fast_stuck", "stuck_threshold": 4},
    {"label": "patient", "stuck_threshold": 16, "door_cooldown": 12},
    {"label": "narrow", "waypoint_skip_distance": 1},
    {"label": "wide_dc2", "waypoint_skip_distance": 8, "door_cooldown": 2},
    {"label": "x_axis", "axis_preference_map_0": "x"},
)

# Survival decisions for the forest wall: heal/flee earlier is the known lever (notes.md).
BATTLE_SPREAD = (
    {"label": "base"},
    {"label": "cautious", "hp_run_threshold": 0.35, "hp_heal_threshold": 0.4},
    {"label": "very_cautious", "hp_run_threshold": 0.5, "hp_heal_threshold": 0.5},
    {"label": "aggressive", "hp_run_threshold": 0.1, "hp_heal_threshold": 0.15},
    {"label": "status_heavy", "status_move_score": 5.0},
    {"label": "cautious_narrow", "hp_run_threshold": 0.35, "hp_heal_threshold": 0.4, "waypoint_skip_distance": 1},
)


@dataclass(frozen=True)
class Segment:
    name: str
    stop_on_map: int | None
    stop_on_badge: int | None
    max_turns: int
    variants: tuple[dict, ...]
    extra_args: tuple[str, ...] = ()


@dataclass
class Baton:
    state_path: Path
    worldmap_path: Path | None
    genome: dict


SEGMENTS = (
    Segment("route1_to_forest", MAPS["VIRIDIAN_FOREST"], None, 4000, NAV_SPREAD),
    Segment("forest_to_pewter", MAPS["PEWTER_CITY"], None, 6000, BATTLE_SPREAD),
    Segment(
        "pewter_to_badge",
        None,
        1,
        4000,
        BATTLE_SPREAD,
        extra_args=("--save-state-on-trainer", "54:{run_dir}/batons/pre_brock.state"),
    ),
    Segment("badge_to_mtmoon", MAPS["MT_MOON_1F"], None, 6000, NAV_SPREAD),
)


def build_agent_cmd(rom, seg, variant, vdir, baton, run_dir):
    """Build (argv, extra-env) for one variant lane. Pure — no filesystem access."""
    genome = {**BASE_GENOME, **baton.genome, **{k: v for k, v in variant.items() if k != "label"}}
    cmd = [
        "uv",
        "run",
        "python",
        str(SCRIPT_DIR / "agent.py"),
        rom,
        "--strategy",
        "medium",
        "--max-turns",
        str(seg.max_turns),
        "--load-state",
        str(baton.state_path),
        "--output-json",
        str(vdir / "fitness.json"),
        "--worldmap-file",
        str(vdir / "world.map"),
        "--stop-state",
        str(vdir / "stop.state"),
        "--label",
        f"{seg.name}:{variant['label']}",
        "--no-self-heal",
        "--no-in-run-heal",
    ]
    if seg.stop_on_map is not None:
        cmd += ["--stop-on-map", str(seg.stop_on_map)]
    if seg.stop_on_badge is not None:
        cmd += ["--stop-on-badge", str(seg.stop_on_badge)]
    cmd += [a.format(run_dir=run_dir) for a in seg.extra_args]
    return cmd, {"EVOLVE_PARAMS": json.dumps(genome)}


def segment_success(fitness, seg):
    """Did this lane's final fitness satisfy the segment's stop condition?"""
    if not fitness:
        return False
    if seg.stop_on_map is not None:
        return fitness.get("final_map_id") == seg.stop_on_map
    if seg.stop_on_badge is not None:
        return bin(int(fitness.get("badges", 0))).count("1") >= seg.stop_on_badge
    return False


def pick_winner(results):
    """Healthiest successful lane wins; ties go to the fewest turns."""
    winners = [r for r in results if r["success"]]
    if not winners:
        return None
    return max(winners, key=lambda r: (r["fitness"].get("lead_hp", 0), -r["fitness"].get("turns", 10**9)))


def prepare_variant_dir(seg_dir, variant, baton):
    """Isolated workdir per lane; each gets its OWN copy of the baton worldmap."""
    vdir = seg_dir / variant["label"]
    vdir.mkdir(parents=True, exist_ok=True)
    if baton.worldmap_path is not None and baton.worldmap_path.exists():
        shutil.copy2(baton.worldmap_path, vdir / "world.map")
    return vdir


def promote_winner(run_dir, seg, winner):
    """Copy the winning lane's artifacts into batons/ and return the next segment's Baton."""
    batons = run_dir / "batons"
    batons.mkdir(parents=True, exist_ok=True)
    state_dst = batons / f"{seg.name}.state"
    shutil.copy2(winner["vdir"] / "stop.state", state_dst)
    map_src = winner["vdir"] / "world.map"
    map_dst = None
    if map_src.exists():
        map_dst = batons / f"{seg.name}.worldmap"
        shutil.copy2(map_src, map_dst)
    (batons / f"{seg.name}.genome.json").write_text(json.dumps(winner["genome"], indent=2) + "\n")
    return Baton(state_path=state_dst, worldmap_path=map_dst, genome=winner["genome"])


def run_segment(
    rom,
    seg,
    baton,
    seg_dir,
    run_dir,
    parallel=6,
    timeout=1200.0,
    grace=90.0,
    popen=subprocess.Popen,
    sleep=time.sleep,
    clock=time.monotonic,
    pick=None,
):
    """Race up to `parallel` decision variants from the same baton; return (pick(results), results)."""
    if pick is None:
        pick = pick_winner
    lanes = {}
    for variant in seg.variants[:parallel]:
        vdir = prepare_variant_dir(seg_dir, variant, baton)
        cmd, extra_env = build_agent_cmd(rom, seg, variant, vdir, baton, run_dir)
        genome = json.loads(extra_env["EVOLVE_PARAMS"])
        log = open(vdir / "agent.log", "wb")
        proc = popen(cmd, env={**os.environ, **extra_env}, cwd=str(WORKSPACE), stdout=log, stderr=subprocess.STDOUT)
        lanes[variant["label"]] = (proc, vdir, genome, log)
        print(f"[relay] {seg.name}/{variant['label']} launched")

    results = []
    first_success_at = None
    deadline = clock() + timeout
    while lanes:
        for label in list(lanes):
            proc, vdir, genome, log = lanes[label]
            if proc.poll() is None:
                continue
            log.close()
            fitness_file = vdir / "fitness.json"
            fitness = json.loads(fitness_file.read_text()) if fitness_file.exists() else {}
            result = {
                "label": label,
                "vdir": vdir,
                "genome": genome,
                "fitness": fitness,
                "success": segment_success(fitness, seg),
                "returncode": proc.returncode,
            }
            results.append(result)
            del lanes[label]
            state = "SUCCESS" if result["success"] else "no"
            print(f"[relay] {seg.name}/{label} exited rc={proc.returncode} success={state}")
            if result["success"] and first_success_at is None:
                first_success_at = clock()
        if not lanes:
            break
        now = clock()
        if now > deadline or (first_success_at is not None and now > first_success_at + grace):
            for label, (proc, vdir, genome, log) in lanes.items():
                proc.kill()
                proc.wait(timeout=10)
                log.close()
                results.append(
                    {"label": label, "vdir": vdir, "genome": genome, "fitness": {}, "success": False, "killed": True}
                )
                print(f"[relay] {seg.name}/{label} killed (straggler)")
            lanes.clear()
            break
        sleep(2.0)
    return pick(results), results
