"""From secret_key_out.state, carefully walk to the right-side exit at (26,27) or (27,27)."""

import json
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
PAIRS = rt.loaded_pairs(TRUTH)
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}

rig = Rig("data/local_runs/roster-bench/secret_key_out.state", settle_on_boot=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def step_path(mp, goal, blocked, cap=200):
    blocked = set(blocked)
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp or (x, y) == goal:
            return (x, y) == goal
        path = rt.path_on_map(TRUTH, PAIRS, mp, (x, y), {goal}, blocked=blocked)
        if not path or len(path) < 2:
            print(f"   no path from {(x, y)} avoiding {sorted(blocked)}", flush=True)
            return False
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=8, release=8)
        rig.ctl.wait(30)
        drain()
        if rig.pos()[1:] == (x, y):
            print(f"   refused {(x, y)} -> {(nx, ny)}; blocking it", flush=True)
            blocked.add((nx, ny))
        else:
            print(f"   step {(x, y)} -> {(nx, ny)}", flush=True)
    return False


print("start", rig.pos(), flush=True)

# First, get to (25,14) or (25,15)
for init in [(20, 16), (25, 14), (25, 15)]:
    if rig.pos()[1:] == init:
        break
    drain()
    rig.walk(165, {init}, battle=rig.battle)
    print(f"walked to {init}: {rig.pos()}", flush=True)

# Try to reach (26,27) via manual path: go down along x=25 or x=26 to row 27
if rig.pos()[0] == 165:
    # Try direct walk first
    for goal in [(26, 27), (27, 27)]:
        print(f"trying rig.walk to {goal}...", flush=True)
        drain()
        w = rig.walk(165, {goal}, battle=rig.battle)
        print(f"  result: {w} {rig.pos()}", flush=True)
        if rig.pos()[1:] == goal:
            before = rig.pos()
            rig.io.press("down", hold=16, release=16)
            rig.ctl.wait(70)
            drain()
            print(f"  stepped down: {rig.pos()}", flush=True)
            if rig.pos()[0] == 8:
                print("*** ON CINNABAR ***", flush=True)
                break

# If still on 165, try step-by-step
if rig.pos()[0] == 165:
    print("trying step-by-step to (26,27)...", flush=True)
    step_path(165, (26, 27), set(), cap=300)
    if rig.pos()[1:] == (26, 27):
        before = rig.pos()
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(70)
        drain()
        print(f"stepped down: {rig.pos()}", flush=True)

print("final", rig.pos(), flush=True)
