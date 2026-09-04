# Walking toward Pallet from the baton — run `talk01` (2026-09-03)

**Baton:** `data/local_runs/roster-bench/v8m10-15.state` (all v8m10 batons sit at `(15, 89, 11)`)
**Final bank:** `data/local_runs/roster-bench/talk01-final.state` at **map 15 `(88, 10)`** — the baton pocket.
**Logs:** `runs/talk01-run{1..6}.log` · **Screens:** `data/telemetry/screens/talk01/` · **Driver:** `scripts/walk_toward_pallet.py`

## The three questions, answered

### 1. Pallet — unreachable from this side of the world. Measured, not assumed.

The player boots in **map 15 pocket P2** (a 115-cell pocket whose *only* connection is its east
edge to map 3). Map 3 pocket P0 (378 cells, 9 bodies, 7 door pads) has exactly two overworld
exits, both measured open: **north → 35** and **west → 15**. Everything else in the 226-map world
hangs off seams that are in *other pockets* of maps 3/15 (or behind them):

| road to Pallet | first seam | seam cells | which pocket holds it | verdict |
|---|---|---|---|---|
| 15 → 14 → 2 → 13 → 1 → 12 → 0 | 15 south | x6-11, x66-67 | **15 P1/P2/P3** — not P2 (the baton pocket, x86-89/east) | REFUSED ×8 across runs |
| 3 → 16 → 10 → 17 → 5 → 22 → 85 → 197 → 46 → 13 → 1 → 12 → 0 | 3 south | x0-9, x11-14, x16-23, x25-28, x30-39 | **3 P1/P2/P3/P5** — not P0 | REFUSED ×4 |
| 3 → 20 → 21 → 4 → … | 3 east | y16, y17 | **3 P1/P3** — not P0 | REFUSED ×4 |

Pallet (0) and map 14 sit in the **A-cluster** ({0,1,2,4,5,8,10,12,13,14,16,17,…}, ~220 maps).
The baton sits in the **B-cluster** ({15-P2, 3-P0, 35, 36, 88, 62..67, 230}). The two clusters are
linked *only* by the three seam rows above, and every one of those rows is cut off from the baton
pocket by a single solid wall cell with **no ledge, no gate, no bike** (audited: the 8 world ledge
triples never cross the P0 boundary; `walkable()` from `(3, 0, 18)` reaches 362 cells — all of P0,
none of the seam cells; no CARD KEY / LIFT KEY gates exist outside the Silph maps 207-213/233; the
bag holds S.S.TICKET/LIFT KEY/CARD KEY but **no BIKE** and no SURF HM).

This is the second independent measurement of the same sealing: all sixteen `v8m10-*` batons are
banked on map 15 `(89,11)` — the previous campaign never escaped the pocket either.

### 2. What actually blocked movement (screenshots are the witness)

Refusal screenshots (each: the game on screen at the moment the step was refused; the player
position is recorded in the telemetry `refusal` event next to each file):

- `refused-to-pallet-15-14-1.png`, `-2.png` — the baton pocket's south wall (run 6, map 15 → 14)
- `refused-to-pallet-3-16-1.png`, `-2.png` — map 3's south seam x0-14 side (run 6)
- `refused-to-pallet-3-20-1.png`, `-2.png` — map 3's east seam (run 6)
- earlier runs: `refused-to-pallet-15-14-{1..4}.png` (runs 1-4), plus the `no-route-*` screens

On every refusal the engine walked to the seam cell, pressed the d-pad, and the player **stayed on
the original map** (`cross` → `no-path`; positions logged, e.g. still at `(15, 88, 10)`, `(3, 1, 18)`,
`(3, 20, 0)`). The collision grid shows the cause directly: map 3 is one map of **10 disconnected
open-cell pockets**; the baton's pocket (378 cells) does not touch any south/east edge cell. Same
for map 15 (5 pockets). The wall is not a door, a gate, or a story flag — it is terrain the engine
refuses to walk across, repeatedly, with the screen open.

Doors that also *do not open* from this side (measured, "door did not open" in every run):
`(27,9)`→62 (pocket P1 side of map 3), `(11,5)`→68 and `(18,5)`→59 on map 15 (pocket P1),
`(4,11)`→228 (pocket P6). The LAST_MAP mats inside every room return only to the map you entered
from, so no room bridges the two clusters.

### 3. Is the water route south of Pallet ("Route 21", map 32) open?

**It cannot be approached from the baton side** — that is the honest answer, and it is structural:
map 32 (20×90, nine surfer trainers) borders **only 0 (Pallet) and 8**, both A-cluster. The earlier
measured leg ("Pallet → 32") found map 32's north edge lists **no walkable cell** — the entry from
Pallet is a water crossing; the bag holds no SURF. From the baton pocket the route is unreachable in
principle (same three sealed seams as §1), so its open/sealed status was never — and cannot here — be
judged by a step.

## What every body that could be reached said (verbatim tails, run 6)

