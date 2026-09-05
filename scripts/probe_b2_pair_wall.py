"""Is B2's (25,4)->(25,5) step a real wall (tile pair 0x05/0x20), as the static model says?"""

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/seafoam_loop_stuck_6.state", settle_on_boot=True)
print("start", rig.pos(), "walk to (25,4):", rig.walk(160, {(25, 4)}, battle=rig.battle), rig.pos(), flush=True)
for _ in range(3):
    before = rig.pos()
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(40)
    print(f"  DOWN from {before[1:]}: now {rig.pos()[1:]} said {rig.textbox()!r}", flush=True)
rig.screenshot("b2_pair_wall")
