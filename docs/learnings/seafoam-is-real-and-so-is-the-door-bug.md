# Seafoam Islands is real ground, and a settle-on-entrance bug that hid it (2026-09-03)

**Result:** we are inside Seafoam Islands — map 192, then map 159 — for the first time this
project has ever managed. Verified live, badges intact at `0b00111111`. Batons:
`door_check.state` (192, 4, 17, right on the entrance), `seafoam_1f_safe.state` (192, 4, 16, one
step clear of it), `seafoam_progress.state` (159, 25, 7).

## The door was never the problem; two automated legs were

A sign on this exact water reads **"SEA ROUTE 19: FUCHSIA CITY - SEAFOAM ISLANDS"** — this sea's
real name, not Cinnabar's. The dry-land patch around x 46–61, y 2–11 on map 31 is Seafoam Islands
itself, with two doors into it at (48,5) and (58,9). A leg walked over (58,5) — three tiles from a
door — and kept going. A second leg, briefed with the exact coordinates, reached the door tile at
15:55 and then stalled out completely: zero telemetry for the rest of its three-hour budget,
burning all 8 of the harness's silent-turn continuations before dying with nothing written down.

Walking it by hand once, the door worked on the first try. Whatever broke both automated
attempts was not the game.

## Strength gates part of Seafoam — measured, not assumed

The first NPC inside answers exactly: **"This requires STRENGTH."** So the operator's instinct
from earlier today was correct, in the correct place: Strength is a real gate in this arc, just
inside Seafoam's interior rather than on the open sea, where nothing is pushable at all (checked
separately — map 31 lists no boulder-type sprites, only trainers).

It does not block everything. The route to the second floor doesn't need it: talking to the
second NPC and the SWIMMER/trainer bodies (Shellder, Psyduck, Seel — all easy KOs) still opens a
walk to (7,5), which warps straight through to map 159.

## The bug that made a working door look broken

Booting `door_check.state` with the default auto-settle landed on **map 31**, not 192 — the save
looked corrupted. It was not. `Rig.probe_step()` tries the plain floor tiles around the player
first and only uses a warp as a last resort, specifically so a state wedged in a doorway can still
prove it accepts input. At Seafoam's own entrance, rock walls the alcove on three sides, so every
"floor" try refused — and the *only* tile that accepted a step was the warp back outside. The
probe returned success (input works, technically true) and silently carried the whole save back
through the door with it. `settle()` — which every `Rig()` boot runs by default — saw that success
and considered itself done, with no sign anything had moved.

Fixed: the last-resort branch now prints which map it warped from and to. It does not change the
behaviour — a doorway that can only be proven by leaving still gets left, because that is a
correct proof of input — but the move is no longer silent. Anyone loading a baton banked at a real
entrance will see it in the log instead of quietly getting a different map back.

**Practical rule this teaches:** never bank a state standing directly on a warp tile. Step one
tile clear of it first — `seafoam_1f_safe.state` exists because of exactly this.

## What is still open

- Map 159's own warps (`(5,3)`, `(13,7)`, `(19,15)`, `(25,11)` → map 160; three more → map 192)
  have not been walked. Map 160 is untouched.
- Whether Seafoam actually connects through to Cinnabar, or only to more of itself, is unproven —
  we are two floors in, not out the other side.
- HM04 (Strength) is still not in the bag. Where it comes from is not yet found; the Fan Club and
  the bike shop are the only two "no item ball, ask a person" NPCs identified so far this arc, and
  neither one is Strength's giver.
- Two automated legs died on this exact task without producing a record. The mission file
  (`docs/prompts/operator_prompt_cinnabar_shore.md`) may simply be too dense — packed with a
  terrain diagram, four screenshots, and a coordinate box — for this model to act on rather than
  reason about indefinitely. A leaner, single-instruction mission is worth trying before assuming
  the model is at fault.
