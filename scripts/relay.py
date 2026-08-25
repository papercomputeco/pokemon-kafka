#!/usr/bin/env python3
"""Divide-and-conquer relay: parallel decision variants per journey segment, save-state batons between.

Each segment fans out N agent.py processes from the same baton (state + worldmap + genome), each
with a different decision variant. The first to satisfy the segment's stop condition self-terminates
via --stop-on-map/--stop-on-badge; the healthiest winner's artifacts seed the next segment.

Children are plain subprocesses (never `paper start claude`). Self-healing runs *inside* each lane
and is isolated to it — a private genome file, a private advice inbox, and (with --sideloop-every)
a private AlphaEvolve subloop — so the only variable between lanes is still the decision variant.
The end-of-run healer stays off: it writes the shared notes.md, which a relay must not mutate once
per lane.
"""

import argparse
import dataclasses
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from healer import append_genome
from memory_writer import append_observations

SCRIPT_DIR = Path(__file__).parent
WORKSPACE = SCRIPT_DIR.parent

# Pokemon Red internal map ids (pret/pokered), as used across the repo.
MAPS = {
    "PEWTER_CITY": 2,
    "CERULEAN_CITY": 3,
    "VIRIDIAN_FOREST": 51,
    "PEWTER_GYM": 54,
    "MT_MOON_1F": 59,
    "MT_MOON_B1F": 60,
    "ROUTE_4": 15,
}

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
    "truth_refuse_strikes": 40,
}

# Navigation levers. NOTE which legs read which: the waypoint Navigator owns stuck_threshold and
# waypoint_skip_distance, and axis_preference_map_0 is map 0 only — so on a leg the ROM-truth
# planner owns (Route 3 -> Mt. Moon) those four knobs are inert and every lane returns byte-
# identical fitness, six lanes' compute for one lane's information. truth_refuse_strikes is the
# knob that leg does read, so the spread varies it too rather than only the Navigator's.
NAV_SPREAD = (
    {"label": "base"},
    {"label": "fast_stuck", "stuck_threshold": 4, "truth_refuse_strikes": 12},
    {"label": "patient", "stuck_threshold": 16, "door_cooldown": 12, "truth_refuse_strikes": 90},
    {"label": "narrow", "waypoint_skip_distance": 1},
    {"label": "wide_dc2", "waypoint_skip_distance": 8, "door_cooldown": 2, "truth_refuse_strikes": 20},
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
    # With stop_on_map: only x >= this column counts. Mt. Moon's clear ends on Route 4 (15), but
    # the lane ENTERED from 15's west side — its entrance mat is (18,5) and the dungeon's east
    # exit lands at (24,5), so without the column check the first bounce back out of the west
    # entrance would score as a clear (the 59<->15 spring, demo-runs/README.md).
    stop_min_x: int | None = None


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
    # The two skill legs past the mountain door. 1F -> B1F is cave navigation on a correct grid
    # (tile-pair collisions included); the clear is the puzzle leg — ladders, the exit chain, and
    # whatever anomalies the live engine holds that the reference does not. Neither has a
    # deterministic solver in agent.py: _mtmoon_action returns None inside 59, on purpose.
    Segment("mtmoon_1f_to_b1f", MAPS["MT_MOON_B1F"], None, 3000, NAV_SPREAD),
    Segment("mtmoon_clear", MAPS["ROUTE_4"], None, 8000, NAV_SPREAD, stop_min_x=22),
    # The road past the mountain (seeded from the mtmoon_clear baton, route4_east_hp25):
    # Route 4's east side down into Cerulean is open-path navigation; the badge leg counts
    # the Cascade Badge however the lane earns it — Nugget Bridge detours included.
    Segment("route4_to_cerulean", MAPS["CERULEAN_CITY"], None, 4000, NAV_SPREAD),
    Segment("cerulean_to_badge2", None, 2, 6000, BATTLE_SPREAD),
)


# Box-wide, not per-worktree: the relay that starves this one may be a leftover in a sibling
# worktree, which a lock under WORKSPACE/data can never see.
LOCK_PATH = Path(os.environ.get("POKEMON_SLOTS_DIR", "/tmp/pokemon-kafka-slots")) / "relay.lock"
_RELAY_LOCK_FD = None  # held for the life of the process; the kernel drops it if we die


