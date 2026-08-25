"""Local backend — the default, and the behavior races have always had.

Runs each variant in-process order on this host via `evolve.run_agent`, one at
a time. This is deliberately the same serial loop `healer.run_race` used
before backends existed: the local path is the baseline a fan-out is measured
against, so it stays boring and unchanged.
"""

from __future__ import annotations

from evolve import run_agent


class LocalBackend:
    """Serial, single-host racing. No credentials, no network, no teardown."""

    name = "local"

    def run_batch(
        self,
        rom: str,
        turns: int,
        candidates: list[dict],
        load_state: str | None = None,
        strategy: str = "low",
    ) -> list[dict]:
        return [run_agent(rom, turns, params, load_state=load_state, strategy=strategy) for params in candidates]
