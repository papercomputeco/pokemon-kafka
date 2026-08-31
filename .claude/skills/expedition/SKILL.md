---
name: expedition
description: Use when running any Pokémon Red progress leg in this repo — badges, dungeons, routes, item hunts, "keep playing", "get badge N", "solve <map>". Casts the measured crew (Point Man / Extractor / Wheelman) through the semantic router, keeps every call captured in tapes and every run event in the game sink, and enforces the ground-truth rules. Read this BEFORE writing a run script.
---

# Expedition — how a leg is run here

The goal is not "beat the game". The goal is **a system that beats the game and compounds**:
local models play, the router casts them, the ROM is the only source of world facts, and every
run leaves behind a tape, an event stream, and a repo change. A badge won by hand teaches the
repo nothing and is worth less than a documented failure.

`docs/expedition-spec.md` already ruled on this. Its own table says the loop that converges is
run → learnings → merge → rerun, "**but a human is the loop body**". This skill exists to keep
the human — and Claude — out of the loop body.

## The crew (titles earned by benchmark, not vibe)

From `benchmarks/2026-08-22-skill-matrix.md`, six models × three skill-isolated legs:

| seat | model | takes |
|---|---|---|
| **The Point Man** | `qwen38-27b-128k` | navigation — best line of six (49 t / 36 HP) |
| **The Extractor** | `kimi-k2.6:cloud` | puzzle — deepest of six (B2F, 18 tiles), top puzzle screen 0.55 |
| **The Wheelman** | `laguna-xs-128k` | battle — 6/6, an execution baseline |

The caller is the router: `references/semantic_router.yaml` via `scripts/semantic_router.py`.

```bash
uv run python scripts/semantic_router.py missions          # the casting table
uv run python scripts/semantic_router.py route "<the leg>" # which seat this leg belongs to
```

**Anthropic is not a seat.** Puzzle escalates to the Extractor, never to Claude. When the
Extractor is exhausted, write the failure down (below) and hand it to the operator — Opus is a
decision a human makes holding a failure record, not a rung the loop climbs.

## The rules

1. **Model Pokémon knowledge is untrusted.** This ROM differs from recollection, and the cost
   is measured: a hand-typed species map hid 6,515 Paras as "Metapod", and a recalled type
   chart carried an ice→fire rule this cartridge does not have. World facts come from
   `references/rom_truth.json` (maps, warps, grids, ledges, tile pairs), `references/type_chart.json`,
   the encounter catalog, or live measurement. Say so in the prompt when handing facts to a model.
2. **Topology is a lookup, not a search.** `rom_truth.route(A, B)` and the extracted warp/
   connection tables answer "how do I get from A to B". Re-deriving it by walking into walls is
   the single largest measured waste in this project.
3. **Tile IDs are per-tileset.** `20/21/30` are spin arrows **only in tileset 22** (Rocket
   Hideout). On tileset 0 routes, `0x30` is ordinary path. Check `map["tileset"]` before reusing
   any tile-id meaning.
4. **Bodies are not walls, and trainers never move.** `road.live_bodies()` gives live positions;
   wandering NPCs clear if you wait (PR #113), but a trainer in a one-tile corridor is permanent
   — plan a different entry row instead. Compute the **body-aware** reachable region before
   choosing an edge cell to cross at; "nearest edge cell" picks walled-off strips.
5. **Every model call goes through the tapes proxy** at `http://localhost:42345/v1/chat/completions`
   (config: provider openai, upstream 11434). A call straight to `:11434` is an uncaptured call.
   Ollama thinking models put the answer in `message.reasoning` when `content` is empty — read both.
6. **Every run emits events** to `data/telemetry/game/<UTC-date>.jsonl` with a stable `run_id`.
   That sink is what the benchmarks mine; a run that doesn't emit is unminable.
7. **Fix the engine, don't fork the scratchpad.** When `rig.drive()` or the road engine fails,
   the convergent move is to repair `scripts/` and merge it. A one-off scratchpad script solves
   this leg and teaches the repo nothing; six of them in a day is how a session drifts.
   Scratchpad needs a stated reason, not a default.
8. **Exhaustion is written down.** When the ladder ends without a solution, write
   `docs/learnings/<leg>-stuck-<run_id>.md` with the measured facts and every action tried, and
   emit `supervisor.exhausted`. Then stop.

## Running a leg

```bash
uv run python scripts/semantic_router.py route "reach saffron and beat sabrina"   # cast the seat
uv run python scripts/supervisor.py run \
    --state data/local_runs/roster-bench/<baton>.state \
    --goal 10,181,178 \            # one boot, a chain of legs; banked between each
    --budget 7200 --engage \       # --engage: on the LAST goal, engage bodies until BADGES changes
    --bank badge6 --live-label "badge 6 — sabrina"
```

The supervisor is the loop body: deterministic Python measures and moves. It boots the baton
(`scripts/expedition_rig.py`), **settles** it — a state banked mid-dialogue swallows every step,
which is how `BADGE5.state` once fingerprinted a wall that was not in the world — looks the
topology up in the extracted truth, and walks it hop by hop. On a failed hop it hands **measured
facts** plus a bounded menu of actions the road engine can actually execute to the seated model
and executes the choice. Models pick actions; they never drive the emulator directly. A wrong
answer costs one attempt; an *unparsed* answer is a non-answer and moves nothing.

`--no-consult` runs the same loop deterministically, never calling a model — the right first
pass on a leg you expect to be pure topology, and the way to tell an engine bug from a real wall.

If the supervisor lacks a capability the leg needs, add it there (with a test) rather than
writing a parallel script. `tests/test_supervisor_leg.py` drives the whole loop against a fake
rig, so a new action or menu costs one test, not a cartridge.

## When a search says "impossible"

Suspect the **state key** before the world. Spin-tile movement depends on the player's *facing*
(`0xC109`); a position-only BFS silently prunes hold-arrivals and declares solvable mazes
unsolvable. Rocket Hideout B4 stood for weeks against an 880-state oracle for exactly this
reason, and fell in 721 states once facing entered the key. Facing belongs in the state key for
any tile-driven puzzle — spinners, ice, currents.

## Definition of done for a leg

- the objective state is banked under `data/local_runs/roster-bench/`
- the tape exists (`tapesctl sessions list --limit 3` shows it)
- events landed in `data/telemetry/game/<date>.jsonl`
- anything learned that a future run needs is in the repo (engine fix, test, or `docs/learnings/`)
  — not only in a chat summary
