"""Bank Strength-capable batons standing off any stair on Seafoam 1F (192) and B1 (159), for the oracle."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/seafoam_west_door.state", settle_on_boot=True)


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
for _ in range(5):  # settling leaves us on or just south of the door tile (48,5): press up until inside
    if rig.pos()[0] != 31:
        break
    rig.io.press("up", hold=16, release=16)
    rig.ctl.wait(60)
    drain()
print("after the door:", rig.pos(), flush=True)
if rig.pos()[0] == 192:
    print("1F: walk to (4,15):", rig.walk(192, {(4, 15)}, battle=rig.battle), rig.pos(), flush=True)
    rig.bank("seafoam_1f_str")
    print("1F: walk to (7,6) below the stair:", rig.walk(192, {(7, 6)}, battle=rig.battle), rig.pos(), flush=True)
    drain()
    rig.io.press("up", hold=8, release=8)
    rig.ctl.wait(60)
    drain()
    print("after the stair:", rig.pos(), flush=True)
if rig.pos()[0] == 159:
    print("B1: walk to (7,7):", rig.walk(159, {(7, 7)}, battle=rig.battle), rig.pos(), flush=True)
    rig.bank("seafoam_b1_str")
print("final", rig.pos(), flush=True)
