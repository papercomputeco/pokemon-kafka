"""Route 23 (34) north to Victory Road: land+water BFS (SURF armed by use_field_move on a water step), every guard
talked to when it blocks the way (what they say with 8 badges is the record), then (4,32) UP onto the (4,31) warp
-> map 108. Bank victory_road_1f_kit."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/route23_kit.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
M = TRUTH["maps"]["34"]
GUARDS = {}


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


def tile(x, y):
    return int(M["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(x, y):
    return 0 <= x < M["width"] and 0 <= y < M["height"] and (M["grid"][y][x] == "1" or tile(x, y) in (0x14, 0x11))


def drain(n=14):
    for _ in range(n):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def bodies():
    return {tuple(b[:2]) for b in rig.bodies()}


def talk(body):
    x, y = rig.pos()[1:]
    dx, dy = body[0] - x, body[1] - y
    if abs(dx) + abs(dy) != 1:
        return None
    said = rig.talk(K[(dx, dy)])
    drain()
    GUARDS[body] = said
    print(f"  guard {body}: {said!r}", flush=True)
    return said


def navigate(goals, cap=700):
    goals, blocked, stuck = set(goals), set(), 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != 34:
            return ("left-map", (m, x, y))
        if (x, y) in goals:
            return ("reached", (x, y))
        solid = (bodies() - goals) | blocked
        prev, q, path = {(x, y): None}, deque([(x, y)]), None
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
                if n not in prev and n not in solid and enterable(*n):
                    prev[n] = c
                    q.append(n)
        if not path or len(path) < 2:
            # a guard in a one-tile corridor: talk to any adjacent body, then try again
            near = [b for b in bodies() if abs(b[0] - x) + abs(b[1] - y) == 1 and b not in GUARDS]
            if near:
                talk(near[0])
                continue
            return ("no-path", (x, y))
        nx, ny = path[1]
        if tile(nx, ny) in (0x14, 0x11) and tile(x, y) not in (0x14, 0x11):
            rig.io.press(K[(nx - x, ny - y)], hold=4, release=8)
            rig.ctl.wait(12)
            before = rig.pos()
            rig.use_field_move("SURF", species="Gyarados")
            said = rig.textbox()
            drain()
            rig.ctl.wait(30)
            if rig.pos() == before:
                print(f"  surf blocked {(x, y)}->{(nx, ny)}: {said!r}", flush=True)
                blocked.add((nx, ny))
                continue
        else:
            rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
            rig.ctl.wait(24)
            drain()
        if rig.pos()[0] != 34:
            return ("left-map", rig.pos())
        if rig.pos()[1:] == (x, y):
            stuck += 1
            near = [
                b
                for b in bodies()
                if abs(b[0] - nx) + abs(b[1] - ny) == 0 or (abs(b[0] - x) + abs(b[1] - y) == 1 and b not in GUARDS)
            ]
            if near:
                talk(near[0])
                stuck = 0
                continue
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
                print(f"  wall {(x, y)}->{(nx, ny)}", flush=True)
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


print("start", rig.pos(), "bodies", sorted(bodies()), flush=True)
drain()
r = navigate({(4, 32)})
print("to (4,32):", r, rig.pos(), flush=True)
rig.screenshot("route23_top")
journal(f"map=34 Route 23 with 8 badges: nav={r}; guards said {GUARDS}")
if rig.pos()[1:] == (4, 32):
    rig.bank("route23_top_kit")
    for _ in range(3):
        if rig.pos()[0] == 108:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
if rig.pos()[0] == 108:
    rig.bank("victory_road_1f_kit")
    print("*** VICTORY ROAD 1F -- banked victory_road_1f_kit ***", rig.pos(), sorted(bodies()), flush=True)
    journal(f"map=108 Victory Road 1F entered from Route 23 (4,31); landed {rig.pos()[1:]}; bodies {sorted(bodies())}")
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
