"""From mansion_215_pressed.state, try every stair back to 214 and then to 165."""

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


def follow(mp, goal, blocked, cap=120):
    blocked = set(blocked)
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp or (x, y) == goal:
            return (x, y) == goal
        path = rt.path_on_map(TRUTH, rt.loaded_pairs(TRUTH), mp, (x, y), {goal}, blocked=blocked)
        if not path or len(path) < 2:
            print(f"   no path from {(x, y)} avoiding {sorted(blocked)}", flush=True)
            return False
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=8, release=8)
        rig.ctl.wait(30)
        if rig.pos()[1:] == (x, y):
            print(f"   refused {(x, y)} -> {(nx, ny)}; blocking it", flush=True)
            blocked.add((nx, ny))
    return False


print("start", rig.pos(), flush=True)

# Try (6,1) stair to 214
print("215 -> 214 via (6,1):", stairs(215, [(6, 2), (5, 1), (7, 1)], "up", 214), rig.pos(), flush=True)
if rig.pos()[0] == 214:
    print("214 from (6,1): to (5,11)?", follow(214, (5, 11), {(9, 4), (9, 5)}), rig.pos(), flush=True)
    if rig.pos()[1:] == (5, 11):
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(70)
        drain()
        print("after (5,11) up:", rig.pos(), flush=True)

# If still on 214 but not on 165, try (25,14) stair
if rig.pos()[0] == 214:
    print("214 -> 215 via (25,14) to reset", flush=True)
    if stairs(214, [(25, 13), (24, 14)], "up", 215):
        print("back on 215:", rig.pos(), flush=True)

if rig.pos()[0] == 215:
    print("215 -> 214 via (25,14):", stairs(215, [(25, 13), (24, 14)], "up", 214), rig.pos(), flush=True)
    if rig.pos()[0] == 214:
        print("214 from (25,14): to (5,11)?", follow(214, (5, 11), set()), rig.pos(), flush=True)
        if rig.pos()[1:] == (5, 11):
            rig.io.press("up", hold=16, release=16)
            rig.ctl.wait(70)
            drain()
            print("after (5,11) up:", rig.pos(), flush=True)

# Try (7,10) stair from 215
if rig.pos()[0] == 215:
    print("215 -> 214 via (7,10):", stairs(215, [(7, 11)], "up", 214), rig.pos(), flush=True)
    if rig.pos()[0] == 214:
        print("214 from (7,10): to (5,11)?", follow(214, (5, 11), {(9, 4), (9, 5)}), rig.pos(), flush=True)
        if rig.pos()[1:] == (5, 11):
            rig.io.press("up", hold=16, release=16)
            rig.ctl.wait(70)
            drain()
            print("after (5,11) up:", rig.pos(), flush=True)

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
            rig.bank("mansion_stairs_pocket_after_215")
            break

print("final", rig.pos(), flush=True)
