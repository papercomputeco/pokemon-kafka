"""Ride B3's conveyor to B4 (map 162), navigate its water to the platform at (6,1), and READ what stands there.

The conveyor drops the surfer at 162 (20,15) in the east water body (x16-27). The sprite at (6,1) sits on a
19-cell land platform (x5-10, y0-2) reached from the west water body (x2-13) via the 0x15 shore at (7,3). The two
water bodies join only through land, so the route is: east water -> a shore -> central land -> west water -> (7,3)
-> platform. Every position is logged; the sprite is read by facing it (talk) and screenshotting.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/seafoam_loop_stuck_3.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def tile(mp, x, y):
    t = TRUTH["maps"][str(mp)]["tiles"]
    return int(t[y][2 * x : 2 * x + 2], 16)


def enterable(mp, x, y):
    m = TRUTH["maps"][str(mp)]
    if not (0 <= x < m["width"] and 0 <= y < m["height"]):
        return False
    return m["grid"][y][x] == "1" or tile(mp, x, y) in (0x14, 0x15)


def bfs(mp, start, goals, blocked):
    from collections import deque

    goals = set(goals)
    prev = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        if c in goals:
            path = [c]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])
            return path[::-1]
        x, y = c
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in prev or n in blocked:
                continue
            if enterable(mp, *n):
                prev[n] = c
                q.append(n)
    return None


def journal(content):
    append_observations(
        "pokedex/memory",
        [
            {
                "referenced_time": datetime.now(timezone.utc).isoformat(),
                "priority": "important",
                "source_session": "extractor",
                "content": content,
            }
        ],
        dedupe=True,
    )


def drain(limit=12):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def navigate(mp, goals, cap=400):
    """Step toward the nearest goal on this map. Arm surf when entering water; block a truly refused step."""
    goals = set(goals)
    blocked = set()
    stuck = 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp:
            return ("left-map", (m, x, y))
        if (x, y) in goals:
            return ("reached", (m, x, y))
        path = bfs(mp, (x, y), goals, blocked)
        if not path or len(path) < 2:
            return ("no-path", (m, x, y))
        nx, ny = path[1]
        entering_water = tile(mp, nx, ny) == 0x14 and tile(mp, x, y) != 0x14
        if entering_water:
            rig.io.press(K[(nx - x, ny - y)], hold=4, release=8)
            rig.ctl.wait(12)
            rig._arm_surf()
            drain()
        rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
        rig.ctl.wait(24)
        drain()
        m2, x2, y2 = rig.pos()
        if m2 != mp:
            return ("left-map", (m2, x2, y2))
        if (x2, y2) == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
            if (x2, y2) != (nx, ny):
                print(f"  drift: aimed {(nx, ny)} landed {(x2, y2)}", flush=True)
    return ("cap", rig.pos())


print("start", rig.pos(), "party", rig.party(), flush=True)
drain()
# STRENGTH ready check
try:
    used = rig.use_field_move("STRENGTH", species="Gyarados")
    print("STRENGTH ready:", used, rig.textbox(), flush=True)
    drain()
except Exception as e:
    print("STRENGTH check raised:", e, flush=True)

if rig.pos()[0] == 161:
    print("walk to (15,7):", rig.walk(161, {(15, 7)}, battle=rig.battle), rig.pos(), flush=True)
    drain()
    rig.io.press("down", hold=4, release=8)
    rig.ctl.wait(16)
    rig._arm_surf()
    for _ in range(40):
        if rig.pos()[0] != 161:
            break
        rig.ctl.wait(8)
    print("after the conveyor:", rig.pos(), flush=True)
    if rig.pos()[0] == 162:
        rig.bank("b4_from_conveyor")

if rig.pos()[0] == 162:
    rig.screenshot("b4_landing")
    # 1) cross the east water to its shore (23,5); 2) central land toward the west shores; 3) west water to (7,3)
    for stage, goals in [
        ("east shore", {(23, 5)}),
        ("west shore (7,3)", {(7, 3), (7, 11)}),
        ("platform edge", {(6, 2), (7, 1), (5, 1), (6, 0)}),
    ]:
        res = navigate(162, goals)
        print(f"stage {stage}: {res}", flush=True)
        rig.screenshot(f"b4_{stage.split()[0]}")
        if res[0] == "no-path":
            journal(f"map=162 B4 nav to {stage} NO-PATH from {res[1]}; blocked by current/wall")
            break
    # read (6,1): stand adjacent, face it, talk + screenshot
    m, x, y = rig.pos()
    if m == 162:
        for cell, face in (((6, 2), "up"), ((7, 1), "left"), ((5, 1), "right"), ((6, 0), "down")):
            if rig.walk(162, {cell}, battle=rig.battle) and rig.pos()[1:] == cell:
                said = rig.talk(face)
                print(f"*** sprite at (6,1) from {cell}: {said!r} ***", flush=True)
                rig.screenshot("b4_legendary")
                journal(
                    f"map=162 B4 the (6,1) sprite, read from {cell} facing {face}: {said!r}; "
                    f"in_battle={rig.mem[qm.ADDR_IN_BATTLE]}"
                )
                if rig.mem[qm.ADDR_IN_BATTLE]:
                    rig.bank("b4_legendary_battle")
                break
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
