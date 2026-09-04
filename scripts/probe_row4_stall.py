"""At (87,4) on Route 20 a surfer stalls pressing LEFT although the run before passed it. Measure."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

FACING = 0xC109
rig = Rig("data/local_runs/roster-bench/merged_on_31.state", settle_on_boot=True)


def clear():
    if rig.mem[qm.ADDR_IN_BATTLE]:
        rig.battle()


for _ in range(60):  # straight west from (99,4)
    clear()
    if rig.pos()[1] <= 87:
        break
    rig.ctl.press("left")
    rig.ctl.wait(24)
print("at", rig.pos(), "facing", hex(rig.mem[FACING]), "text:", repr(rig.textbox()), flush=True)
for key in ("left", "up", "down", "left", "left"):
    clear()
    before, f0 = rig.pos(), rig.mem[FACING]
    rig.ctl.press(key, hold_frames=40, release_frames=20)
    rig.ctl.wait(40)
    now, f1 = rig.pos()[1:], hex(rig.mem[FACING])
    print(f"{key:5} hold40: {before[1:]} facing {hex(f0)} -> {now} facing {f1}", repr(rig.textbox()), flush=True)
    rig.screenshot(f"stall_{key}")
    if rig.textbox():
        for _ in range(4):
            rig.ctl.press("b")
            rig.ctl.wait(20)
# the io path road uses, for contrast
before = rig.pos()
rig.io.press("left", hold=8, release=8)
rig.ctl.wait(40)
print("io.press left:", before[1:], "->", rig.pos()[1:], "text:", repr(rig.textbox()), flush=True)
print("final", rig.pos(), flush=True)
