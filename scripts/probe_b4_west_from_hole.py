"""Fall through B3's (3,16) hole (a boulder already in it) to B4's west side, then test whether the platform's
current is now passable. If the current still blocks, map exactly which B4 cells the drop reaches, per the west
channel. This tests the RIGHT current -- B4's west water by the (6,1) platform -- not B3's (15,7) conveyor.
"""

import json
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE = (
    sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/oracle/161_3-16_5-14_8-14_9-12_18-6_19-6.state"
)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def tile(mp, x, y):
    return int(TRUTH["maps"][str(mp)]["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(mp, x, y):
    m = TRUTH["maps"][str(mp)]
    return 0 <= x < m["width"] and 0 <= y < m["height"] and (m["grid"][y][x] == "1" or tile(mp, x, y) in (0x14, 0x15))


def drain(limit=14):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def journal(c):
    append_observations(
        "pokedex/memory",
        [
            {
                "referenced_time": datetime.now(timezone.utc).isoformat(),
                "priority": "important",
                "source_session": "extractor",
                "content": c,
            }
        ],
        dedupe=True,
    )


def navigate(mp, goals, cap=400, arm=True):
    goals = set(goals)
    blocked = set()
    stuck = 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp:
            return ("left-map", (m, x, y))
        if (x, y) in goals:
            return ("reached", (x, y))
        prev = {(x, y): None}
        q = deque([(x, y)])
        path = None
        while q:
            c = q.popleft()
            if c in goals:
                path = [c]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                path = path[::-1]
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if n not in prev and n not in blocked and enterable(mp, *n):
                    prev[n] = c
                    q.append(n)
        if not path or len(path) < 2:
            return ("no-path", (x, y))
        nx, ny = path[1]
        if arm and tile(mp, nx, ny) == 0x14 and tile(mp, x, y) != 0x14:
            rig.io.press(K[(nx - x, ny - y)], hold=4, release=8)
            rig.ctl.wait(12)
            ok = rig._arm_surf()
            said = rig.textbox()
            drain()
            if not ok and rig.pos()[1:] == (x, y):
                print(f"  surf refused {(x, y)}->{(nx, ny)}: {said!r}", flush=True)
                blocked.add((nx, ny))
                continue
        rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
        rig.ctl.wait(24)
        drain()
        if rig.pos()[0] != mp:
            return ("left-map", rig.pos())
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


print("start", rig.pos(), "boulders(sprites)", sorted(tuple(b[:3]) for b in rig.bodies()), flush=True)
drain()
# step onto the (3,16) hole to fall to B4. approach from (3,15) DOWN, or (2,16)/(4,16).
fell = False
for stand, face in (((3, 15), "down"), ((2, 16), "right"), ((4, 16), "left")):
    if rig.walk(161, {stand}, battle=rig.battle) and rig.pos()[1:] == stand:
        rig.io.press(face, hold=16, release=16)
        rig.ctl.wait(70)
        drain()
        if rig.pos()[0] == 162:
            fell = True
            break
print("after the hole:", rig.pos(), flush=True)
if fell:
    rig.bank("b4_west_from_hole")
    rig.screenshot("b4_west_landing")
    journal(f"map=162 fell through B3 (3,16) hole -> B4 at {rig.pos()[1:]} (west side)")
    # from here try to reach the platform edge, arming surf on the west water
    res = navigate(162, {(6, 2), (7, 1), (5, 1), (6, 0), (7, 2)})
    print("navigate to platform edge:", res, flush=True)
    rig.screenshot("b4_west_reach")
    m, x, y = rig.pos()
    if m == 162 and y <= 4:
        for cell, face in (((6, 2), "up"), ((7, 1), "left"), ((5, 1), "right"), ((7, 2), "up")):
            if rig.walk(162, {cell}, battle=rig.battle) and rig.pos()[1:] == cell:
                said = rig.talk(face)
                inb = rig.mem[qm.ADDR_IN_BATTLE]
                print(f"*** (6,1) from {cell}: {said!r} in_battle={inb} ***", flush=True)
                rig.screenshot("b4_legendary")
                journal(f"map=162 B4 (6,1) read from {cell} facing {face}: {said!r}; in_battle={inb}")
                if inb:
                    rig.bank("b4_legendary_battle")
                break
    else:
        journal(f"map=162 from the hole-drop, platform nav = {res}; the west current still blocks the crossing")
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
