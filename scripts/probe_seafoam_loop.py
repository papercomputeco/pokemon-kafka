"""Seafoam west door -> east door along the Surf-aware stair loop, then the south shore -> Cinnabar.

A walk-only fill says "no route"; B3 (map 161) is crossed on water. The follower below plans on
land + 0x14 water with the tile-pair rules, and arms SURF whenever a step leaves land for water.
"""

import json
import sys
from collections import deque

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

HOPS = [  # (map, stair cell to step onto, map it leads to)
    (192, (7, 5), 159),
    (159, (13, 7), 160),
    (160, (5, 13), 161),
    (161, (25, 14), 160),
    (160, (25, 11), 159),
    (159, (23, 15), 192),
    (192, (26, 17), 31),
]
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/seafoam_west_door.state"
rig = Rig(STATE, settle_on_boot=True)
truth = json.load(open("references/rom_truth.json"))
pairs = rt.loaded_pairs(truth)
print("start", rig.pos(), "| surf:", rig.knows_move("SURF"), "str:", rig.knows_move("STRENGTH"), flush=True)


def M(mid):
    return truth["maps"][str(mid)]


def tid(m, x, y):
    return int(m["tiles"][y][2 * x : 2 * x + 2], 16)


def is_land(m, x, y):
    return m["grid"][y][x] == "1"


def is_water(m, x, y):
    return tid(m, x, y) == 0x14 and not is_land(m, x, y)


def plan(mid, start, goal):
    m = M(mid)
    w, h = m["width"], m["height"]
    solid = {(s["x"], s["y"]) for s in m["sprites"] if s.get("pic") == 63}
    prev = {start: None}
    q = deque([start])
    while q:
        x, y = q.popleft()
        if (x, y) == goal:
            path = []
            c = goal
            while c:
                path.append(c)
                c = prev[c]
            return path[::-1]
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in prev or (nx, ny) in solid:
                continue
            if not (is_land(m, nx, ny) or is_water(m, nx, ny)):
                continue
            if is_land(m, x, y) and is_land(m, nx, ny) and not rt.passable(m, pairs, x, y, nx, ny):
                continue
            prev[(nx, ny)] = (x, y)
            q.append((nx, ny))
    return None


def drain(limit=14):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


KEY = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}


def follow(mid, goal):
    """Step a planned path; re-plan after any displacement; arm SURF at each shore."""
    for _ in range(400):
        drain()
        mp, x, y = rig.pos()
        if mp != mid:
            return "map-change"
        if (x, y) == goal:
            return True
        path = plan(mid, (x, y), goal)
        if not path or len(path) < 2:
            return "no-path"
        nx, ny = path[1]
        m = M(mid)
        key = KEY[(nx - x, ny - y)]
        if is_land(m, x, y) and is_water(m, nx, ny):
            rig.io.press(key, hold=4, release=8)  # face the water first
            rig.ctl.wait(20)
            if not rig._arm_surf():
                print(f"   SURF refused at {(x, y)} facing {key}: {rig.textbox()!r}", flush=True)
                return "surf-refused"
            drain()
            if rig.pos()[1:] != (x, y):  # the arm animates us onto the water already
                continue
        rig.io.press(key, hold=8, release=8)
        rig.ctl.wait(30)
    return "cap"


start_i = next(i for i, (mp, _c, _n) in enumerate(HOPS) if mp == rig.pos()[0])
if rig.pos()[0] == 31:
    rig.io.press("up", hold=8, release=8)
    rig.ctl.wait(40)
    start_i = 0
for i in range(start_i, len(HOPS)):
    mp, cell, nxt = HOPS[i]
    if rig.pos()[0] != mp:
        print(f"hop {i}: expected map {mp}, at {rig.pos()}", flush=True)
        rig.bank(f"seafoam_loop_lost_{i}")
        sys.exit(2)
    r = follow(mp, cell)
    if rig.pos()[0] == mp and rig.pos()[1:] == cell:  # on the stair without firing it: step off and on
        for key in ("up", "down", "left", "right"):
            rig.io.press(key, hold=8, release=8)
            rig.ctl.wait(30)
            if rig.pos()[0] != mp:
                break
            follow(mp, cell)
    print(f"hop {i}: {mp} {cell} -> {nxt}: {r} now {rig.pos()}", flush=True)
    rig.screenshot(f"loop_{i}_{rig.pos()[0]}")
    if rig.pos()[0] != nxt:
        rig.bank(f"seafoam_loop_stuck_{i}")
        sys.exit(3)

print("east door exit:", rig.pos(), flush=True)
if rig.pos()[2] == 9:
    rig.io.press("down", hold=8, release=8)
    rig.ctl.wait(30)
    drain()
print("south shore:", rig.pos(), flush=True)
rig.bank("island_south")
r = follow(31, (0, 14))
print("to Cinnabar's edge:", r, rig.pos(), repr(rig.textbox()), flush=True)
if rig.pos()[0] == 31 and rig.pos()[1] == 0:
    rig.io.press("left", hold=8, release=8)
    rig.ctl.wait(40)
    drain()
rig.screenshot("cinnabar_arrival" if rig.pos()[0] != 31 else "stuck_west")
rig.bank("cinnabar_arrival" if rig.pos()[0] != 31 else "cinnabar_side_stuck")
print("*** CINNABAR ***" if rig.pos()[0] == 8 else "not there", rig.pos(), flush=True)
