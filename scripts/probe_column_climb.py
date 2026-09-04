"""From the B4 landing: into the (20,17) warp, up B3's water column, east along the band, land at (23,12)."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/seafoam_b3_surfing.state", settle_on_boot=False)
print("start", rig.pos(), flush=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def go(key, until, cap=30):
    trail = [rig.pos()]
    for _ in range(cap):
        drain()
        if until(rig.pos()):
            break
        rig.io.press(key, hold=8, release=8)
        rig.ctl.wait(30)
        if rig.pos() != trail[-1]:
            trail.append(rig.pos())
    return trail


# measured: (20,16) refuses from (20,15); the x=21 column is open
print("B4: right to x=21:", go("right", lambda p: p[1] >= 21, cap=3), flush=True)
print("B4: down to the (21,17) warp:", go("down", lambda p: p[0] != 162, cap=6), flush=True)
rig.screenshot("after_b4_warp")
if rig.pos()[0] != 161:
    print("did not come up on B3; at", rig.pos(), flush=True)
    sys.exit(2)
print("B3 column: climb UP:", go("up", lambda p: p[2] <= 11 or p[0] != 161), flush=True)
rig.screenshot("column_top")
if rig.pos()[0] == 161 and rig.pos()[2] <= 11:
    print("band: EAST to x=23:", go("right", lambda p: p[1] >= 23 or p[0] != 161), flush=True)
    rig.screenshot("band_east")
if rig.pos()[0] == 161 and rig.pos()[1] >= 23:
    print("land: DOWN to (23,12):", go("down", lambda p: p[2] >= 12 or p[0] != 161, cap=4), flush=True)
    if rig.pos()[1:] == (23, 12):
        rig.bank("b3_east_region")
        print("*** B3 EAST REGION ***", rig.pos(), flush=True)
print("final", rig.pos(), repr(rig.textbox()), flush=True)
