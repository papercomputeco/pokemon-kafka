"""Replay B1's (17,6) RIGHT push: the boulder and the player fall to B2. Bank there and read B2's sprites."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/seafoam_b1_str.state", settle_on_boot=True)


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
print("activate:", rig.use_field_move("STRENGTH", species=rig.party()[who][0]), flush=True)
for _ in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(40)
drain()
w = rig.walk(159, {(16, 6)}, battle=rig.battle)
print("B1 sprites:", sorted(rig.bodies()), "| walk:", w, rig.pos(), flush=True)
drain()
rig.io.press("right", hold=4, release=8)
rig.ctl.wait(20)
drain()
rig.io.press("right", hold=16, release=16)
rig.ctl.wait(90)
drain()
print("after the push:", rig.pos(), "| sprites here:", sorted(rig.bodies()), flush=True)
rig.screenshot("b1_drop_landing")
if rig.pos()[0] == 160:
    rig.bank("b2_after_b1_drop")
    print("*** banked on B2 after the drop ***", flush=True)
