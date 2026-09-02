# Blocker (measured 2026-09-02): the water crossings gate on *surfer survival*, and the surfer is L20

This is the single load-bearing fact behind "stuck on the way to Cinnabar/Viridian." Everything else
(menu stickiness, lead-swap, "No SURFing here") was either a red herring or a symptom of this one.

## What is actually true (measured, not recalled)

1. **Gyarados is the ONLY surfer in the party.** Read all six 44-byte party structs: only
   Gyarados (species 22) has move 0x2C(Surf). Dugtrio/Primeape/Pidgeot/Hypno/Charizard (all L99–100,
   full HP) cannot learn Surf (Fire/Normal/Psychic). In Gen 1 the *active* party member IS the one
   who SURFs, so during water travel the surfer takes every encounter and must be at lead.

2. **The water pool is mixed levels 5–40.** Maps 30/31/32/0 all draw from the same encounter table:
   Tentacool/Shellder at L5,10,15,5,10,15,20,30,35,40. ~70% are ≤L20 (a L20 Gyarados can usually win),
   ~30% are L30+/L40 (a L20 Gyarados LOSES).

3. **MEASURED failure (the decisive one).** From a clean healthy baton, the *first* west step into
   water on map 30 rolled a **Lv30 Tentacool (68 HP)**. Gyarados L20 (73 HP) used Surf for **9 dmg**
   (water resisted) and took 8–11/round → **fainted at round 7–8**. The party switched Dugtrio L100,
   KO'd the Tentacool and a Lv30 Shellder — the team WINS the battle — but Gyarados is now at 0 HP.

4. **Gen 1 consequence (measured): a fainted member is omitted from the POKéMON menu.** The moment
   Gyarados fainted, the rig reported *"Gyarados is not on the POKeMON menu (fainted members are not
   listed)"* and SURF was permanently gone. `cross()` then returned `stuck-on-edge` three times.
   **The five full-HP mons cannot save the crossing — only a LIVE surfer can SURF.**

## Why the earlier confusion happened

