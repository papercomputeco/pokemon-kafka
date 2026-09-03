# Seafoam Islands — explored floor-by-floor (2026-09-03)

**Part / goal.** Engage every body on every floor of Seafoam Islands (1F–5F), enter every warp,
record what each body says / does, then — the acceptance step — reach Cinnabar (map 8) and read
the Poké Gym door text.

**Baton.** `data/local_runs/roster-bench/seafoam_1f_safe.state` — Seafoam 1F (map 192), 6 badges,
party [Charizard L100, Dugtrio L100, Primeape L99, Pidgeot L99, Hypno L99, **Gyarados L20 73/73
(SURF)**]. Party is one-shot level; Gyarados is the only SURF user and stays lead-protected.

## The short version

* Seafoam here is a **5-floor vertical shaft**, maps **192 (1F) → 159 (2F) → 160 (3F) → 161 (4F) →
  162 (5F)**, each 30×18, joined only by interior doors (no exterior map between floors). 5F is a
  dead end (only exits back to 4F).
* Trainers were **engaged and defeated** on the floors I could reach (EXP gained each time); NPCs
  **talk** (e.g. 1F `(18,10)` → *"This requires STRENGTH."*).
* Many bodies and several interior doors sit on **"pad" tiles** that plain walking cannot enter —
  `walk`/`approach` report *no-path* / *not-reached* from the floor's main walkable region. These
  are only reached by the game's pad/ledge approach (riding onto the tile from a specific side),
  which the generic walker does not drive. That is the single biggest "what did I find" about
  these floors.
* **Cinnabar (map 8) is sealed from this save.** Established in-game and by ROM geometry, not lore
  (details + the 2026-09-03 sealed-region finding below), so the gym door text could not be read.

## Seafoam door/pad mechanism (the new part)

Seafoam's floors use a **tile-pair collision** rule (the "ledge/pad" mechanic). In tileset 17 the
pair set blocks stepping **between tile 0x05 and 0x20/0x2A/0x21/0x41** (and their reverses).
Consequences, measured against the game's accepted/rejected steps:

* Some **door tiles and body standing-tiles are in a pocket** that the floor's main region cannot
  `walk` into (BFS with the pair rule gives separate components; BFS without it does not — the
  pair rule is what seals the pockets, matching the live *no-path*).
* Example (1F map 192): the trainer at `(26,7)` and the 2F-door set are reachable, but certain
  pads are not from the entry tile. On 2F (159) the `(17,6)` NPC and the 3F doors `(4,2)/(13,7)`
  fell *no-path* from the pocket I was standing in after engaging `(22,6)`.
* This is **not** a bug and **not** SURF-arming; it is the game refusing the step. `road.walk`
  correctly honours it (returns *no-path*) — the walker simply has no pad-ride verb yet.

This generalises the earlier `seafoam-is-real-and-so-is-the-door-bug.md` finding: the door tile
can be a warp target the walker can't step onto.

## Floor-by-floor (map, bodies, warps)

Geometry from `scripts/rom_truth` extraction (`truth.json`); engagement from live play this
session + the prior Seafoam session. "reached" = the walker got beside the body and read/fought.

### 1F — map 192
* **Bodies:** NPC `(18,10)` — *reached*, said **"This requires STRENGTH."** (a STRENGTH boulder /
  ledge pad). Trainer `(26,7)` — **fought** (defeated, EXP gained); *not reachable by plain walk
  from the entry tile* (pad pocket).
* **Warps:** → **159 (2F)** at `(7,5)`,`(23,15)`,`(25,3)`; → **255 (outside/sea)** at `(4,17)`,`(5,17)`,`(26,17)`,`(27,17)`.
* **Enterable:** yes — used `(7,5)` → 2F.

### 2F — map 159
* **Bodies:** Trainer `(22,6)` — *reached, fought* (defeated, **379 EXP** this pass). NPC `(17,6)` —
  **not reached** (pad pocket, *no-path* from where I stood).
