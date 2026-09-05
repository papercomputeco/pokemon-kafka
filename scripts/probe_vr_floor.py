"""Victory Road, one floor: walk (grid BFS, bodies solid, no tile-pair model; trainers fought when they challenge)
to a target warp cell and step through. argv: state, map, target x, target y, bank name, [face key]."""

import json
import subprocess
import sys
from collections import deque

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE, MAP, TX, TY, BANK = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
FACE = sys.argv[6] if len(sys.argv) > 6 else None
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
M = TRUTH["maps"][str(MAP)]


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


def navigate(goals, cap=400):
    goals, blocked, stuck = set(goals), set(), 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != MAP:
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
                if n in prev or n in solid or not (0 <= n[0] < M["width"] and 0 <= n[1] < M["height"]):
                    continue
                if M["grid"][n[1]][n[0]] == "1":
                    prev[n] = c
                    q.append(n)
        if not path or len(path) < 2:
            return ("no-path", (x, y), sorted(blocked))
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
        rig.ctl.wait(24)
        drain()
        if rig.pos()[0] != MAP:
            return ("left-map", rig.pos())
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
                print(f"  wall {(x, y)}->{(nx, ny)}", flush=True)
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


print("start", rig.pos(), "bodies", sorted(bodies()), flush=True)
drain()
r = navigate({(TX, TY)})
print("navigate:", r, rig.pos(), flush=True)
if rig.pos()[0] == MAP and FACE:
    rig.io.press(FACE, hold=16, release=16)
    rig.ctl.wait(90)
    drain()
if rig.pos()[0] != MAP:
    rig.bank(BANK)
    print(f"*** {BANK}: {rig.pos()} bodies {sorted(bodies())} ***", flush=True)
else:
    rig.screenshot(f"vr_{MAP}_stuck")
    rig.bank(f"{BANK}_stuck")
print("final", rig.pos(), flush=True)