- "No SURFing on GYARADOS here!" while standing *on land* (the central plaza) is EXPECTED — you must
  be facing the actual water (x0–3 on map 30's west edge). The player at (6,6) was on the walkable
  plateau, not deep water (map 30 = a 20×54 water route with a ~5–8% central land strip, water both sides).
- The lead_swap failures were menu navigation noise on a contamina**ted** baton; the *real* death was
  the surfer fainting in a water encounter and dropping out of the party list.
- "stuck-on-edge" after `cross()` = surf_cross stepped into a solid/invalid cell — a *symptom*.

## The critical path (what actually unlocks badges 7 & 8)

- Cinnabar (map 166) is reachable ONLY via water: `30 → 31 → 8`. No land route (graph-verified).
- Viridian (map 45) is reachable ONLY via water: `8 → 32 → 0 → 12 → 1`. No land route.
- **Every one of those water hops can roll a L30–40 foe that KO's a L20 Gyarados and ends the surfer.**
  So the crossings are ~0.7-per-encounter coin flips, and a multi-hop route to Viridian is near-impossible
  with a L20 surfer.

**Therefore: the surfer must survive the water encounters first.** Concretely:
- Primary: **level Gyarados to ~L28–32** so its Surf outscales the L30–40 water foes (currently it
  deals ~9 dmg at L20, needs ~15–20). In Gen 1 the whole party splits exp (slow), so Gyarados must
  fight as the active attacker for meaningful exp; keep it alive (switch out if it would faint; the
  five L99–100 mons win the battle).
- Alternative / hedge: verify at each water approach that Gyarados is alive and its HP high; heal; if
  it ever faints mid-crossing, the route is over for that attempt — reload a healthy baton.

## Safe zones (no water) for grinding/positioning near the crossing
- Map 7 (Fuchsia, 40×36, no wilds, has a healer) — reachable by LAND from map 30 (south↔30, west↔29, east↔26).
- Map 26 (grass_rate 15, no water), Map 29 (grass_rate 25, no water), both off map 7 — land reachable.
- Map 30 north → map 7: **walkable land crossing, no SURF needed** (the plaza strip is on the walk side).

## Poisoned batons (do NOT settle_on_boot=True on these — auto-fight kills the surfer on boot)
- `b7_surfing.state`: Gyarados already fainted, on water (6,4/6,6). All dirs refused.
- Any baton saved *after* a water encounter in which Gyarados took KO damage.
- Good clean batons: `b7_badge.state` (map 30 (6,2) Gyarados 73/73), and the freshly banked
  `b7_badge_clean.state`.

## Definition of done for the "stuck" sub-goal
Gyarados (the only surfer) at a level where it reliably survives a Lv30–40 Tentacool/Shellder, healed,
then: `30→31→8` (bank at map 8) → Cinnabar gym 166 (badge 7) → `8→32→0→12→1` → Viridian gym 45 (badge 8).

---

## Progress + the one open question that decides the strategy (added 2026-09-02, late)

**What is now implemented, measured, and tested (not just reasoned about):**

- **A `protect` rule in `BattleStrategy.choose_action`** (`scripts/agent.py`, 7 unit tests in
  `tests/test_agent.py`, full 399-test suite green, ruff clean): *whenever a strictly stronger healthy
  mon (gap ≥ 10 levels) exists, hand the fight to it — switch to the strongest healthy backup before
  the weak lead takes a hit.* It fires at full HP (not just in the red) and in **both wild and
  trainer (gym) fights**, because the surfer is the opening active in both. A lone strong lead (no
  gap ≥ 10 backup) still fights and levels. Never in `force_fight` (data-collection) mode.
  This directly implements "the surfer must survive": the L20 Gyarados stays out of combat and the
  five L99–100 mons (who one-shot L30–40 water foes, measured: Dugtrio did 62 to a L30 Shellder) win
  the battle so SURF survives for the next water leg AND the gyms that come after each crossing.

- **MEASURED (not recalled): in Gen 1 the party lead does NOT change on a mid-battle switch.** Sent
  Dugtrio (slot 1) in on turn 1 of a Swimmer fight, won it, and the party order was *unchanged*
  (Gyarados still lead at index 0, Dugtrio still index 1). So the weak surfer (whichever mon is at
  member 0) is *always* the opening active and always takes the first hit. There is no way to make the
  strong mon the permanent lead; the *only* protection is switching the weak lead out **early in each
  battle** — exactly what the `protect` rule now does.

- **MEASURED: early switching fully protects the surfer.** In the Swimmer fight above, Gyarados ended
  the battle at **73/73** (zero damage) because it was switched out before the enemy's first hit, and
  Dugtrio won. This is the live proof the `protect` mechanism works — the same battle-menu path
  (`_select_battle_menu("pkmn")` → `navigate_menu` → confirm) the rule routes its `switch` through.

**The one open question that decides whether `protect` is safe in *water* fights (must measure before
relying on it to cross):**

- The `protect` rule works by switching the Gyarados (the SURF user) to a strong mon (Dugtrio etc.)
  mid-encounter. That is proven safe in **land** fights (the Swimmer test: character returned cleanly to
  the overworld). But during a **water** encounter the character is in the SURF state when the fight
  starts. The question: **after the surfer is switched to a non-Surf mon and the battle ends, does the
  SURF/water-travel state persist, or does the active non-Surf mon strand in the water?** In Gen 1 SURF
  is a player *state* (measured earlier: "the surfing flag is a dead end … the crossing is not a straight
  run", and "SURF is armed and the water is not a tile id"), which *suggests* it persists independent of
  the active mon — but that specific interaction (switch-surfer-out-mid-water-fight → still able to
  water-travel) has **not** been measured. If it does NOT persist, `protect`-switching in a water fight
  would strand the party in water (worse than burning the surfer), and the fallback is the original
  "level the Gyarados up" plan (Strategy A) so the surfer itself wins the water fight.
  → **Next step: run one water encounter from a healthy baton, let `protect` switch the surfer out,
  win, and confirm the character can still walk on water. Only then is `protect` cleared for the crossing.**

**Poisoned batons** and **safe batons** are as listed above; the freshly banked `b8_strong_lead.state`
(map 30, (6,7), Gyarados 73/73, the (8,7) Swimmer already defeated) is a good clean starting point.
