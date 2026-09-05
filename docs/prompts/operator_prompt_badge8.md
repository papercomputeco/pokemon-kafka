# Mission: badge 8 — Giovanni in the Viridian gym (map 45)

Wheelman seat (battle). `uv run ...` for Python. Print `date` at start and before any summary. Screenshot every
refusal. Journal every measured fact (`append_observations`, `source_session:"extractor"`, content `map=45 ...`).

## Baton

`data/local_runs/roster-bench/gym8_inside.state` — inside map 45 at (16,16), just off the door mats (16,17)/(17,17).
Seven badges. Party (all healed): Gyarados L100 (SURF/HYPER BEAM/BITE/STRENGTH), Dugtrio L100, Pidgeot L100
(FLY), Hypno L99, Articuno L100 (MIST/ICE BEAM/FLY/BLIZZARD), Charizard L100. Bag: 31 ULTRA BALL, 5 HYPER POTION.
Money 58,128. Outside bank: `viridian_main.state` (map 1 (23,28)).

## Measured (journal: grep `map=45`, `map=1 Viridian door`)

- The gym door (Viridian (32,7)) opens with seven badges; it was shut earlier in the run.
- Floor: 20x18, tileset 7, one ROM pocket (244 cells); the step survey from the entrance stands on 171 of them.
  Bodies: nine trainers at (2,1) (12,7) (11,11) (10,7) (3,7) (13,5) (10,1) (2,16) (6,5); an NPC at (16,15)
  ("VIRIDIAN GYM was closed for a long time"); an ITEM ball at (16,9).
- Tiles (`references/rom_truth.json`, map 45): floor 0x11. **0x4c is a SPINNER**: stepping onto (13,16) from
  (14,16) slid the player left to (8,16); (13,17) the same. Cells: (19,1) (18,2) (4,6) (16,10) (13,16) (13,17).
  **0x3f is a STOP tile** (you land and stay): (11,1) (17,2) (19,2) (0,7) (1,9) (18,11) (16,12) (4,13) (13,13)
  (13,14) (7,16) (1,17). 0x4d at (11,2) (5,13) (4,14) and 0x3c at (19,11) (0,15) (1,15): not yet stepped on
  deliberately — measure the direction of each before planning across them.
- Trainers challenge on sight: the survey's "talking walls" at (12,8..10) LEFT, (1,7), (15,5)/(16,5), (5,16)
  are their sentences, and `rig.walk(..., battle=rig.battle)` wins those fights (the L100s one-shot).
- `rig.walk` derails on spinners (planned over the ROM grid, which calls them floor). Drive spinner rows by a
  single press and read where you land; plan from the landing.

## The job

1. `supervisor run --state gym8_inside.state --goal 45 --engage --bank badge8` is the first pass (running at
   the time of writing, log `badge8_gym.log`). The verdict is the BADGES byte: 0b01111111 -> 0b11111111.
2. If the engage loop cannot reach a body because of the spinner rows, hand-drive: press onto the spinner,
   read the landing, `walk` from there; pick up the ball at (16,9) (`rig.collect_item(16, 9)`) on the way.
3. The leader is one of the nine trainers; the badge byte says which fight was his. Bank `badge8_won`.

## Discipline

Drain text after battles. Kill by PID. One-off drivers are `scripts/probe_<name>.py`; commit as you go.
