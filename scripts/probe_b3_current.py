"""Catalog B3's current: enter the water at (15,8) and log where it carries the surfer, per held input."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/seafoam_loop_stuck_3.state", settle_on_boot=True)
import io as _io  # noqa: E402


def drain(limit=12):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


drain()
print("walk to (15,7):", rig.walk(161, {(15, 7)}, battle=rig.battle), rig.pos(), flush=True)
drain()
rig.io.press("down", hold=4, release=8)
rig.ctl.wait(20)
root = _io.BytesIO()
rig.pb.save_state(root)
for held in (None, "right", "up", "left", "down"):
    rig.pb.load_state(_io.BytesIO(root.getvalue()))
    rig.ctl.wait(10)
    armed = rig._arm_surf()
    drain()
    traj = [rig.pos()]
    for _ in range(40):
        if held:
            rig.io.press(held, hold=8, release=0)
        else:
            rig.ctl.wait(8)
        p = rig.pos()
        if p != traj[-1]:
            traj.append(p)
        if p[0] != 161:
            break
    comp = [f"{p[1]},{p[2]}" if p[0] == 161 else f"map{p[0]}@{p[1]},{p[2]}" for p in traj]
    print(f"held={held!s:5} armed={armed}: " + " > ".join(comp), flush=True)
