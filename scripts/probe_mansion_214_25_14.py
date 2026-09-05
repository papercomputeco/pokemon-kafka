"""From mansion_215_pressed.state, warp to 214 via (25,14) and test connectivity."""

import json
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}

rig = Rig("data/local_runs/roster-bench/mansion_215_pressed.state", settle_on_boot=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def step_path(rig, mp, goal, cap=120):
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp or (x, y) == goal:
            return True
        path = rt.path_on_map(TRUTH, rt.loaded_pairs(TRUTH), mp, (x, y), {goal})
        if not path or len(path) < 2:
            print(f"   no ROM path from {(x, y)} to {goal}", flush=True)
            return False
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=8, release=8)
        rig.ctl.wait(30)
        if rig.pos()[1:] == (x, y):
            print(f"   REFUSED {(x, y)} -> {(nx, ny)} on {mp}", flush=True)
            return False
    return False


print("start", rig.pos(), flush=True)

# Walk to (25,14) on 215 and warp to 214
print("walk to (25,14)?", step_path(rig, 215, (25, 14)), rig.pos(), flush=True)

if rig.pos()[1:] == (25, 14):
    print("at (25,14), pressing up to warp", flush=True)
    rig.io.press("up", hold=16, release=16)
    rig.ctl.wait(70)
    drain()
    print("after warp:", rig.pos(), flush=True)

if rig.pos()[0] == 214:
    print("214: (25,14) -> (5,11)?", step_path(rig, 214, (5, 11)), rig.pos(), flush=True)
    if rig.pos()[1:] == (5, 11):
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(70)
        drain()
        print("165?", rig.pos(), flush=True)

# Also try (25,14) -> (6,1) on 214
if rig.pos()[0] == 214:
    print("214: (25,14) -> (6,1)?", step_path(rig, 214, (6, 1)), rig.pos(), flush=True)

# Also try (25,14) -> (7,10) on 214
if rig.pos()[0] == 214:
    print("214: (25,14) -> (7,10)?", step_path(rig, 214, (7, 10)), rig.pos(), flush=True)

print("final", rig.pos(), flush=True)
