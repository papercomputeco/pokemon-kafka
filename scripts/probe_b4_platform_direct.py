"""From the B4 (map 162) conveyor landing, navigate straight to the (6,1) platform and read what stands on it.

Static enterable-BFS proves the landing (20,15) reaches the platform in ~30 steps: down/across the east water,
through the central land, up the west water's left channel to (7,4), up onto the (7,3) shore and the platform.
The earlier staged run detoured onto the wrong shore (7,11); this goes for the platform-adjacent cells directly.
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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/b4_from_conveyor.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def tile(mp, x, y):
    return int(TRUTH["maps"][str(mp)]["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(mp, x, y):
    m = TRUTH["maps"][str(mp)]
    return 0 <= x < m["width"] and 0 <= y < m["height"] and (m["grid"][y][x] == "1" or tile(mp, x, y) in (0x14, 0x15))


def bfs(mp, start, goals, blocked):
    goals = set(goals)
    prev = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        if c in goals:
            p = [c]
            while prev[p[-1]] is not None:
                p.append(prev[p[-1]])
            return p[::-1]
        x, y = c
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n not in prev and n not in blocked and enterable(mp, *n):
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


def navigate(mp, goals, cap=600):
    goals = set(goals)
    blocked = set()
    stuck = 0
    seen_at = {}
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp:
            return ("left-map", (m, x, y))
        if (x, y) in goals:
            return ("reached", (m, x, y))
        seen_at[(x, y)] = seen_at.get((x, y), 0) + 1
        path = bfs(mp, (x, y), goals, blocked)
        if not path or len(path) < 2:
            return ("no-path", (m, x, y))
        nx, ny = path[1]
        if tile(mp, nx, ny) == 0x14 and tile(mp, x, y) != 0x14:
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
                print(f"  wall at {(nx, ny)} from {(x, y)}", flush=True)
        else:
            stuck = 0
    return ("cap", rig.pos())


print("start", rig.pos(), "party", rig.party(), flush=True)
drain()
res = navigate(162, {(6, 2), (7, 1), (5, 1), (6, 0)})
print("navigate to platform edge:", res, flush=True)
rig.screenshot("b4_platform_reached")
m, x, y = rig.pos()
if m == 162:
    for cell, face in (((6, 2), "up"), ((7, 1), "left"), ((5, 1), "right"), ((6, 0), "down"), ((7, 2), "up")):
        w = rig.walk(162, {cell}, battle=rig.battle)
        if rig.pos()[1:] == cell:
            rig.screenshot(f"b4_beside_{cell[0]}_{cell[1]}")
            said = rig.talk(face)
            inb = rig.mem[qm.ADDR_IN_BATTLE]
            print(f"*** sprite at (6,1) from {cell} facing {face}: {said!r} | in_battle={inb} ***", flush=True)
            rig.screenshot("b4_legendary")
            journal(f"map=162 B4 the (6,1) platform sprite, read from {cell} facing {face}: {said!r}; in_battle={inb}")
            if inb:
                rig.bank("b4_legendary_battle")
                # look at the battle: species/level from the enemy read
                enemy = qm.read_enemy(rig.io) if hasattr(qm, "read_enemy") else None
                print("enemy:", enemy, flush=True)
            break
    else:
        print("could not stand beside (6,1); at", rig.pos(), flush=True)
        journal(f"map=162 B4 platform reached ({res}) but no cell beside (6,1) was stood on; final {rig.pos()}")
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
