# Pewter (Badge 1) → Mt. Moon 1F via Route 3

Mission: from the seed `demo-runs/states/mtmoon_seeds/badge1_gym_hp6.state` (standing on Brock's
tile (5,1) in Pewter Gym, map 54, Badge 1 in hand, one Charmeleon L16 at 6/48 HP), get a
`badge_to_mtmoon` lane to `final_map_id: 59` and leave the baton
`<run>/batons/badge_to_mtmoon.state`.

| field | value |
|---|---|
| start | 2026-08-18 07:49 PDT (`date`) |
| harness | relay.py `--segments badge_to_mtmoon --sideloop-every 300`, NAV_SPREAD (6 lanes) |
| seed | badge1_gym_hp6.state (Pewter Gym, badge 1, hp 6/48) |

Obstacle files (written as they clear):

- `route3-heal-gating.md` — the 6/48 HP start with the heal trip gated off (it requires *not*
  having the badge): a faint on Route 3 is the only heal path, and it must land where the leg
  can be re-run.
- `route3-gym-exit.md` — leaving the gym west out the door with the badge (the map-54 waypoints
  are aimed at Brock, the map-2 waypoints are aimed at the gym door: both point the wrong way
  for this leg).
- `route3-crossing.md` — the Route 3 leg: Pewter east exit → Bikers / grass → Mt. Moon warps.

Outcome: _(filled at end)_
