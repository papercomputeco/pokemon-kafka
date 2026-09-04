"""Decisive B4 test: reach shore (7,11) from the landing (manual surf/walk), then arm SURF DOWN into the west
water (7,12) -- the only launch from central land into the platform's pond. Read the exact sentence either way.
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


def tile(x, y):
    return int(TRUTH["maps"]["162"]["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(x, y):
    m = TRUTH["maps"]["162"]
    return 0 <= x < m["width"] and 0 <= y < m["height"] and (m["grid"][y][x] == "1" or tile(x, y) in (0x14, 0x15))


def bfs(start, goals, blocked):
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
            if n not in prev and n not in blocked and enterable(*n):
                prev[n] = c
                q.append(n)
    return None


def drain(limit=12):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


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


def navigate(goals, cap=400):
    goals = set(goals)
    blocked = set()
    stuck = 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != 162:
            return ("left-map", (m, x, y))
        if (x, y) in goals:
            return ("reached", (x, y))
        path = bfs((x, y), goals, blocked)
        if not path or len(path) < 2:
            return ("no-path", (x, y))
        nx, ny = path[1]
        if tile(nx, ny) == 0x14 and tile(x, y) != 0x14:
            rig.io.press(K[(nx - x, ny - y)], hold=4, release=8)
            rig.ctl.wait(12)
            rig._arm_surf()
            drain()
        rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
        rig.ctl.wait(24)
        drain()
        m2, x2, y2 = rig.pos()
        if m2 != 162:
            return ("left-map", (m2, x2, y2))
        if (x2, y2) == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


def arm_test(shore, face, water):
    res = navigate({shore})
    if res[0] != "reached":
        return f"nav-to-{shore}:{res}"
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(16)
    before = rig.pos()
    armed = rig._arm_surf()
    said = rig.textbox()
    after = rig.pos()
    rig.screenshot(f"b4_launch_{shore[0]}_{shore[1]}")
    drain()
    out = f"armed={armed} moved={after != before} now={after[1:]} said={said!r}"
    if after != before and after[0] == 162:
        rig.bank(f"b4_launched_{shore[0]}_{shore[1]}")
        # continue on toward the platform
        res2 = navigate({(6, 2), (7, 1), (5, 1)})
        out += f" | onward:{res2}"
        if res2[0] == "reached":
            rig.bank("b4_platform_edge")
    return out


print("start", rig.pos(), flush=True)
r1 = arm_test((7, 11), "down", (7, 12))
print("launch off (7,11):", r1, flush=True)
if "onward:('reached'" not in r1:
    r2 = arm_test((7, 3), "down", (7, 4))
    print("launch off (7,3):", r2, flush=True)
else:
    r2 = "skipped"
journal(f"map=162 B4 launch test: (7,11)->{r1} ; (7,3)->{r2}")
# if on the platform edge, read (6,1)
m, x, y = rig.pos()
if m == 162 and y <= 3:
    for cell, face in (((6, 2), "up"), ((7, 1), "left"), ((5, 1), "right"), ((7, 2), "up")):
        if rig.walk(162, {cell}, battle=rig.battle) and rig.pos()[1:] == cell:
            said = rig.talk(face)
            inb = rig.mem[qm.ADDR_IN_BATTLE]
            print(f"*** (6,1) from {cell}: {said!r} in_battle={inb} ***", flush=True)
            rig.screenshot("b4_legendary")
            journal(f"map=162 B4 (6,1) sprite from {cell} facing {face}: {said!r}; in_battle={inb}")
            if inb:
                rig.bank("b4_legendary_battle")
            break
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
