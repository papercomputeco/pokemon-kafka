"""After the first switch: walk the ROM path from (24,12) toward the (21,23) stairs; name the refused cell."""

import json
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

truth = json.load(open("references/rom_truth.json"))
rig = Rig("data/local_runs/roster-bench/mansion_doors_open.state", settle_on_boot=True)
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


print("start", rig.pos(), flush=True)
for _ in range(60):
    drain()
    mp, x, y = rig.pos()
    if mp != 165 or (x, y) == (21, 22):
        break
    path = rt.path_on_map(truth, rt.loaded_pairs(truth), 165, (x, y), {(21, 22)})
    if not path or len(path) < 2:
        print("no ROM path from", (x, y), flush=True)
        break
    nx, ny = path[1]
    rig.io.press(K[(nx - x, ny - y)], hold=8, release=8)
    rig.ctl.wait(30)
    drain()
    if rig.pos()[1:] == (x, y):
        m = truth["maps"]["165"]
        tid = m["tiles"][ny][2 * nx : 2 * nx + 2]
        print(f"REFUSED step {(x, y)} -> {(nx, ny)} (tile 0x{tid}): {rig.textbox()!r}", flush=True)
        rig.screenshot("mansion_refused")
        break
print("end", rig.pos(), flush=True)
if rig.pos()[1:] == (21, 22):
    rig.bank("mansion_at_stairs")
    print("*** at the stairs ***", flush=True)
