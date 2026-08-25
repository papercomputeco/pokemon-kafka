"""Backend contract for racing parameter variants.

A race is N independent short agent runs that differ only in their navigator
params. `healer.run_race` produced them serially on one host; a backend is the
seam that lets the same work list run somewhere else without the callers
knowing. Local is the default and behaves exactly as the serial loop did.

The unit of work matches `evolve.run_agent`: (rom, turns, params) -> fitness
dict. Backends return fitness dicts positionally aligned with `candidates`, so
a caller can zip them back together. A backend never raises for a single failed
run — it returns `degraded_fitness()` in that slot, mirroring how
`evolve.run_agent` already absorbs a timeout or crash. One bad variant must not
abort a race.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


def degraded_fitness(max_turns: int) -> dict:
    """The fitness a failed run reports.

    Byte-identical to `evolve.run_agent`'s except-branch so a failure scores the
    same however it was produced. `score()` reads these keys directly, so a
    missing key would raise instead of ranking last.
    """
    return {
        "turns": max_turns,
        "battles_won": 0,
        "maps_visited": 0,
        "final_map_id": 0,
        "final_x": 0,
        "final_y": 0,
        "badges": 0,
        "party_size": 0,
        "stuck_count": max_turns,
    }


@runtime_checkable
class RaceBackend(Protocol):
    """Runs a list of parameter variants and returns their fitness dicts."""

    def run_batch(
        self,
        rom: str,
        turns: int,
        candidates: list[dict],
        load_state: str | None = None,
        strategy: str = "low",
    ) -> list[dict]:
        """Return one fitness dict per candidate, in candidate order.

        `strategy` is the agent's decision tier. It defaults to "low" — the
        heuristic tier, which makes zero LLM calls — so racing stays free and
        deterministic unless a caller opts into an LLM tier.

        Body is intentionally the docstring alone: an `...` here would be an
        unexecutable line that the repo's 100% coverage gate would flag.
        """
