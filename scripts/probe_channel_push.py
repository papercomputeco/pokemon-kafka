"""Land on B3 (19,7) through B2's east hole; do we stay put without input, and can (19,6) be pushed UP from there?"""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/b2_east_after_drop.state", settle_on_boot=False)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


drain()
who = rig.knows_move("STRENGTH")
print("activate on B2:", rig.use_field_move("STRENGTH", species=rig.party()[who][0]), flush=True)
for _ in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(40)
drain()
print("walk to (22,7):", rig.walk(160, {(22, 7)}, battle=rig.battle), rig.pos(), flush=True)
for _ in range(3):
    if rig.pos()[0] == 161:
        break
    rig.io.press("up", hold=16, release=16)
    rig.ctl.wait(90)
print("landed:", rig.pos(), repr(rig.textbox()), "sprites", sorted(rig.bodies()), flush=True)
rig.screenshot("b3_19_7_landing")
# measured: with no input the water carries us (19,7)->(18,7)->(18,8)->(18,9), ~30 frames a cell.
# So the push goes in at once, then the drift is mapped on a second landing.
before = sorted(rig.bodies())
rig.io.press("up", hold=16, release=8)
rig.ctl.wait(40)
print("immediate push UP:", rig.pos(), before, "->", sorted(rig.bodies()), repr(rig.textbox()), flush=True)
rig.screenshot("channel_push_up")
if sorted(rig.bodies()) != before:
    rig.bank("b3_channel_opened")
    print("*** CHANNEL BOULDER MOVED ***", flush=True)
rig2 = Rig("data/local_runs/roster-bench/b2_east_after_drop.state", settle_on_boot=False)
rig2.walk(160, {(22, 7)}, battle=rig2.battle)
for _ in range(3):
    if rig2.pos()[0] == 161:
        break
    rig2.io.press("up", hold=16, release=16)
    rig2.ctl.wait(90)
trail = [rig2.pos()]
for _ in range(90):
    rig2.ctl.wait(8)
    if rig2.pos() != trail[-1]:
        trail.append(rig2.pos())
    if rig2.pos()[0] != 161:
        break
cells = [f"{p[1]},{p[2]}" if p[0] == 161 else f"map{p[0]}@{p[1]},{p[2]}" for p in trail]
print("full no-input drift:", " > ".join(cells), flush=True)
