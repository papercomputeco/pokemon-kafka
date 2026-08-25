#!/usr/bin/env python3
"""Fan-out runner for parameter races.

Takes a work list (a healer variant grid by default), runs every arm through a
backend, and prints one JSON summary. Local is the default backend, so this is
useful with no cloud account at all; `--backend daytona` fans the same work
list out across one sandbox per arm.

    # serial, on this machine (default)
    uv run scripts/fanout/cli.py --rom rom/red.gb --variants 3

    # one sandbox per arm
    uv run scripts/fanout/cli.py --rom rom/red.gb --variants 3 \
        --backend daytona --snapshot pokemon-fanout-abc1234

Teardown is guaranteed for the daytona backend, including on Ctrl-C: the
KeyboardInterrupt path still runs the sweep before exiting non-zero.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
# Direct execution puts scripts/fanout on sys.path, not scripts/, so the repo's
# flat modules (evolve, healer) would not import. pytest already sets this up.
if str(SCRIPT_DIR.parent) not in sys.path:  # pragma: no cover - direct-execution only
    sys.path.insert(0, str(SCRIPT_DIR.parent))

from evolve import DEFAULT_PARAMS, score  # noqa: E402
from healer import RULES, sample_variants  # noqa: E402

from fanout import get_backend  # noqa: E402


def build_work_list(n: int, rule_name: str, seed: int) -> list[dict]:
    """The healer's own variant grid: resample only the implicated knobs.

    Reusing `sample_variants` rather than inventing a grid keeps the fan-out
    racing what the healer would have raced serially.
    """
    rule = next((r for r in RULES if r["name"] == rule_name), RULES[0])
    variants = sample_variants(DEFAULT_PARAMS, rule["params"], n, random.Random(seed))
    for i, variant in enumerate(variants):
        variant["label"] = f"{rule['name']}-{i}"
    return variants


def summarize(
    results: list[dict], elapsed: float, backend_name: str, cohort: str, turns: int = 0, strategy: str = "low"
) -> dict:
    ranked = sorted(results, key=lambda r: r["score"], reverse=True)
    return {
        "cohort": cohort,
        "backend": backend_name,
        # Provenance: scores are only comparable across runs at the same turn
        # budget and tier, so the summary records both.
        "turns": turns,
        "strategy": strategy,
        "arms": len(results),
        "elapsed_seconds": round(elapsed, 1),
        "winner": ranked[0]["label"] if ranked else None,
        "results": ranked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fan out a parameter race across a backend")
    parser.add_argument("--rom", required=True, help="Path to the ROM (uploaded per sandbox, never baked)")
    parser.add_argument("--backend", choices=["local", "daytona"], default="local", help="Default: local")
    parser.add_argument("--variants", type=int, default=3, help="Number of arms to race")
    parser.add_argument("--turns", type=int, default=500, help="Max turns per arm")
    parser.add_argument("--rule", default="navigation-thrash", help="Which healer rule's knobs to resample")
    parser.add_argument("--seed", type=int, default=0, help="Seed for variant sampling (reproducible grids)")
    parser.add_argument(
        "--strategy",
        choices=["low", "medium", "high"],
        default="low",
        help="Agent decision tier. low (default) makes zero LLM calls; medium/high emit "
        "traffic through the capture sidecar and cost money.",
    )
    parser.add_argument("--snapshot", help="Daytona snapshot name (required for --backend daytona)")
    parser.add_argument("--cohort", help="Tag grouping this fan-out in the capture store (default: auto)")
    parser.add_argument("--concurrency", type=int, default=5, help="Max sandboxes in flight")
    parser.add_argument("--output-json", help="Write the summary JSON here as well as stdout")
    args = parser.parse_args(argv)

    rom = Path(args.rom)
    if not rom.exists():
        print(f"[fanout] ROM not found: {rom}", file=sys.stderr)
        return 2

    cohort = args.cohort or f"fanout-{args.rule}-{args.seed}"
    candidates = build_work_list(args.variants, args.rule, args.seed)

    kwargs = {}
    if args.backend == "daytona":
        if not args.snapshot:
            print("[fanout] --backend daytona requires --snapshot", file=sys.stderr)
            return 2
        kwargs = {"snapshot": args.snapshot, "cohort": cohort, "concurrency": args.concurrency}
    backend = get_backend(args.backend, **kwargs)

    print(
        f"[fanout] {len(candidates)} arms | backend={args.backend} | strategy={args.strategy} "
        f"| turns={args.turns} | cohort={cohort}",
        file=sys.stderr,
    )
    if args.strategy != "low":
        print(f"[fanout] strategy={args.strategy} makes real LLM calls — this run costs money", file=sys.stderr)

    start = time.time()
    try:
        fitnesses = backend.run_batch(
            str(rom.resolve()), args.turns, candidates, load_state=None, strategy=args.strategy
        )
    except KeyboardInterrupt:
        # The backend's own finally-block has already swept its sandboxes by
        # the time this is reached; say so plainly rather than exiting silent.
        print("\n[fanout] interrupted — sandboxes torn down", file=sys.stderr)
        return 130

    elapsed = time.time() - start
    results = [
        {
            "label": c.get("label", f"arm_{i}"),
            "params": {k: v for k, v in c.items() if k != "label"},
            "fitness": f,
            "score": score(f),
        }
        for i, (c, f) in enumerate(zip(candidates, fitnesses))
    ]
    summary = summarize(results, elapsed, args.backend, cohort, turns=args.turns, strategy=args.strategy)

    payload = json.dumps(summary, indent=2)
    print(payload)
    if args.output_json:
        Path(args.output_json).write_text(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover - entrypoint
    sys.exit(main())
