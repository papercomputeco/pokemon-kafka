"""From mansion_fell_165.state, test all known doors on 165 from inside and outside the pocket."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm
from expedition_rig import Rig

rig = Rig("data/local_runs/roster-bench/mansion_fell_165.state", settle_on_boot=True)


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

# Test from inside the pocket: (20,18) and (21,18) facing UP toward (20,17)/(21,17)
for stand in ((20, 18), (21, 18)):
    drain()
    rig.walk(165, {stand}, battle=rig.battle)
    if rig.pos()[1:] != stand:
        print(f"cannot reach {stand}", flush=True)
        continue
    before = rig.pos()
    rig.io.press("up", hold=16, release=16)
    rig.ctl.wait(40)
    drain()
    print(f"pocket door {stand} UP -> moved={rig.pos() != before} now {rig.pos()[1:]}", flush=True)

# Test from outside: (20,16) and (21,16) facing DOWN toward (20,17)/(21,17)
for stand in ((20, 16), (21, 16)):
    drain()
    rig.walk(165, {stand}, battle=rig.battle)
    if rig.pos()[1:] != stand:
        print(f"cannot reach {stand} from outside", flush=True)
        continue
    before = rig.pos()
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(40)
    drain()
    print(f"pocket door {stand} DOWN -> moved={rig.pos() != before} now {rig.pos()[1:]}", flush=True)

# Test (16,7) and (24,13)
for stand, face in (((16, 6), "down"), ((24, 12), "down")):
    drain()
    rig.walk(165, {stand}, battle=rig.battle)
    if rig.pos()[1:] != stand:
        print(f"cannot reach {stand}", flush=True)
        continue
    before = rig.pos()
    rig.io.press(face, hold=16, release=16)
    rig.ctl.wait(40)
    drain()
    print(f"door {stand} {face} -> moved={rig.pos() != before} now {rig.pos()[1:]}", flush=True)

print("final", rig.pos(), flush=True)
