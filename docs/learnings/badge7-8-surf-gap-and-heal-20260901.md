obstacle: badge7-8 — Cinnabar (Blaine) / Viridian (Giovanni) from the Safari Zone Secret House; the baton left here because routes 19/20/22 are water and the engine cannot surf.
symptom:  State 0b00111111 at map 222 (Safari Zone Secret House, 232,0,2); the only SURF user (Gyarados, member 0) is at 0 HP — it blocks `use_field_move` (fainted lead) and cannot be sent to surf until healed. The land path to the Fuchsia Center is trivial, but every path to Cinnabar and Viridian crosses a 5–8%-walkable water route (the A* engine treats water tiles as walls, so `road.walk` / `road.cross_edge` refuse them and report no-path / stuck-on-edge).
category: navigation | surf | bag | battle
failed:    - variant: heal-only (no surf fix)
  failure: Fine on the land leg, but Cinnabar (map 8) connects only via 31 and 32 and Viridian (map 1) only via the 12→1 edge off route 0/12 — all downstream of a water crossing, so it cannot reach the gym without surf.
  variant: recalled "surf across the routes"
  failure: The routes are NOT pure water. Measured from `references/rom_truth.json`, each has a walkable land *plaza* in its middle (map 31: 100 walkable cells at x≈40–49 across ~18 rows; map 30: a 51-cell land component from its north edge) but water on both edges (map 30's plaza does not reach its west edge; map 31's plaza does not reach its x=0 edge). So the crossing is mixed: walk the plaza, SURF the water, and the road engine must support *both* within one map — a plain land-A* over-calls walls, a plain "all water" assumption under-calls.
winner:    Heal leg shipped and banked (2026-09-01, this change). (1) `expedition_rig.Rig.battle` gained a no-FIGHT special-menu fallback: after a special menu (e.g. the Safari's BAIT/ROCK/BALL/RUN) has been offered for SPECIAL_MENU_GRACE=5 turns without a FIGHT ever being drawn and the routine still cannot select from it, a wild is fled (RUN is bottom-right of every 2x2 battle menu; `_flee_special_menu` normalises the cursor, presses bottom-right, confirms, dismisses the "you run" text). A gym leader always draws a FIGHT, so `_fightable()` never lets this fire on a trainer, and a trainer cannot be fled anyway — the fix is scoped to undriveable wilds. (2) Surf gap analysed from ROM truth (see `why it worked`). The heal leg then ran 222→219→(reroute 218)→220→156→7→154, fought the one on-path battle normally (a Lv26 Chansey — it *has* a FIGHT, so `_fightable()` correctly kept it on the fight path), and healed Gyarados 0→73 HP. `b7_healed.state` banked at (154,3,3), badges still 0b00111111.
why it worked:  The wedge on 218→220 the previous session was *not* a bag issue and *not* a land issue — it was a battle the fight routine could not select from, which spun to the 200-turn cap. `Rig.battle` only knew one way to end a fight (the agent's own turn, which anchors on a FIGHT tile); a special menu has none. The fix adds a second, orthogonal escape that only ever fires when the menu has no FIGHT *and* the wild is fleeable, so it cannot touch a trainer fight. Measured (not recalled) from the collision grids: map 30 (Route 19, 20x54) is 63/1080 walkable; map 31 (Route 20, 100x18) 100/1800; map 32 (Route 22, 20x90) ~8%; both 30 and 31 have land mid-points that do not connect edge-to-edge, which is why a pure `road.walk` fails on them yet a pure "it's all water" model would also be wrong. There is NO land-only path: `route 7 8` = 7→30→31→8 and `route 8 1` = 8→32→0→12→1, every map id on the way after Cinnabar is ≥61% walkable *except* the two route hops the engine cannot currently drive. Bag is 20/20 (HM SURF present, so the mon is teachable) but no item is needed on the way, so no tossing.
generalizes:  When a battle the routine can win does not in the time it should, the usual cause is a *menu it cannot select from* (a screen, not a move) — detect "the option it anchors on is not drawn" as the wedge signature, not "no progress", because a slow-but-drivable menu and a special one are different beasts and only the second is safe to flee. And a "water route" is a land-PLAZA plus water edges, not a lake: the A* passability predicate has to be *contextual* (water is surfable iff the mon can SURF AND is currently in/wanting the water), not a static tile class.
artifacts:   data/local_runs/roster-bench/b7_healed.state (Gyarados L20 hp73, at 154), data/local_runs/roster-bench/b7heal2.log, scripts/expedition_rig.py (SPECIAL_MENU_GRACE, `_fightable`, `_flee_special_menu`), references/rom_truth.json (maps 30/31/32 grids)

## discovered on the badge-7 leg, 2026-09-01 (baton b7_badge.state @ map 30, x=6 y=2)

What the `surf_cross` mechanism itself proved: the crossing logic is sound. From the healed
baton (Fuchsia, 154), the leg ran 154 → 7 → **30** — SURF arming-on-refusal fired and the run
crossed into map 30 (the first water segment). The re-arm on the **next** segment, 30→31, then
reported `no field move called 'SURF' on party member 0` and the ladder exhausted the edge.
That is NOT a routing bug and NOT a scroll-offset bug (verified the offset is 0); it is the
following wall, measured off the baton, not recalled:

- The POKeMON menu on this baton has exactly **four** awake entries — PRIMEAPE, PIDGEOT, HYPNO,
  CHARIZARD — and wraps. GYARADOS and DUGTRIO are **fainted**; Gen 1 omits fainted party
  members from the menu, so they are unreachable for a field move. None of the four awake mons
  can SURF. The only surfer in the party is the one that is down.
- `rig.party()` still decodes six rows (Gyarados L20, Dugtrio L100, Primeape, Pidgeot, Hypno,
  Charizard); two of them are HP-0 in the live game. So "healed Gyarados 0→73" was its *stat*
  after the last Center — it fainted again on the 7→30 crossing, because it is the **lead
  (member 0)** and the lead auto-fights the surf-encounter wild, and a L20 Gyarados loses to it
  while a L99–100 backup clears the fight and leaves Gyarados fainted.
- A false positive I almost trusted: the surf scan does report a "SURF" under `window_row` for
  the member it lands on, but that read is a **decoded cursor glyph merged into the text**
  (`AAAAAAAASURF` — the highlight tile bleeding into the string). `field_moves()` / `window_row`
  must mask the cursor glyph before a field-move name is matched, or the "found SURF" signal is
  unreliable. (It masked the symptom: the re-arm was failing on *who* is selected, not on the
  move text.)

The wall, general: the party's SURF user and its auto-battle lead are the **same weak mon**, and
it cannot do both — it must be awake to surf but it faints the moment it leads the very battle
the surf triggers. Surfing the routes is not blocked by navigation; it is blocked by this single
party. The unlock is to **separate the two roles**: lead a strong mon (any of Primeape / Pidgeot /
Hypno / Charizard, all L99–100 and awake) into the crossing battles so the surfer is never
auto-sent and can stay awake, then arm SURF on the (now-awake) Gyarados in a non-lead slot —
which is also a party-order change, and in Gen 1 that is done by RAM surgery on the snapshot
(validated) or by a battle policy that re-leads a strong mon before each fight. Whichever way it
is done, `use_field_move`'s member walk should also stop trusting the (artifact) "SURF" match and
confirm the selected member by party index/name, and `battle` should prefer a live, high-HP lead
over the party's first slot.