def acquire_relay_lock(lock_path=None, pid=None):
    """Refuse to start while another relay owns the box. Returns (ok, holder_pid).

    Parallel relays multiply every lane, and the box silently stops delivering the ~30 turns/s the
    segment budgets assume. The lanes then report as wedged, so the model reads a CPU shortage as a
    navigation wall and "fixes" the wrong thing.

    fcntl.flock, not a pid file: it is atomic across processes (five relays launched from one shell
    command start within milliseconds — a read-then-write check let all five through) and the
    kernel releases it when the holder dies, so there is no stale state to detect and no
    create-then-stamp window to race (the pid-file version lost that race 4 times out of 8).
    """
    global _RELAY_LOCK_FD
    lock_path = Path(lock_path or LOCK_PATH)
    pid = pid or os.getpid()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            holder = int(os.pread(fd, 32, 0).decode().strip() or 0)
        except (OSError, ValueError):
            holder = 0
        os.close(fd)
        return False, holder
    os.ftruncate(fd, 0)
    os.write(fd, str(pid).encode())
    _RELAY_LOCK_FD = fd
    return True, pid


def release_relay_lock(lock_path=None, pid=None):
    """Drop the lock if we hold it; never raise, a failed release must not fail the run."""
    global _RELAY_LOCK_FD
    if _RELAY_LOCK_FD is None:
        return
    try:
        fcntl.flock(_RELAY_LOCK_FD, fcntl.LOCK_UN)
        os.close(_RELAY_LOCK_FD)
    except OSError:
        pass
    _RELAY_LOCK_FD = None