* **Warps:** → **160 (3F)** at `(4,2)`,`(13,7)`,`(19,15)`,`(25,11)`; → **192 (1F)** at `(7,5)`,`(23,15)`,`(25,3)`.
* **Enterable:** yes (from 1F). Interior 3F doors partly pad-sealed from the trainer pocket.

### 3F — map 160
* **Bodies:** Trainers `(18,6)` and `(23,6)` — **fought** (defeated, EXP gained in the prior
  Seafoam session).
* **Warps:** → **159 (2F)** at `(5,3)`,`(13,7)`,`(19,15)`,`(25,11)`; → **161 (4F)** at `(5,13)`,`(25,3)`,`(25,14)`.

### 4F — map 161
* **Bodies:** NPCs `(5,14)`,`(3,15)`,`(8,14)`,`(9,14)`,`(18,6)`,`(19,6)` — mostly **pad pockets**;
  the main-region one `(5,14)` is the reachable one. Several *no-path*.
* **Warps:** → **160 (3F)** at `(5,12)`,`(25,3)`,`(25,14)`; → **162 (5F)** at `(8,6)`,`(25,4)`,`(20,17)`,`(21,17)`.

### 5F — map 162 (dead end)
* **Bodies:** NPCs `(4,15)`,`(5,15)` (main region) and Trainer `(6,1)` — the trainer at `(6,1)` is
  in an **isolated single-cell pocket** (BFS: its own 1-cell component); the two `(15)` NPCs share
  the main region.
* **Warps:** → **161 (4F)** only, at `(11,7)`,`(20,17)`,`(21,17)`,`(25,4)`. No downward exit.
  ⇒ 5F is the bottom of the shaft.

## Cinnabar (map 8) — sealed from this save

Cinnabar's data (from the ROM extract): map 8, 20×18, **2 NPCs** at `(12,5)`,`(14,6)`, warps to
interior maps **165, 166 (the Poké Gym), 167, 171, 172**. The gym (166, 20×18) holds **8 trainers
+ the leader NPC `(16,13)`** (Blaine) and exits only to the outside (255). So the gym door text
lives at map 8's warp into 166 — which I could not reach.

**Why it's sealed** (in-game measurement + signature-located ROM geometry; see
`docs/learnings/badges7-8-baton-region-sealed-20260903.md`, same save family / party):

1. The map-31 sea the Seafoam and Cinnabar shores both front is **split by a solid 1-tile wall
   (row 1, all `0x3a`)**. Row 0 is a straight 100-cell east–west line that reaches Cinnabar at
   `(0,0)`, but its only entry is the east edge `(99,0)`.
2. Everything a crossing lands on (the Seafoam lagoon at `(48,6)`, the 30→31 landings at rows 5–16)
   is in a **different water component** (min x ≈ 48–63) that never touches row 0.
3. Confirmed live: `R.cross(31,8)` (Gyarados surfing) failed 4× in the prior run and again this
   session (`surfmoved-failed` from `(48,6)`) — the surf drifts in the lagoon pool and cannot
   cross to x=0. It is not a SURF-arming or battle problem (SURF arms, Gyarados holds 73/73).

**So:** reaching Cinnabar needs a *replaced baton* on the badge-cluster side (map 7 / Fuchsia
water, or a map past the 26/27 pockets), not more walking from Seafoam. The save is a valid 6-badge
checkpoint; the wall is the region topology, not the agent.

## What I still owe (honest gaps)

* Some pad-pocket bodies (1F `(26,7)` from the entry tile, 2F `(17,6)`, most 4F NPCs, 5F `(6,1)`)
  were **fought (trainers) or identified but not spoken to this pass** — the walker has no pad-ride
  verb. A `road.pad_ride` (approach from the tile the pair rule opens) would close this.
* The gym door text (maps 8→166) — blocked by the seal above.

## Files

* Driver: `data/local_runs/roster-bench/sf_floorlog.py`
* Captured log: `data/local_runs/roster-bench/seafoam_floorlog.jsonl`
* Prior sealed-region finding: `docs/learnings/badges7-8-baton-region-sealed-20260903.md`
* Prior door-bug finding: `docs/learnings/seafoam-is-real-and-so-is-the-door-bug.md`
