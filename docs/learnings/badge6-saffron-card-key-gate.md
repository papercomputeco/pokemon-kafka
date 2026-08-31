# Badge 6 (Sabrina): cleared to Saffron, stopped at the CARD KEY

Session 2026-08-30/31, first legs driven by the real `scripts/supervisor.py run`. Badges
`0b00011111` throughout — no badge was won. What was won is the road, and two gates that are
now measured instead of assumed.

## Cleared, and banked

`BADGE5.state` (Fuchsia gym) → Fuchsia → Saffron → inside Silph Co, then Silph 1F → 2F → 3F →
the floor below the top. Batons under `data/local_runs/roster-bench/`: `b6-7`, `b6-10`, `b6`,
`b6_silph-234` (map 209), `b6_silph-178` (Saffron, at the gym door).

**The measured road Fuchsia → Saffron**, which is not the one `rt.route` reaches for first:

```
7 -> 26 -> 25 -> 24 -> 23 -> (gate house 87) -> 4 Lavender -> 19 Route 8 -> 10 Saffron
```

Two of those hops are gate buildings, not edges — `cross_edge` returns `no-path` and
`pass_gate` gets through: **23→4** and **19→10**. Two others are graph paths the world refuses
and the supervisor auto-bans:

- **29→28, Cycling Road.** Map 28 is 20x144 and every ledge extracted from this cartridge hops
  *down*, *left* or *right* — there is no upward ledge anywhere in the ROM. The connection
  table is undirected; the world is not.
- **30→31, Route 19.** Water. Needs Surf, which the engine does not have.

**Route 12 (map 23) is severed** into a south region (428 cells, y21–107) and a north region
(67 cells, y0–17). Gate house 87 is the only link: door **(10,21)** on the south side,
**(10,15)/(11,15)** on the north. Its corridor pinches to a single cell at **(10,63)** — grid
row 63 is walkable only at x=10 — and a trainer parked at **(10,62)** plugged it. Beating that
trainer opened the road. The trainer we kept bumping into at (14,76) was a bystander; column 15
walks straight around it. See `road.blocking_body`.

## Gate 1 — Sabrina's gym door (the reason no badge was won)

Saffron's gym is the warp at **(34,3) → 178**. The body at **(34,4)** alone severs that hop, and
what it says is the whole finding:

> **"Get out of the way!"**

Engaged three times; it does not battle, does not move, and does not vary. This is a script
gate, not a trainer. Full record: `docs/learnings/map10-to-178-stuck-20260831-012749-466a.md`.

## Gate 2 — the CARD KEY (what actually blocks gate 1)

Silph Co floors are maps **181, 207, 208, 209, 210, 211, 212, 213, 233, 234** (234 is 16x18,
the small top floor), all **tileset 22** — the facility set, where tiles decide where you end up
and a planned walk is a category error.

- **Silph 1F's pad at (16,10) → 208 is dead.** `rt.route` picks it because the graph has no
  opinion about which doors work. The floor's live ways up are **(26,0) → 207** and
  **(20,0) → 236**.
- On **map 209**, the warp at **(11,7) → 234** is refused, and the NPC at **(14,6)** says on
  screen that it **requires a CARD KEY**. That is read from the game, not recalled.

`b6_silph-234.state` is banked on 209 in front of that warp. An earlier run *reported* reaching
234; it had not. The read was torn across the warp window — `(234, 17, 11)` on a map sixteen
tiles wide — and `Rig.settled_pos()` exists now so that "arrived" can never again come from a
position the world has not finished writing.

## What the next run needs

1. **Find the CARD KEY.** It is somewhere in Silph's lower floors, which are already reachable
   and already tileset-22 territory — so `ORACLE_SEARCH` (facing-keyed, `0xC109` in the state
   key) is the mover, not `walk`. The supervisor offers it automatically on tileset 22.
2. **Top floor → Giovanni.** Expect the gym guard at (34,4) to stand down once Silph falls; that
   is the hypothesis this leg leaves behind, not a fact — verify it by walking back to (34,3).
3. **Then badges 7 and 8 are blocked on SURF**, which does not exist in `scripts/` in any form
   (only field-Cut, `road.cut_facing`). Cinnabar (map 8) connects only north→32 and east→31,
   both water. Surf and Strength come from the Safari Zone in Fuchsia. Build field-HM support in
   the engine, with tests, before planning either leg.

## Engine changes this leg paid for

Every one of these was a bug found by running, not by reading:

| what | why it mattered |
|---|---|
| `Rig.settle()` | a baton banked mid-dialogue swallows every step; `BADGE5.state` fingerprinted a wall that was not in the world |
| `probe_step` avoids warps | the settle probe stepped onto Fuchsia gym's mat and warped back inside |
| `rt.route(banned=)` + reroute | Cycling Road and the dead Silph pad, routed around instead of argued about |
| `road.blocking_body` / `gate_doors` | name the body that severs the map, not the one underfoot |
| `_clear_blocker` retires verdicts | Route 12 was banned as impassable on evidence gathered while the blocker still stood |
| per-seat tokens **and** timeouts | the Extractor was starved: 6,286 reasoning tokens and no answer at a 1,600 cap; raising tokens without the wait just changed the failure to "timed out" |
| `Rig.oracle_goto` restored | it did not survive the promotion out of the scratchpad, and tileset 22 is where it is the only mover |
| `settled_pos` | a torn read across a warp is not a place |