def sideloop_parallel_for(lanes, cpus=None):
    """How many subloop lanes each relay lane may race at once, given the box.

    Every relay lane is a headless emulator pinning a core, and each spawns its own subloop race
    on top. Unbudgeted, six lanes x six subloop lanes is 42 emulators on a 32-core box: the lanes
    slow below the ~30 turns/s the segment budgets assume, hit --max-turns without moving, and
    report as wedged. That failure is indistinguishable from a real navigation wall in the report,
    which makes it the expensive kind of wrong.
    """
    cpus = cpus or os.cpu_count() or 4
    return max(1, min(6, (cpus - lanes) // max(1, lanes)))


def build_agent_cmd(rom, seg, variant, vdir, baton, run_dir, sideloop_every=0, sideloop_parallel=None):
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
        # In-run heal ON, isolated per lane. When a lane's stuck streak crosses the terminal-wedge
        # threshold it races variants from its own wedged savestate and hot-applies the winner —
        # the mechanism the repo has always shipped in agent.py, which the relay disabled outright
        # from its first commit. It cannot be enabled naively: `healer.py` appends the winning
        # genome to a notes file and `agent.py` loads its baseline from one, so six parallel lanes
        # pointed at the repo's notes.md would race each other for the shared genome and each lane
        # would heal from another lane's baseline. Each lane therefore gets `genome.md` in its own
        # variant dir, seeded with that lane's genome (see race_variants) — a heal stays inside the
        # lane that wedged. `--no-self-heal` stays: the end-of-run healer writes the *shared*
        # notes.md, and a relay must not mutate the repo genome once per lane.
        "--in-run-heal-notes",
        str(vdir / "genome.md"),
        # Continuous self-heal: the advice inbox is how a healed genome reaches a *running* lane.
        # Per-lane like genome.md, and for the same reason — a shared inbox would hot-apply one
        # lane's winner into every other lane and destroy the only variable the relay controls.
        "--advice-inbox",
        str(vdir / "advice"),
    ]
    if sideloop_every:
        if sideloop_parallel:
            cmd += ["--sideloop-parallel", str(sideloop_parallel)]
        # The AlphaEvolve subloop: every N turns the lane snapshots itself, races variants from
        # that snapshot in the background and hot-applies the winner between turns. In-run heal
        # is reactive and one-shot (it waits for a terminal wedge); this heals the whole time.
        cmd += ["--sideloop-every", str(sideloop_every)]
    if seg.stop_on_map is not None:
        cmd += ["--stop-on-map", str(seg.stop_on_map)]
        if seg.stop_min_x is not None:
            cmd += ["--stop-min-x", str(seg.stop_min_x)]
    if seg.stop_on_badge is not None:
        cmd += ["--stop-on-badge", str(seg.stop_on_badge)]
    cmd += [a.format(run_dir=run_dir) for a in seg.extra_args]
    return cmd, {"EVOLVE_PARAMS": json.dumps(genome)}


def _kill_lane(proc):
    """Kill the lane's entire process group (uv run spawns python as a child; plain kill orphans it)."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError, AttributeError):
        proc.kill()  # test fakes and already-dead lanes
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def segment_success(fitness, seg):
    """Did this lane's final fitness satisfy the segment's stop condition?"""
    if not fitness:
        return False
    if seg.stop_on_map is not None:
        if fitness.get("final_map_id") != seg.stop_on_map:
            return False
        return seg.stop_min_x is None or fitness.get("final_x", -1) >= seg.stop_min_x
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


DEFAULT_MEMORY_DIR = WORKSPACE / "pokedex" / "memory"
DEFAULT_NOTES = WORKSPACE / "notes.md"


def _genome_diff(genome):
    """Only the knobs that differ from BASE_GENOME — the part worth remembering."""
    diff = {k: v for k, v in (genome or {}).items() if BASE_GENOME.get(k) != v}
    return ", ".join(f"{k}={v}" for k, v in sorted(diff.items())) if diff else "base"


def record_win(seg, winner, *, memory_dir, notes_path, run_dir):
    """Write a segment win back into the agent's own memory (best-effort, never raises).

    Always: an ``[important]`` line in ``<memory_dir>/observations.md`` — the same journal the
    observer and the Flink alerts-consumer write, so a relay win shows up next to the wedges it
    fixed. Optionally (``notes_path`` set): promote the winning genome into ``notes.md`` in the
    exact block ``load_genome_from_notes`` reads at agent startup, so the next plain run starts
    from it. Promotion is opt-in because a segment genome (e.g. flee-at-50% for the forest)
    becomes the *global* baseline.
    """
    f = winner.get("fitness", {})
    diff = _genome_diff(winner.get("genome"))
    content = (
        f"relay {seg.name} cleared by {winner['label']}: genome={diff}; "
        f"lead_hp={f.get('lead_hp')} turns={f.get('turns')} final_map={f.get('final_map_id')}; "
        f"run={run_dir}"
    )
    row = {
        "referenced_time": datetime.now(timezone.utc).isoformat(),
        "priority": "important",
        "content": content,
        "source_session": "relay",
    }
    try:
        append_observations(memory_dir, [row], dedupe=True)
    except OSError as exc:  # memory is a side channel; the relay result must survive it
        print(f"[relay] memory write-back skipped: {exc}")
    if notes_path is not None:
        try:
            reason = (
                f"- [{row['referenced_time'][:19]}Z] relay {seg.name} won by {winner['label']} "
                f"(turns {f.get('turns')}, lead_hp {f.get('lead_hp')}). Keep genome diffs: {diff}"
            )
            append_genome(notes_path, winner.get("genome") or {}, reason)
        except OSError as exc:
            print(f"[relay] notes promotion skipped: {exc}")


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
    sideloop_every=0,
):
    """Race up to `parallel` decision variants from the same baton; return (pick(results), results)."""
    if pick is None:
        pick = pick_winner
    lanes = {}
    lane_count = len(seg.variants[:parallel])
    subloop_parallel = sideloop_parallel_for(lane_count) if sideloop_every else None
    for variant in seg.variants[:parallel]:
        vdir = prepare_variant_dir(seg_dir, variant, baton)
        cmd, extra_env = build_agent_cmd(rom, seg, variant, vdir, baton, run_dir, sideloop_every, subloop_parallel)
        genome = json.loads(extra_env["EVOLVE_PARAMS"])
        # Seed the lane's private genome file so an in-run heal races from *this* lane's knobs.
        # healer.py's base is DEFAULT_PARAMS + whatever the notes file holds; without this the
        # heal would race from the defaults and hot-apply a winner tuned against the wrong lane.
        (vdir / "genome.md").write_text(
            f"# {seg.name}:{variant['label']} lane genome\n<!-- autotune:genome\n{json.dumps(genome)}\n-->\n"
        )
        log = open(vdir / "agent.log", "wb")
        proc = popen(
            cmd,
            env={**os.environ, **extra_env},
            cwd=str(WORKSPACE),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
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
            success = segment_success(fitness, seg)
            if seg.stop_on_map is not None or seg.stop_on_badge is not None:
                success = success and (vdir / "stop.state").exists()
            result = {
                "label": label,
                "vdir": vdir,
                "genome": genome,
                "fitness": fitness,
                "success": success,
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
                _kill_lane(proc)
                log.close()
                results.append(
                    {"label": label, "vdir": vdir, "genome": genome, "fitness": {}, "success": False, "killed": True}
                )
                print(f"[relay] {seg.name}/{label} killed (straggler)")
            lanes.clear()
            break
        sleep(2.0)
    report_inert_spread(seg, results)
    return pick(results), results


# Fitness keys that record what the lane DID, as opposed to how long the box let it run. Wall-clock
# noise must not disguise a spread that explored nothing.
_BEHAVIOUR_KEYS = ("turns", "final_map_id", "final_x", "final_y", "stuck_count", "battles_won", "maps_visited")


def report_inert_spread(seg, results):
    """Say so when every lane of a spread came back byte-identical.

    Genome variants only diverge on legs that read the knobs they set: the ROM-truth planner that
    owns Route 3 ignores stuck_threshold, waypoint_skip_distance and axis_preference_map_0
    entirely, so a NAV spread over those returns one lane's information for six lanes' compute —
    and the report looks like six independent confirmations rather than one result copied six
    times. Cheap to detect, and silence here is what made it cost 12,000 turns x 6 to notice.
    """
    scored = [r for r in results if r.get("fitness") and not r.get("killed")]
    if len(scored) < 2:
        return False
    signature = {tuple(r["fitness"].get(k) for k in _BEHAVIOUR_KEYS) for r in scored}
    if len(signature) > 1:
        return False
    print(
        f"[relay] NOTE {seg.name}: all {len(scored)} lanes returned identical fitness — the genome "
        f"knobs this spread varies are not read by this segment. Treat it as ONE sample, and see "
        f"NAV_SPREAD's note on which leg reads which knob."
    )
    return True


DEFAULT_ROM = WORKSPACE / "rom" / "Pokemon - Red Version (USA, Europe) (SGB Enhanced).gb"
DEFAULT_SEED = WORKSPACE / "demo-runs" / "states" / "route1.state"


def _select_segments(spec):
    if not spec:
        return list(SEGMENTS)
    by_name = {s.name: s for s in SEGMENTS}
    picked = []
    for name in spec.split(","):
        name = name.strip()
        if name not in by_name:
            raise KeyError(name)
        picked.append(by_name[name])
    return picked


def main(argv=None):
    parser = argparse.ArgumentParser(description="Divide-and-conquer relay to Mt. Moon")
    parser.add_argument("rom", nargs="?", default=str(DEFAULT_ROM))
    parser.add_argument("--segments", default="", help="Comma-separated segment names (default: all)")
    parser.add_argument("--parallel", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=1200.0, help="Per-segment wall clock (s)")
    parser.add_argument("--grace", type=float, default=90.0, help="Straggler grace after first success (s)")
    parser.add_argument("--seed-state", default=str(DEFAULT_SEED))
    parser.add_argument(
        "--seed-worldmap",
        default=None,
        help="Learned map (worldmap JSON) the seed starts from — e.g. the previous segment's "
        "winning lane's .worldmap. Each lane gets its own copy; the relay's default is a "
        "blank map so a lane rediscovers what the previous run already knew.",
    )
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print the lane commands; launch nothing")
    parser.add_argument("--memory-dir", default=str(DEFAULT_MEMORY_DIR), help="observations.md dir for win write-back")
    parser.add_argument("--notes", default=str(DEFAULT_NOTES), help="notes.md to receive --promote-genome blocks")
    parser.add_argument(
        "--promote-genome",
        action="store_true",
        help="Also append each segment winner's genome to notes.md (becomes the agent's global baseline)",
    )
    parser.add_argument("--no-memory", action="store_true", help="Disable all memory write-back")
    parser.add_argument(
        "--allow-concurrent",
        action="store_true",
        help="Run even if another relay holds the lock (the row it produces is not a verdict)",
    )
    parser.add_argument(
        "--sideloop-every",
        type=int,
        default=0,
        help="Turns between per-lane AlphaEvolve self-heal subloops (0 = off; 400 is a sane cadence)",
    )
    parser.add_argument(
        "--max-turns-scale",
        type=float,
        default=1.0,
        help="Multiply every segment's max_turns (e.g. 0.25 for a quick smoke)",
    )
    args = parser.parse_args(argv)

    try:
        segments = _select_segments(args.segments)
    except KeyError as exc:
        print(f"[relay] unknown segment: {exc.args[0]} (choose from {', '.join(s.name for s in SEGMENTS)})")
        return 1

    run_dir = (
        Path(args.run_dir)
        if args.run_dir
        else (WORKSPACE / "data" / "relay" / datetime.now(timezone.utc).strftime("%y%m%d-%H%M%S"))
    )
    baton = Baton(
        state_path=Path(args.seed_state),
        worldmap_path=Path(args.seed_worldmap) if args.seed_worldmap else None,
        genome={},
    )

    if args.dry_run:
        for seg in segments:
            scaled_seg = dataclasses.replace(seg, max_turns=max(1, int(seg.max_turns * args.max_turns_scale)))
            for variant in scaled_seg.variants[: args.parallel]:
                vdir = run_dir / scaled_seg.name / variant["label"]
                cmd, env = build_agent_cmd(args.rom, scaled_seg, variant, vdir, baton, run_dir, args.sideloop_every)
                print(f"# {scaled_seg.name}/{variant['label']}")
                print(f"EVOLVE_PARAMS='{env['EVOLVE_PARAMS']}' \\\n  {' '.join(cmd)}")
            print(f"# ... then baton = {run_dir / 'batons' / (seg.name + '.state')}")
        return 0

    if not Path(args.rom).exists():
        print(f"[relay] ROM not found: {args.rom}")
        return 1
    if not baton.state_path.exists():
        print(f"[relay] seed state not found: {baton.state_path}")
        return 1

    if not args.allow_concurrent:
        ok, holder = acquire_relay_lock()
        if not ok:
            print(
                f"[relay] REFUSED: relay pid {holder} is already running. Each relay launches up to "
                f"{args.parallel} emulators (plus subloops); running them in parallel starves every "
                "lane, and a starved lane reports as wedged — a CPU shortage read as a navigation "
                "wall. Wait for it, or pass --allow-concurrent (that run is not a verdict)."
            )
            return 2

    (run_dir / "batons").mkdir(parents=True, exist_ok=True)

    report = {"run_dir": str(run_dir), "segments": []}
    for seg in segments:
        winner = None
        attempts = []
        scaled = dataclasses.replace(seg, max_turns=max(1, int(seg.max_turns * args.max_turns_scale)))
        for attempt, seg_variant in enumerate((scaled, dataclasses.replace(scaled, max_turns=scaled.max_turns * 2))):
            seg_dir = run_dir / (seg.name if attempt == 0 else f"{seg.name}_retry")
            print(f"[relay] === {seg.name} (attempt {attempt + 1}, max_turns={seg_variant.max_turns}) ===")
            winner, results = run_segment(
                args.rom,
                seg_variant,
                baton,
                seg_dir,
                run_dir,
                parallel=args.parallel,
                timeout=args.timeout,
                grace=args.grace,
                sideloop_every=args.sideloop_every,
            )
            attempts.append(
                [
                    {
                        "label": r["label"],
                        "success": r["success"],
                        "killed": r.get("killed", False),
                        "fitness": r["fitness"],
                    }
                    for r in results
                ]
            )
            if winner is not None:
                break
        report["segments"].append(
            {"name": seg.name, "winner": winner["label"] if winner else None, "attempts": attempts}
        )
        if winner is None:
            _write_report(run_dir, report)
            print(f"[relay] FAILED at {seg.name} after 2 attempts — report: {run_dir / 'report.json'}")
            release_relay_lock()
            return 1
        baton = promote_winner(run_dir, seg, winner)
        f = winner["fitness"]
        print(f"[relay] {seg.name} -> {winner['label']} (turns={f.get('turns')} lead_hp={f.get('lead_hp')})")
        if not args.no_memory:
            record_win(
                seg,
                winner,
                memory_dir=Path(args.memory_dir),
                notes_path=Path(args.notes) if args.promote_genome else None,
                run_dir=run_dir,
            )

    _write_report(run_dir, report)
    print(f"[relay] CONQUERED {' -> '.join(s.name for s in segments)}")
    print(f"[relay] final baton: {baton.state_path} | report: {run_dir / 'report.json'}")
    release_relay_lock()
    return 0


def _write_report(run_dir, report):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
