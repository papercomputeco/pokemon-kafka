# Closed-Loop Feedback: Advice Inbox, Unlimited Runs, Envelope Identity

**Date:** 2026-08-14
**Status:** Approved

## Goal

Let one agent process run indefinitely while stream-derived anomalies and
observations feed back *into the live session* for unblocking and
self-healing — instead of landing in `observations.md` / `notes.md` where
they are only read at the next session start.

## Current state

Outbound is complete: agent → JSONL (`scripts/publisher.py`) → bridge →
local Kafka → Flink (windowed anomaly queries) → `agent.telemetry.alerts`
→ alerts-consumer → `pokedex/memory/observations.md` + `alerts.jsonl`.

Inbound has one live path: the in-run heal (`agent.py`), triggered by the
agent's *own* stuck-streak counter, which races healer variants from a
wedged savestate and hot-applies the winning genome via
`apply_genome_live`. Stream-derived signals (Flink alerts) cannot reach a
running session, and `run()` is bounded by `for _ in range(max_turns)`
with fitness written only at end of run.

## Decision

Mirror the outbound design: the agent stays **broker-free**, and feedback
arrives as **JSONL files in an inbox directory** the agent polls between
turns. Writers (today the Flink alerts-consumer; later the healer, an
operator, or a cassette) append `pokemon.advice.v1` lines; the agent
reads new complete lines with the same byte-offset discipline the
game-event bridge uses.

A future pokemon-cassette's `advise` surface writes the same envelope to
the same inbox — this spec defines the contract it will target.

## Components

### Envelope identity (prerequisite)

`pokemon.game.v1` events gain two additive fields, stamped by
`GameEventCollector`:

- `run_id` — the recorder's run id when recording, otherwise a generated
  id; the future Kafka partition key (today the bridge keys every message
  by the constant `schema` value, collapsing ordering into one partition).
- `event_id` — `"<run_id>:<seq>"`, monotonic per collector; the
  at-least-once dedup key for downstream consumers.

Additive only: Flink's fixed ROW schema and all existing consumers ignore
unknown JSON fields.

### Advice envelope (`pokemon.advice.v1`)

```json
{
  "schema": "pokemon.advice.v1",
  "id": "flink:LOW_HP_GRIND:3f2a9c1d8e40",
  "type": "genome_patch" | "note",
  "data": { },
  "expires_at": "2026-08-14T12:00:00Z",
  "source": "flink:LOW_HP_GRIND"
}
```

- `genome_patch`: `data` is a partial genome; the agent clamps it with
  `evolve.clamp_params` and hot-applies via the existing
  `apply_genome_live` path.
- `note`: `data.text` is appended to the strategy notes (`MemoryFile`)
  when a notes file is configured, and always logged + emitted as a
  `milestone` event so it lands in the Pokédex feed.
- `expires_at` is the poisoning guard (the stale-worldmap /
  hard-block-expiry lesson): expired advice is dropped, never applied.
  Absent = never expires (an operator's explicit choice); unparseable =
  dropped. Applied ids are remembered per run, so at-least-once writers
  are safe.

### Agent inbox polling

`scripts/advice.py` (new): pure functions `poll_inbox(dir, offsets)`
(sorted `*.jsonl`, complete lines only, malformed lines skipped) and
`is_expired(advice, now)`. `PokemonAgent` gains `--advice-inbox DIR` and
`--advice-poll-turns N` (default 50): a `_tick_advice()` hook next to
`_tick_in_run_heal()` polls every N loop turns and applies new advice.
Inbox failures log and never break the run.

### Unlimited runs + rolling fitness

- `--max-turns 0` = unlimited: the run loop becomes a `while` on
  `max_turns <= 0 or loop_turns < max_turns`.
- `--fitness-every N` rewrites the `--output-json` path with
  `compute_fitness()` every N turns, so healer rules and observers can
  evaluate a live window on a run that never ends.

### Alerts → inbox

The alerts-consumer (already writing `observations.md` + `alerts.jsonl`)
gains a third sink: when `ADVICE_INBOX_DIR` is set, each alert is shaped
into a `note` advice (deterministic id = alert-type + content hash, TTL
from `ADVICE_TTL_SECONDS`, default 600) and appended to
`<inbox>/advice.jsonl`. docker-compose points it at
`/memory/inbox` (the existing `./pokedex/memory` mount).

### Resource-exhaustion detection (Flink)

The existing rules catch the agent not *moving*. Two new rules catch it
not *surviving* — the class behind the reproducible turn-385 Viridian
Forest blackout (HP bleeding across fights, no heals):

- `LOW_HP_GRIND`: 10+ battle events in 2 minutes with lead HP ≤ 25% of max.
- `BATTLE_LOSS_STREAK`: 2+ `battle_end` events with `won = false` in
  10 minutes (the ROW gains a `won` BOOLEAN column).

## Out of scope

- The pokemon-cassette itself (separate repo; consumes this contract).
- `heal_now` advice type (the in-run heal already self-triggers).
- Exactly-once inbox delivery; per-run inbox directories.
- Any change that makes the agent process broker-aware.

## Testing

Everything under `scripts/` stays inside the 100% coverage gate; the
alerts-consumer follows the existing stubbed-`confluent_kafka` pattern in
`tests/test_alerts_consumer.py`. No live agent sessions are run —
verification is `uv run pytest --cov` + ruff only (agent runs route
through paperd and are sandbox-only by project policy).
