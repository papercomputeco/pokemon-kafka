"""Which cells on Seafoam B3 (map 161) accept SURF? Try every reachable shore cell and record the sentence.

At (18,12) facing the 0x14 water at (18,11) the game said "No SURFing on GYARADOS here!" with
Gyarados standing at 73/73. The tile model calls 0x14 water everywhere; the cartridge disagrees
somewhere. Verdict per cell: position change (armed) or the refusal sentence.
"""

import json
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import road  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/seafoam_loop_stuck_3.state"
MAP = 161
rig = Rig(STATE, settle_on_boot=True)
truth = json.load(open("references/rom_truth.json"))
pairs = rt.loaded_pairs(truth)
m = truth["maps"][str(MAP)]
assert rig.pos()[0] == MAP, rig.pos()


def tid(x, y):
    return int(m["tiles"][y][2 * x : 2 * x + 2], 16)


def drain(limit=14):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


_mp, sx, sy = rig.pos()
region = road.reachable(truth, pairs, MAP, (sx, sy))
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
cands = []
for x, y in region:
    for key, (dx, dy) in DIRS.items():
        nx, ny = x + dx, y + dy
        if 0 <= nx < m["width"] and 0 <= ny < m["height"] and m["grid"][ny][nx] != "1" and tid(nx, ny) == 0x14:
            cands.append((abs(x - sx) + abs(y - sy), (x, y), key, (nx, ny)))
cands.sort()
print(f"{len(cands)} shore (cell, facing) pairs in reach; trying the nearest 10", flush=True)
for _d, cell, key, water in cands[:10]:
    drain()
    r = rig.walk(MAP, {cell}, battle=rig.battle)
    if rig.pos()[1:] != cell:
        print(f"  {cell}: could not stand there ({r}), at {rig.pos()[1:]}", flush=True)
        continue
    rig.io.press(key, hold=4, release=8)
    rig.ctl.wait(20)
    before = rig.pos()
    ok = rig._arm_surf()
    said = rig.textbox()
    print(f"  {cell} {key} -> {water} {hex(tid(*water))}: armed={ok} now={rig.pos()[1:]}", repr(said), flush=True)
    drain()
    if ok or rig.pos() != before:
        rig.screenshot("b3_surfing")
        rig.bank("seafoam_b3_surfing")
        print("*** SURF ARMED on B3 at", rig.pos(), "***", flush=True)
        break
