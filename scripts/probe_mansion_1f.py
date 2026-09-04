"""Step from mansion floor 214 back up its (5,10) stair onto 165 and bank there for the survey."""

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/secret_key-165.state", settle_on_boot=True)
print("start", rig.pos(), flush=True)
if rig.pos()[0] == 214:
    rig.walk(214, {(5, 11)}, battle=rig.battle)
    for _ in range(3):
        if rig.pos()[0] == 165:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(70)
print("now", rig.pos(), flush=True)
if rig.pos()[0] == 165:
    rig.walk(165, {(5, 12), (6, 11), (4, 11)}, battle=rig.battle)
    rig.bank("mansion_1f")
    print("banked mansion_1f at", rig.pos(), flush=True)