Reached and engaged — 11 maps, ~40 engagements (battles included):

**Map 3 (the hub, P0):**
- (27,12) "…I'll keep it at home, so it won't get dirty!" — the one who wants "a bright red BICYCLE!" (9,27)
- (9,21) / (15,18) "There might be a way around. / That bush in front of the shop is in the way."
- (28,12) "The people here were robbed. It's obvious that TEAM ROCKET is —"
- (29,26) / (28,26) the two SLOWBRO brothers: "SLOWBRO punch! No! You blew it again!" / "SLOWBRO is loafing around…"
- (31,20) "Youe a trainer too? Collecting, fighting, it's a tough life." (defeated)
- 62 (bike shop, through pad (27,11)): (2,1)…(5,6) "I figure what's lost is lost! I decided to teach DIGLETT how to DIG without a TM!"

**Map 35 (7 trainers, all "I did my best… no regrets!" except):**
- (5,20) "AAAAAAA got 280 for winning!" (defeated)

**Map 36 (dead-end 60-cell route, 9 trainers):**
- (14,2) "All POKéMON have weaknesses. It's best to raise different kinds."
- (18,5) "On S.S.ANNE, I saw trainers from around the world."
- (24,4) "Oh well. My girl will cheer me up." · (18,8) "I wish my guy was as good as you!"
- (32,3) "I knew I had to fight you!" — five 99-lv POKéMON, defeated
- (37,4) "You came from MT. MOON? May I have a CLEFAIRY?"
- (8,4) "Drat! A ZUBAT bit me back in there." · (23,9) "The collector has many rare kinds of POKéMON."
- (13,7) "Youe going to see BILL? First, let's fight!" (defeated)

**Map 88 (room off 36):** (4,4) defeated ("AAAAAAA got 595 for winning!")

**Map 63:** (1,2) "Hello there! Do you want to trade your POLIWHEEL for JYNX?" — declined ("Well, if you don't want to…")

**Map 64 (Cable Club):** (4,3) "Have you heard about BILL? Everyone calls him a POKéMANIAC!" · (11,2) "Welcome to the Cable Club! This area is reserved for 2…"

**Map 65 (MISTY's gym):** (2,3) "You have to face other trainers to find out how good you really are." · (8,7) "MISTY is going to keep improving! She won't lose to someone like you!" · (7,10) "You beat MISTY! What'd I tell ya? You and me kid, we make a pretty [good team]."

**Map 66 (bike shop):** (5,6) "A plain city BIKE is good enough for me! You can't put…" · (1,3) "These BIKEs are cool, but theye way expensive!" · (6,2) "Have you seen any RARE CANDY? It's supposed to make POKéMON go [up in level]"

**Map 67:** (3,4) "…cool, but theye way expensive!" (bike-talk continues)

**Map 230 (Cable Club, pad (9,11)):** reached; its trainer (5,3) refused from the mat landing (pocket split)

**Bag on pickup attempts:** "No more room for items!" (35 (10,5), 36 (22,2)) — the bag is full of TMs/HMs/fossils from the v8 campaign.

Bodies listed by the cartridge but **unreachable from the baton pocket** (each in a sealed pocket;
their pads, if any, do not open from our side): map 3 (30,8) & (4,12); map 15 (9,8) — the mission's
named body — and (63,3); map 63 (5,4); map 64 (3,1); map 65 (4,2); map 66 (6,2); map 88 (6,5);
map 230 (5,3). The (9,8) body's own pocket holds the league pads → 59/68 and the 15→14 seam x6-11:
every door out of that pocket is also sealed, measured four-plus ways.

## Bugs found and fixed while walking

1. **Body-tile trap:** an engagement can leave the player standing on a body's tile; every walk then
   reads no-path. Fixed: `Mission.off_body()`.
2. **Seam-bounce oscillation (run 5):** `cross` lands the feet on the seam row and the engine's own
   settle/probe step walked straight back across (log: `crossed 3 -> 35`, next line at `3 (21,0)`) —
   to_map then re-crossed in a loop, re-engaging the hub nine times a pass. Fixed:
   `Mission.pull_away()` steps off the boundary after every successful cross.
3. **Stale door-pad lines:** `door_pads()` parsed the *last* "not walkable" line ever seen, so map
   15's pads (→59/68) were attempted while standing on map 3. Harmless ("door did not open") but
   slow; the line should be tagged with the map it was heard on.
4. `Rig.walk` takes `(map_id, [(x, y)], cap=…)` — not `(x, y)`. Cost one crash + one bank.

## If someone finishes this road

From the baton side, nothing to find: the pocket is a closed component
{15-P2, 3-P0, 35, 36, 88, 62..67, 230} and the road to Pallet is on the other side of three
sealed wall cells. A baton banked anywhere in the A-cluster (e.g. map 14, 20, or 4) would put the
whole road — including map 32's water entry — within reach. The two clusters are different worlds
from this side of the wall.
