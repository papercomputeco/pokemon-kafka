"""At the conveyor's B4 landing (20,15): which directions move, and what is on screen?"""

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/seafoam_b3_surfing.state", settle_on_boot=False)
print("start", rig.pos(), "text", repr(rig.textbox()), flush=True)
rig.screenshot("b4_landing_0")
for key in ("down", "left", "right", "up", "down"):
    before = rig.pos()
    rig.io.press(key, hold=16, release=16)
    rig.ctl.wait(50)
    print(f"{key:5}: {before[1:]} -> {rig.pos()[1:]} text={rig.textbox()!r}", flush=True)
    rig.screenshot(f"b4_landing_{key}")
    for _ in range(3):
        rig.ctl.press("b")
        rig.ctl.wait(20)
print("final", rig.pos(), flush=True)
