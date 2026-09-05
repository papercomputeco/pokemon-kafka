"""From mansion_215_pressed.state, test whether (10,6) region connects to (7,11) region on 215."""

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


def step_path(rig, mp, goal, cap=80):
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


def stairs(mp, beside, key, want):
    drain()
    rig.walk(mp, set(beside), battle=rig.battle)
    for _ in range(3):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(70)
        drain()
    return rig.pos()[0] == want


print("start", rig.pos(), flush=True)

# Try walking from (10,6) to (7,11) on 215
print("215: (10,6) -> (7,11)?", step_path(rig, 215, (7, 11)), rig.pos(), flush=True)

if rig.pos()[1:] == (7, 11):
    print("*** (7,11) REACHABLE FROM (10,6) ***", flush=True)
    print("215 -> 214 via (7,10):", stairs(215, [(7, 11)], "up", 214), rig.pos(), flush=True)
    if rig.pos()[0] == 214:
        print("214: (7,10) -> (5,11)?", step_path(rig, 214, (5, 11)), rig.pos(), flush=True)
        if rig.pos()[1:] == (5, 11):
            rig.io.press("up", hold=16, release=16)
            rig.ctl.wait(70)
            drain()
            print("165?", rig.pos(), flush=True)

if rig.pos()[0] == 165:
    print("*** BACK ON 165 ***", rig.pos(), flush=True)
    for stand in ((20, 16), (21, 16)):
        drain()
        rig.walk(165, {stand}, battle=rig.battle)
        if rig.pos()[1:] != stand:
            continue
        before = rig.pos()
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(40)
        drain()
        print(f"   {stand} DOWN -> moved={rig.pos() != before}", flush=True)
        if rig.pos() != before:
            rig.bank("mansion_stairs_pocket_215")
            break

print("final", rig.pos(), flush=True)
