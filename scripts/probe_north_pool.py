"""B3's untried shore: the north pool from (15,4) facing up; then a Strength push on (18,6) from the water."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/seafoam_loop_stuck_3.state", settle_on_boot=True)


def drain(limit=12):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def sprites():
    return sorted(rig.bodies())


drain()
who = rig.knows_move("STRENGTH")
print("activate STRENGTH:", rig.use_field_move("STRENGTH", species=rig.party()[who][0]), flush=True)
for _ in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(40)
drain()
print("walk to (15,4):", rig.walk(161, {(15, 4)}, battle=rig.battle), rig.pos(), flush=True)
drain()
rig.io.press("up", hold=4, release=8)
rig.ctl.wait(20)
armed = rig._arm_surf()
traj = [rig.pos()]
for _ in range(30):
    rig.ctl.wait(8)
    if rig.pos() != traj[-1]:
        traj.append(rig.pos())
    if rig.pos()[0] != 161:
        break
print("north pool: armed", armed, "trajectory", traj, flush=True)
rig.screenshot("north_pool")
if rig.pos()[0] == 161 and rig.pos()[2] <= 5:
    rig.bank("b3_north_pool")
    # surf east along the pool to (18,5), face the boulder below, push
    for key, want in (("right", 18), ("down", 5)):
        for _ in range(12):
            drain()
            p = rig.pos()
            if (key == "right" and p[1] >= want) or (key == "down" and p[2] >= want):
                break
            rig.io.press(key, hold=8, release=8)
            rig.ctl.wait(30)
    print("at", rig.pos(), "sprites", sprites(), flush=True)
    before = sprites()
    rig.io.press("down", hold=4, release=8)
    rig.ctl.wait(20)
    drain()
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(70)
    print("push (18,6) DOWN from water:", rig.pos(), before, "->", sprites(), repr(rig.textbox()), flush=True)
    rig.screenshot("push_from_water")
    if sprites() != before:
        rig.bank("b3_channel_pushed")
        print("*** BOULDER MOVED FROM THE WATER ***", flush=True)
print("final", rig.pos(), flush=True)
