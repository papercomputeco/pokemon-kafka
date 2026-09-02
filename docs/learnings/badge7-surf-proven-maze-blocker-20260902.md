# Badge 7 — SURF is PROVEN; the water/rock **maze** to map 31 is the remaining blocker

Date: 2026-09-02 (later pass)
Goal (operator): reach Blaine via SURF, win badge 7; then Viridian badge 8.
Status: **SURF works and is reliable within a single run.** The blocker is now precisely
characterized: the sea around map 30 is a solid **water/rock checkerboard maze**, the west
exit (map 31) is unreachable by any straight surf, and the **SURF-armed state does not persist
across state reloads** — so the single long surf needed to cross has to happen in one run, from
a clean menu state. The 09-02 crew hit the same wall with *more* turns; this pass adds the
definitive menu mechanics, a proven surf run, and the exact baton.

## What is now PROVEN (no longer a hypothesis)

1. **SURF is functional and Gyarados is the surfer.** Surfing succeeded multiple times:
   - `cross(7,30)` (Fuchsia → map 30) via the rig's surf machinery.
   - Surfing the water strip on map 30: **(14,10) → (13,10) → … → (1,10)** — a continuous
     13-tile surf run, westward, all on water.
   So "No SURFing on GYARADOS here!" is a **location** refusal (facing rock), not a Gyarados,
   level, move, or status issue. (The earlier "status byte 0x0F" and "Gyarados can't surf"
   theories are both disproven.)

2. **Water encounters are handled correctly** (the 09-01 blocker is solved in practice):
   a wild **Tentacool** (water) appeared mid-surf; the rig **switched the lead to Dugtrio
   (L100) and KO'd it with Scratch** (48 dmg). **Gyarados stayed in the party at 73 HP, never
   took the hit.** This is the "Gyarados stays out, a strong member wins" survival we want.
   It happened repeatedly across the surf strip without Gyarados dropping. So the party can
   now absorb water-gym-style encounters (weak water wilds) *and* keep its one surfer alive.

3. **The top-level overworld menu** (decoded from the window layer; items sit on even rows
   r2..r14, `ADDR_MENU_MAX`=7): POKéDEX · **POKéMON (idx 1)** · ITEM · [idx 3, cursor glyph] ·
   SAVE · OPTION · EXIT. SURF is **under POKéMON → Gyarados → field submenu**.

## The SURF arm mechanics (the part that was flaky, now understood)

- Arm with the **menu-reading** path `Rig.use_field_move("SURF", face=<dir>, species="Gyarados")`,
  **not** the blind-key `surf_facing`/`_arm_surf` — the blind path lands the menu cursor wrong
  and silently fails. `use_field_move` reads the window, finds Gyarados's row, then SURF, and
  only then confirms. This is what made the strip-surf work.
- **Once SURF is armed it STAYS armed through `b` (close-menu) presses and through *walk* turns
  (a "block" press at rock just refuses).** The D-pad then issues surf-attempts: water → you
  surf (move); rock → "No SURFing on GYARADOS here!" (no move). So you **cannot freely walk
  the island while SURF is armed** — disarm (B) to walk, then re-arm when you want to surf.
- Practical order for a surf step: `disarm (B) → walk to the shore tile → use_field_move(SURF,
  face=dir, species=Gyarados) → press dir → (battle?) → you are on the water.`

## Party state (the baton)

| mon       | lvl | hp    | role                              |
|-----------|-----|-------|-----------------------------------|
| **Gyarados** | 20  | **73**  | the **only surfer**; keep out of combat (lead) |
| Dugtrio   | 100 | 242   | tank that KO'd the water wilds     |
| Primeape  | 99  | 300   |                                    |
| Pidgeot   | 99  | 347   |                                    |
| Hypno     | 99  | 341   |                                    |
| Charizard | 100 | 341   |                                    |

Badges: **6**. Gyarados 73 HP is the one fragile item — it must keep surviving (switch-out,
done for us by the rig) so it stays the surfer. If Gyarados ever fainted, **SURF is lost** and
the badge-7 leg is over.

## The remaining blocker — precisely

