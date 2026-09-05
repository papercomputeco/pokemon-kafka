"""Route 23's north half (the ledge maze) to the Plateau (9) and into the League lobby (174). The ROM planner's
path (ledge hops included), one press per step. Bank indigo_lobby."""

import json
import subprocess
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
PAIRS = rt.loaded_pairs(TRUTH)
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/vr_exit_route23.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def settle():
    for _ in range(3):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
        rig.ctl.press("b")
        rig.ctl.wait(20)


def bodies():
    return {tuple(b[:2]) for b in rig.bodies()}


def navigate(mp, goals, cap=400):
    goals, blocked, stuck = set(goals), set(), 0
    for _ in range(cap):
        settle()
        m, x, y = rig.pos()
        if m != mp:
            return ("left-map", (m, x, y))
        if (x, y) in goals:
            return ("reached", (x, y))
        path = rt.path_on_map(TRUTH, PAIRS, mp, (x, y), goals, blocked=(bodies() - goals) | blocked)
        if not path or len(path) < 2:
            return ("no-path", (x, y))
        nx, ny = path[1]
        dx, dy = nx - x, ny - y
        key = K[(dx // abs(dx) if dx else 0, dy // abs(dy) if dy else 0)]
        rig.io.press(key, hold=12, release=8)
        rig.ctl.wait(40 if abs(dx) + abs(dy) == 2 else 24)
        if rig.pos()[0] != mp:
            return ("left-map", rig.pos())
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
                print(f"  refused {(x, y)}->{(nx, ny)}", flush=True)
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


print("start", rig.pos(), flush=True)
settle()
if rig.pos()[0] == 34:
    r = navigate(34, {(9, 0), (10, 0)})
    print("to Route 23's north edge:", r, rig.pos(), flush=True)
    for _ in range(3):
        if rig.pos()[0] != 34:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
print("Plateau?", rig.pos(), flush=True)
if rig.pos()[0] == 9:
    rig.bank("indigo_plateau")
    r = navigate(9, {(9, 6), (10, 6)})
    print("to the League door step:", r, rig.pos(), flush=True)
    for _ in range(3):
        if rig.pos()[0] != 9:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
if rig.pos()[0] == 174:
    rig.bank("indigo_lobby")
    print("*** LEAGUE LOBBY -- banked indigo_lobby ***", rig.pos(), "bodies", sorted(bodies()), flush=True)
print("final", rig.pos(), flush=True)
