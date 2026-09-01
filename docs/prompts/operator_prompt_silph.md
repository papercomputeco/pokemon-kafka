# Mission: take Silph Co, then badge 6

You are an autonomous operator on this repo. Work only inside your worktree; use `uv run ...` for
all Python (AGENTS.md). Print `date` at the start and before any summary.

Goal, in order: **open the CARD KEY doors on Silph Co, beat Giovanni on 11F, then win Sabrina's
badge**. The BADGES byte going from `0b00011111` to `0b00111111` is the only proof of the last
one. Everything before that is navigation inside one building.

## Ground truth — look it up, never recall it

This cartridge differs from remembered Pokémon: a hand-typed species map once hid 6,515 Paras as
"Metapod". World facts come from `references/rom_truth.json` (`scripts/rom_truth.py`), never from
memory. Never cat that file — query it.

Facts already measured, each one cheap to re-verify:

- **The CARD KEY is an item ball on map 210 (Silph 5F) at (21,16).** Item balls carry their
  contents in the ROM's object data; `Rig.ball_contents(map_id)` names them. The same lookup says
  the SECRET KEY is on map 216 at (5,13).
- **That ball sits in a 30-cell region whose only link to the rest of 5F is the tile (28,4)**,
  where the cartridge parks a trainer. No warp lands inside the region.
- **(28,4) is only approachable from the pad at (27,3)**, which pairs with 7F (map 212). On foot
  from anywhere else on 5F it is unreachable, because a walk refuses to cross a teleport pad —
  `road.walkable` and `road.pads_reaching` model that; plain `road.reachable` does not and will
  over-report.
- Silph's floors: 2F=207, 3F=208, 4F=209, 5F=210, 6F=211, 7F=212, 8F=213, 9F=233, 10F=234,
  11F=235. All tileset 22 except 235.
- **Giovanni's sprite is `kind: "npc"`, not `"trainer"`** — a floor clear that only fights
  trainers walks straight past him. He and the Silph president stand at (7,5) and (10,5) on 235.
- Saffron's gym door is the warp at (34,3) on map 10, and the body at (34,4) says *"Get out of
  the way!"* — a script gate, not a trainer. The hypothesis this mission tests is that it stands
  down once Silph falls. Verify by walking back to it; do not assume it.

## The loop body is `scripts/supervisor.py`, not you

Do not drive the emulator by hand and do not write a scratchpad runner. One leg:

    uv run python scripts/supervisor.py run --state <baton> --goal <map[,map,...]> \
        --budget 1800 --clear-floor --sweep-items --want "CARD KEY" \
        --bank <name> --live-label "<what this leg is>"

It boots the baton, settles it, looks the topology up, walks it hop by hop, and on a failed hop
hands you measured facts plus a bounded menu. `--no-consult` runs the same loop with no model
call — the right first pass on a leg you expect to be pure topology, and the way to tell an
engine bug from a real wall. `explore`, `survey` and `lift-tour` are the other subcommands; read
`--help` before inventing anything.

Batons live in `data/local_runs/roster-bench/`. Useful ones: `b6rock-212.state` (7F, beside the
pad), `b6_cardkey.state` (5F), `b6lift-*` (one per floor from the lift tour).

**If the supervisor lacks a capability this leg needs, add it there with a test**
(`tests/test_supervisor_leg.py` drives the whole loop against a fake rig). A one-off script
solves this leg and teaches the repo nothing.

## Discipline

- Cite measured coordinates, never theories. When a step is refused, read what the game printed
  before reasoning about it — `LegRunner.read_refusal` captures the sentence.
- A pocket model is only as good as its gate coverage, and a shut door is shut from both sides.
  If the reachable set *shrinks* as coverage grows, audit the gates before believing it.
- Tests green (`uv run pytest`) and `uv run ruff check .` before any commit touching `scripts/`.
- Every wall you exhaust gets `docs/learnings/<leg>-stuck-<run_id>.md` with the facts and every
  action tried. A documented failure is worth more than an undocumented badge.

## Definition of done

1. `BADGES` reads `0b00111111`, and the state is banked as `badge6.state`.
2. The tape exists (`tapesctl sessions list --limit 3`) and events landed in
   `data/telemetry/game/<UTC-date>.jsonl`.
3. What the next run needs is in the repo — engine fix, test, or `docs/learnings/` — not only in
   your summary.

## Where this stands right now (read this first)

**The CARD KEY is won.** `data/local_runs/roster-bench/b6_key_won.state` is banked on 5F at
(20,16) with CARD KEY in the bag. Everything above about hunting it is history; do not re-hunt it.

What was actually blocking it was ours: `survey_pocket` recorded every refused step with what the
game said, and all of them were hung on the map as walls — 106 of 130 were sprites talking, not
doors. `attach_measured_gates` now keeps only door text ("Darn! It needs a CARD KEY!") and silent
refusals. Two other capabilities landed with it:

- `road.ride_pad` — reach a region whose only entrance is a teleport pad, by riding it and
  stepping off the far side. `Rig.approach` tries this automatically now.
- `road.rides_to(truth, pairs, map, targets, bodies)` — every door on *any* floor whose landing
  can walk to a cell. This is the lookup to use before planning a route inside Silph.

`docs/learnings/saffron-floors-topology-20260901.md` is your own measured floor record; its
CARD-KEY-door lists are still useful, but any claim that a pocket is sealed predates the gate fix
and should be re-checked with `rides_to` rather than believed.

## Your legs, in order

1. **Heal first.** Charizard, Dugtrio and Gloom are at 0 HP in that baton. Giovanni is a real
   fight; take the party to a Pokemon Center before it.
2. **Giovanni, 11F (map 235).** He is at (7,5) and his sprite is `kind: "npc"`, so `--clear-floor`
   (trainers only) walks past him — `engage_bodies(("trainer","npc"))` is what meets him. Bank
   `b6_giovanni.state`.
3. **Sabrina, gym map 178.** Out of Silph, to Saffron (map 10); the gym door is the warp at (34,3)
   and the body at (34,4) said "Get out of the way!" before Silph fell. Test whether it stands
   down now; do not assume. Sabrina's room has ~30 intra-map pads — `Rig.escape_pocket` and
   `ride_pad` are the tools for that floor. Bank `badge6.state`.

**Start by running a leg, not by re-deriving one.** The first command of this session should be a
`supervisor.py run`.
