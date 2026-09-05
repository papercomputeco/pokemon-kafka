"""From secret_key_out.state, carefully exit the mansion to map 8."""

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
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)

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

# First, step to (20,16) to get fully out of the pocket
drain()
if rig.pos()[1:] == (20, 17):
    rig.io.press("up", hold=8, release=8)
    rig.ctl.wait(30)
    drain()
    print("stepped to", rig.pos(), flush=True)

# Now navigate to exit (6,27) or (7,27)
if rig.pos()[0] == 165:
    for goal in [(6, 27), (7, 27)]:
        print(f"trying to reach {goal}...", flush=True)
        ok = step_path(165, goal, set(), cap=300)
        print(f"reached {goal}: {ok} {rig.pos()}", flush=True)
        if ok:
            break

# Step down through the exit
if rig.pos()[0] == 165 and rig.pos()[1:] in [(6, 27), (7, 27)]:
    for _ in range(3):
        if rig.pos()[0] == 8:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(70)
        drain()
        print("step down:", rig.pos(), flush=True)

print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
