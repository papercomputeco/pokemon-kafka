#!/usr/bin/env python3
"""Side-agent harness: an AlphaEvolve subloop raced from a live run's snapshot.

The game's while loop is the harness: agent.py snapshots its live state and spawns this
process (--sideloop-every). We fan out short bounded lanes from that snapshot, score them
with evolve.score, and append the winning genome to the live run's advice inbox as a
pokemon.advice.v1 genome_patch line — the game hot-applies it between turns and never stops.
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from advice import SCHEMA_ADVICE
from evolve import score
from relay import BATTLE_SPREAD, Baton, Segment, run_segment


def sideloop_segment(horizon, variants=BATTLE_SPREAD):
    """A stop-less segment: lanes run to the horizon and are compared by score, not arrival."""
    return Segment("sideloop", stop_on_map=None, stop_on_badge=None, max_turns=horizon, variants=variants)


def pick_by_score(results):
    """Best lane by evolve.score; lanes with no fitness never win."""
    scored = [r for r in results if r["fitness"]]
    if not scored:
        return None
    return max(scored, key=lambda r: score(r["fitness"]))


def advice_line(genome, source="sideloop"):
    return json.dumps(
        {
            "schema": SCHEMA_ADVICE,
            "id": f"{source}-{uuid.uuid4().hex[:8]}",
            "type": "genome_patch",
            "source": source,
            "data": genome,
        }
    )


def run_sideloop(rom, state_path, genome, work_dir, advice_out, horizon=800, parallel=4, timeout=600.0, **race_kwargs):
    """Race lanes from the snapshot; append the winner's genome as advice. Returns the winner."""
    # Subloop lanes are the low-priority tenant of the box-wide emulator pool: they ask for a slot
    # with no wait, so under load a heal is skipped (the lane logs "SIDELOOP | finished rc=1")
    # instead of queuing behind — and starving — the very lane it is trying to heal.
    os.environ.setdefault("POKEMON_SLOT_WAIT", "0")
    baton = Baton(state_path=Path(state_path), worldmap_path=None, genome=genome)
    seg = sideloop_segment(horizon)
    winner, _results = run_segment(
        rom,
        seg,
        baton,
        Path(work_dir) / "lanes",
        Path(work_dir),
        parallel=parallel,
        timeout=timeout,
        pick=pick_by_score,
        **race_kwargs,
    )
    if winner is None:
        return None
    advice_out = Path(advice_out)
    advice_out.parent.mkdir(parents=True, exist_ok=True)
    with open(advice_out, "a") as f:
        f.write(advice_line(winner["genome"]) + "\n")
    print(f"[sideloop] winner={winner['label']} -> {advice_out}")
    return winner


def main(argv=None):
    parser = argparse.ArgumentParser(description="AlphaEvolve subloop from a live snapshot")
    parser.add_argument("rom")
    parser.add_argument("--state", required=True)
    parser.add_argument("--genome-json", default="{}")
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--advice-out", required=True)
    parser.add_argument("--horizon", type=int, default=800)
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args(argv)
    winner = run_sideloop(
        args.rom,
        args.state,
        json.loads(args.genome_json),
        args.work_dir,
        args.advice_out,
        horizon=args.horizon,
        parallel=args.parallel,
        timeout=args.timeout,
    )
    return 0 if winner is not None else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
