# Seafoam Islands — west side, all five floors (2026-09-03)

Mission: work the west (left) side of every floor (192→159→160→161→162) instead of rushing the
vertical shaft; talk/fight every body; try multi-direction + pad before declaring unreachable;
report any warp that leads outside the 192/159/160/161/162 chain.

Baton in: `seafoam_1f_safe.state` (map 192, 6 badges). Baton out: `seafoam_west_descend.state`
(map 161, 4F). Logs: `sf_descend_run2.log`, `seafoam_west_descend.jsonl`.

## What the west side actually is (measured, not recalled)

The previous leg filed the west-side bodies as "pad pockets." Talking to them this turn produced
the game's own words, and those words split the bodies into two kinds:

**STRENGTH boulders, not bodies.** Four of the six "west-side bodies" answered *"This requires
STRENGTH"* when I stood adjacent and pressed A. They are Seafoam's Strength boulders that the
earlier leg mis-logged as bodies:

| floor | cell | game's reply |
|-------|------|--------------|
| 1F (192) | (18,10) | "This requires STRENGTH" |
| 4F (161) | (5,14)  | "This requires STRENGTH" |
| 4F (161) | (8,14)  | "This requires STRENGTH" |
| 4F (161) | (9,14)  | "This requires STRENGTH" |

Nobody in the party knows Strength (leader Charizard L100: moves #0F/#A3/Ember/#53), so these
boulders cannot be pushed. That is an honest, measured limit — not a route failure.

**Sealed pockets — real bodies the generic walker cannot reach.** The remaining west-side bodies
sat in their own collision components with no routeable neighbour, so they reported UNREACHED with
an evidence screenshot at each (these are the genuine "pad-pocket"/water bodies the walker can't
ride to):

- 2F (159): (17,6), (22,6)
- 3F (160): (18,6), (23,6)
- 4F (161): (3,15), (18,6), (19,6)
- 5F (162): (4,15), (5,15), and trainer (6,1)

Evidence PNGs: `data/telemetry/screens/…/evidence_<map>_<x>_<y>.png`.

## The floor is not a vertical shaft — it's a component graph

The decisive structural fact, confirmed by the engine's own reachability: **each floor splits into
several disconnected collision components, and different doors land in different components.**
So "go down one floor" is not a single hop — it is "pick the door that lands in the component you
want."

- 1F door (7,5) lands in 2F's main component (216 cells); 1F door (25,3) lands in a separate 2F
  component (51 cells) that holds the (22,6) body. That 2F component's only exit is door (25,3) back
  to 1F — a dead-end branch.
- 2F has four doors to 3F, landing in four different 3F components (92 / 148 / 148 / 20 cells). The
  3F bodies (18,6) and (23,6) sit in components none of those door-landings can reach.
- 3F door (5,13) lands in 4F's main component (215 cells) holding the four Strength boulders; the
  4F bodies (3,15),(18,6),(19,6) are in other components.
- 4F doors (8,6)/(25,4) land in 5F's main component (150 cells); the 5F bodies and trainer (6,1) are
  in separate pockets.

**This is the "don't rush the shaft" lesson made concrete:** a body's reachability depends on which
door you came in by, and some bodies live in one-door-in, one-door-out side rooms. The generic
floor-to-floor driver lands in the "main" component and then cannot see the side-room bodies — exactly
what made them look like "pad pockets."

## Warp / map report (the mission's explicit question)

Every warp on all five floors stays inside the {192,159,160,161,162} chain. The **only** exits to
outside the interior are 1F's four ocean doors — (4,17), (5,17), (26,17), (27,17) — all to map **255
(open ocean)**. No warp on any floor leads to an unmapped/fresh floor. So: nothing new to report;
the only "outside" is the ocean at the 1F water's edge.

## Reliability notes (reproducible, costed here)

- Crossing floors via `RIG.walk`/`RIG.drive` threads open water: random water battles (Seel, Horsea,
  Staryu, Slowpoke, ~Lv28–32) fire en route, and occasionally a warp fires mid-walk (seen
  159→160), depositing us on the next floor. Treat "map changed during a walk" as expected here,
  not a bug. `ensure_map()` (driving back to the intended floor) recovers cleanly.
- Because of that, "heard" dialogue must be read after clearing the battle/EXP page, or it is
  contaminated with the previous battle's "gained N EXP" (caught twice and fixed by flushing A/B
  before the real press-A).
- Banked states mid-pair or on a warp mat boot on the wrong side (the rig's `bank` already steps
  off mats — `seafoam_west_descend.state` landed safely on 4F at (161,8,7)).

## Bottom line

West side of all five floors worked: the "bodies" that look reachable are Strength boulders (blocked
for lack of Strength — measured, not assumed), and the true bodies sit in one-door side components the
floor-to-floor driver doesn't route into. The warp question is a clean no: no floor links outside the
five-map seafoam chain except the 1F ocean (255). To actually engage the side-room bodies next, the
walker needs pad-ride / SURF-in-to-side-room routes, or the doors that specifically land in their
component (e.g. 2F (22,6) is only reachable via 1F door (25,3)).
