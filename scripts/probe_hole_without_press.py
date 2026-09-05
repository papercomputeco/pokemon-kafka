"""From mansion_catalog_end.state, go to 215 without pressing its switch, try to reach (16,13) and fall through."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm
from expedition_rig import Rig

rig = Rig("data/local_runs/roster-bench/mansion_catalog_end.state", settle_on_boot=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def stairs(mp, beside, key, want):
    drain()
    rig.walk(mp, set(beside), battle=rig.battle)
    for _ in range(3):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(70)
        drain()
    return rig.pos()[0] == want


print("start", rig.pos(), flush=True)

# 165 -> 214
print("165 -> 214:", stairs(165, [(5, 11)], "up", 214), rig.pos(), flush=True)

# 214 -> 215 via (6,1) or (7,10)
if rig.pos()[0] == 214:
    print(
        "214 -> 215:",
        stairs(214, [(6, 2), (7, 1)], "up", 215) or stairs(214, [(6, 10), (8, 10), (7, 11)], "down", 215),
        rig.pos(),
        flush=True,
    )

# On 215, walk to (16,13)
if rig.pos()[0] == 215:
    print("215 walk to (16,13):", rig.walk(215, {(16, 13)}, battle=rig.battle), rig.pos(), flush=True)
    if rig.pos()[1:] == (16, 13):
        before = rig.pos()
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
        print(f"hole without press: {before} -> {rig.pos()}", flush=True)
        # Test the pocket doors if we fell to 165
        if rig.pos()[0] == 165:
            for stand in ((20, 18), (21, 18)):
                drain()
                rig.walk(165, {stand}, battle=rig.battle)
                if rig.pos()[1:] == stand:
                    b = rig.pos()
                    rig.io.press("up", hold=16, release=16)
                    rig.ctl.wait(40)
                    drain()
                    print(f"  pocket door {stand} UP: moved={rig.pos() != b}", flush=True)

print("final", rig.pos(), flush=True)
