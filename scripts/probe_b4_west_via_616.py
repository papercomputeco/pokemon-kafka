"""Drop through B3's (6,16) hole to B4's west channel (~(5,14)), then navigate the west water to the (6,1)
platform, arming SURF with use_field_move (the working verb) and reading 'The current is much too fast!' when
it blocks. This tests reaching the legendary from the west side directly, no boulder-current stop required.
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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/seafoam_loop_stuck_3.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def tile(mp, x, y):
    return int(TRUTH["maps"][str(mp)]["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(mp, x, y):
    m = TRUTH["maps"][str(mp)]
    return 0 <= x < m["width"] and 0 <= y < m["height"] and (m["grid"][y][x] == "1" or tile(mp, x, y) in (0x14, 0x15))


def drain(n=14):
    for _ in range(n):
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


def arm_surf():
    """The working arm: face water, use SURF via species, return (moved, said)."""
    before = rig.pos()
    used = rig.use_field_move("SURF", species="Gyarados")
    said = rig.textbox()
    drain()
    return rig.pos() != before, said, used


def navigate(mp, goals, cap=300):
    goals = set(goals)
    blocked = set()
    stuck = 0
    log = []
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp:
            return ("left-map", (m, x, y), log)
        if (x, y) in goals:
            return ("reached", (x, y), log)
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
            return ("no-path", (x, y), log)
        nx, ny = path[1]
        onto_water = tile(mp, nx, ny) == 0x14 and tile(mp, x, y) != 0x14
        if onto_water:
            rig.io.press(K[(nx - x, ny - y)], hold=4, release=8)
            rig.ctl.wait(12)
            moved, said, used = arm_surf()
            if not moved:
                log.append(f"blocked {(x, y)}->{(nx, ny)}: {said!r}")
                print(f"  surf blocked {(x, y)}->{(nx, ny)}: {said!r}", flush=True)
                blocked.add((nx, ny))
                continue
        else:
            rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
            rig.ctl.wait(24)
            drain()
        if rig.pos()[0] != mp:
            return ("left-map", rig.pos(), log)
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
    return ("cap", rig.pos()[1:], log)


print("start", rig.pos(), flush=True)
drain()
# drop through the (6,16) hole: approach from (6,15)/(5,16)/(7,16) and step onto it
fell = False
for stand, face in (((6, 15), "down"), ((5, 16), "right"), ((7, 16), "left")):
    if rig.walk(161, {stand}, battle=rig.battle) and rig.pos()[1:] == stand:
        rig.io.press(face, hold=16, release=16)
        rig.ctl.wait(70)
        drain()
    if rig.pos()[0] == 162:
        fell = True
        break
print("after (6,16):", rig.pos(), flush=True)
if rig.pos()[0] == 162:
    rig.bank("b4_from_616")
    rig.screenshot("b4_616_landing")
    journal(f"map=162 fell through B3 (6,16) hole -> B4 at {rig.pos()[1:]}")
    res = navigate(162, {(6, 2), (7, 1), (5, 1), (6, 0), (7, 2)})
    print("navigate to platform edge:", res[0], res[1], flush=True)
    for line in res[2][:12]:
        print("   ", line, flush=True)
    rig.screenshot("b4_616_reach")
    journal(f"map=162 from (6,16) drop, platform nav={res[0]} at {res[1]}; blocks={res[2][:6]}")
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
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