Map 30 (20×54) is **island land (x4–13, y6–9) + a spine (x13, y0–5) surrounded by a rock/
water checkerboard sea**. Surfing proves which tiles are real water: the **y10 row is a
continuous water strip from x1 to x14** (surfed it). But it is a **dead-end pocket**: from
(1,10) west is rock (x=0, the map-31 boundary), and (1,9)/(1,11) are rock — so that strip
does **not** touch the west edge. The water *is* connected (the island is surrounded), so a
path to the west edge exists, but it requires surfing **far** (east around the island, over
x14–19, around, back up to x=0) — **many surf steps and several water encounters in a single
uninterrupted run**.

Two things combine to block the last crossing (map 30 → map 31 → map 8/Cinnabar → 166/Blaine):

1. **SURF state does not survive a state reload / bank/load.** Reload a state and the player is
   back on land and SURF is disarmed; re-arming is only reliable from a *clean* menu state. I
   could re-run one surf step, but not chain the many-step maze across reloads.
2. **The single run needed is long** (the full water-connection around the island to x=0) and
   each step risks a water encounter. It succeeds if done as one continuous scripted surf from a
   freshly-armed state.

## The baton and the exact next move

State: `data/local_runs/roster-bench/b8_aton_surf_proven.state` — **map 30 (1, 10)**, party as
above, Gyarados 73 HP, badges 6. (Other good saves in the same dir: `b8_baton_fuchsia.state`
(map 7, safe on land), `b8_mazewest.state` (map 30 island (6,9)).)

**Next session, do the crossing in ONE run:**
1. Boot `b8_aton_surf_proven.state`. It may be on land or water — read `settle_pos()`; if on the
   island, **disarm (B×6), walk to a water strip tile (e.g., (14,10))**; if already on water,
   continue.
2. In that same run, with `use_field_move("SURF", species="Gyarados")` to arm when needed,
   **BFS the connected water toward the west edge (x=0)**, preferring `left`/`up` (map 31 is
   west). Handle each encounter (the rig auto-switches + Dugtrio/Primeape KO weak water wilds;
   Gyarados stays at 73). Keep going until `settle_pos()` reports **map 31** (that is the
   crossing).
3. On map 31 (100-wide sea; land plaza ~cols 68–81 rows 3–13; warps (48,5)/(58,9)→192 AVOID):
   surf the land plaza, then surf **west** to the map-8 (Cinnabar) edge.
4. On map 8: walk to (18,3) → **map 166 (Blaine's gym)**. Badge 7.
5. Then route to Viridian (map 1) → Giovanni → **badge 8**.
6. Bank after each: `b8_on_31`, `b8_on_8`, `badge7.state`, `badge8.state`.

**If the single-run surf keeps hitting the SURF-reload wall:** the reliable alternative is to have
the rig's `road.surf_cross` do the multi-step surf (it was built for exactly this), with the now-
working surfer-encounter fix (`4c18f46`) and `knows_move` fix (`551646a`) already in. Try
`Rig.cross(30, 31)` from a state positioned on the island facing the water; it re-arms SURF on
each refused step.

## Ground rules honored

No ROM-structure reads, no RAM diffing beyond the rig's own helpers (`settle_pos`, `party`,
`dialogue`, `use_field_move`, `menu_rows`), no new engine code this pass — pure navigation with
SURF. SURF-ability decided by *attempting to surf* (the game's own refusal/acceptance), never by
a water-tile constant. `date` printed before summaries.

## Commits on the 09-02 pass (engine fixes, all green: 82 passed, ruff clean)

- `4c18f46` road.py: `surf_cross` no longer reads a fresh surfer water-encounter as a blocked
  step (surf advances on battle or a changed cell).
- `551646a` expedition_rig: `knows_move` matches by move id (learned moves decode to ids), not
  species name — so the surfer is found.
- `77d5376` expedition_rig: `surf_facing` drives the field submenu with `menu_cursor_to` (the
  blind up-wraps selected the wrong entry and broke battle menus).

## Open / out of scope this pass

- The actual map 30 → 31 → 8 → 166 crossing (the single-run surf maze) — the remaining badge-7 work.
- Cinnabar's water (surfing past Cinnabar to the next sea) and Viridian (badge 8) — badge-8 work,
  reachable only after the Cinnabar crossing is proven.
- A permanent fix so SURF state survives reloads (would make the maze trivially scriptable across
  runs) — engine work for a later pass; the "one-run surf" above is the workaround.
