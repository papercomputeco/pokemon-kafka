"""From secret_key_out.state, try exiting the mansion via the left side."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm
from expedition_rig import Rig

rig = Rig("data/local_runs/roster-bench/secret_key_out.state", settle_on_boot=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


print("start", rig.pos(), flush=True)

# Step to (20,16)
drain()
rig.walk(165, {(20, 16)}, battle=rig.battle)
print("at (20,16):", rig.pos(), flush=True)

# Test left-side doors
for stand, face in (((16, 6), "down"), ((15, 6), "down")):
    drain()
    w = rig.walk(165, {stand}, battle=rig.battle)
    print(f"walk to {stand}: {w} {rig.pos()}", flush=True)
    if rig.pos()[1:] == stand:
        before = rig.pos()
        rig.io.press(face, hold=16, release=16)
        rig.ctl.wait(40)
        drain()
        print(f"  door {stand} {face}: moved={rig.pos() != before} text={rig.textbox()!r}", flush=True)
        if rig.pos() != before:
            # door is open, step back
            rig.walk(165, {stand}, battle=rig.battle)

# Try to walk to left exit (4,27) or (5,27)
if rig.pos()[0] == 165:
    for goal in [(5, 27), (6, 27), (7, 27)]:
        drain()
        w = rig.walk(165, {goal}, battle=rig.battle)
        print(f"walk to {goal}: {w} {rig.pos()}", flush=True)
        if rig.pos()[1:] == goal:
            before = rig.pos()
            rig.io.press("down", hold=16, release=16)
            rig.ctl.wait(70)
            drain()
            print(f"step down from {goal}: {rig.pos()}", flush=True)
            if rig.pos()[0] == 8:
                print("*** ON CINNABAR ***", flush=True)
                break

print("final", rig.pos(), flush=True)
