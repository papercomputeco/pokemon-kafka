# Saffron/Silph: measured floor topology (2026-09-01)

All of the below is extracted from `rom/pokemon_red.gb` (rom_truth) or from surveyed runs in
`data/local_runs/roster-bench/` (survey-*.json, b6_*.log). Nothing here is recalled lore.

## Floor identity (from warp pairs, 0-indexed target-index resolution)

2F=207, 3F=208, 4F=209, 5F=210, 6F=211, 7F=212, 8F=213, 9F=233, 10F=234, 11F=235,
elevator car=236 (4x4, warps point at map 237), Silph entrance from city 181 at (16,10)→2F(27,3).
Saffron city = map 181 (30x18, strip in front of building) and map 10 (40x36, holds the gym
door: (34,3) -> 178; gate body at (34,4) @10, defeated to open). Sabrina's gym = 178 (20x18,
35 internal warps; battle room per prior run at (12,4)). Map 255 is a third-party target:
235 (5,5)->255#9, 178 (8,17)/(9,17)->255#2, 181 (10,17)/(11,17)->255#5. Map 25 = 20x54, no warps.

## 5F (210) — where the CARD KEY ball is

- Ball (21,16) confirmed CARD KEY by cartridge speech (b6_cardkey.log 2026-08-31).
- Static grid pockets: [209, 168, 29, 47, 33, ...]. Pocket 0 (209 cells) contains BOTH the
  row-1..5 upper region AND the ball L (col 28 rows 5-16 + row 16 cols 9-28); the ONLY seam
  between them is tile (28,4), where a trainer sits ("Show TEAM ROCKET a little respect!").
- 210 warp pads: (20,0)->car, (24,0)->6F, (26,0)->4F, (27,3)->7F, (9,15)->9F, (11,5)->3F, (3,15)->3F.
- survey-210 (start (8,15), 168 cells, complete): exits (20,1)up->car, (24,1)up->211, (26,1)up->209,
  (26,3)right->212, (27,2)down->212, (28,3)left->212 [three approaches to the (27,3) pad],
  (10,5)right->208, (11,4)down->208, (12,5)left->208, (8,15)right->233, (9,14)down->233.
  Doors (all CARD KEY): (8,13)L, (8,12)L, (8,5)L, (8,4)L, (16,10)L, (16,11)L.
- CONSEQUENCE: (28,3) and the (28,4) trainer ARE reachable in the measured (8,15) component
  (28,3,left exit was observed). The 9F->5F warp (17,15)@233 lands (9,15)@210 in this component.

## 7F (212)

- Pockets: p1 92 [(21,3),(18,1),(1,9),(1,5),(5,14)...], p3 50, p5 39, p6 28 [(21,15) pad],
  p0 29 [(5,7),(5,3) pads], p4 8, p2 14.
- survey-212 (start (21,3), 233 cells, complete): doors ALL CARD KEY: (21,3)down, (20,3)down,
  (11,5)down, (10,5)down — i.e. p1 is sealed from p3 and p5. Exits: (22,1)up->211, (18,1)up->236 (car),
  (16,1)up->213.
- The (21,15) pad (p6) pairs with 210 (27,3); p6 is behind CARD KEY doors from p1 => the 7F pad is
  NOT the entry to the card pocket. The entry is on 5F itself (above).
- Live bodies snapshot 2026-09-01 (stuck record): (1,5),(1,9),(2,15),(3,7),(7,10),(10,8),(13,2),(13,13),
  (19,14) [trainer AAAAAAA got 1400],(20,2),(24,11).

## 9F (233)

- survey-233 (start (13,16), 112 cells, complete): exits (14,1)up->234, (16,1)up->213, (18,1)up->236,
  (16,15)right->210, (17,14)down->210, (17,16)up->210. Doors all CARD KEY: (12,13)L,(12,12)L,(18,3)D,
  (19,3)D,(19,11)U,(18,11)U; plus stale battle text at (21,14)L,(21,15)L.

## 11F (235)

- 18x18, 324 grid cells, 52 walkable (pockets [128, 52]). Warps: (9,0)->234, (13,0)->car, (3,2)->212,
  (5,5)->255. Giovanni (7,5) kind "npc" (NOT trainer); president (10,5) "trainer"; trainer (15,9)
  [AAAAAAA got 750] already down (b6_lift.log: "engaged the trainer at (15, 9)").
- Lift tour (b6_lift.log): 11F lands (13,0)->(15,10), 52-cell pocket; Giovanni's pocket (128 cells)
  entered via 212 (5,7) -> 235 (3,2). 7F lands (18,1) -> banked (21,3). 5F lands (20,1). 10F lands (12,1)->(1,12).

## Failed attempts so far (both recorded)

- 210 (11,5) landing (via 208/3F): engaged 3 trainers (8,16),(8,3),(18,10); FAILED to reach (28,4)
  trainer, failed to open (21,16) ball (b6_cardkey.log).
- 212 (21,3): ORACLE/SWEEP no-path to (21,15), screen text "Darn! It needs a CARD KEY!" (stuck record
  map212-to-210-stuck-20260901-014455).

## Chosen route (to execute)

L1: b6lift-9F -> 233 (17,15) --warp--> 210 (9,15); walk (8,15)-component -> (28,3); engage (28,4)
    trainer; win -> walk (28,5)..(28,16) -> (21,16); open ball => CARD KEY. Bank b6_key.state.
L2: -> 233 (16,1) --warp--> 213 (16,0) -> 212 (16,0) [p1] -> (5,14) -> (5,7) --warp--> 235 (3,2)
    -> (7,5) Giovanni (npc battle, expect it to work like (15,9) did). Bank b6_giov.state.
L3: -> 235 (9,0) -> 234 (10,0) -> 209 (4F) -> 208 (3F) -> 207 (2F) (24,0) -> 181 (26,0) city strip
    -> map 10 city -> defeat (34,4) gate body -> (34,3) -> 178 (8,17) -> (12,4) Sabrina => 6th badge.
    Bank badge6.state.
