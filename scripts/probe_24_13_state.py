"""From secret_key_out.state, test the state of door (24,13) on 165."""

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

# Walk to (24,14)
print("walk to (24,14):", rig.walk(165, {(24, 14)}, battle=rig.battle), rig.pos(), flush=True)

# Try stepping to (24,13)
if rig.pos()[1:] == (24, 14):
    before = rig.pos()
    rig.io.press("up", hold=16, release=16)
    rig.ctl.wait(40)
    drain()
    print("step (24,14) up:", rig.pos() != before, rig.pos(), flush=True)
    print("text:", repr(rig.textbox()), flush=True)

# Try walking to (16,6) to test (16,7)
print("walk to (16,6):", rig.walk(165, {(16, 6)}, battle=rig.battle), rig.pos(), flush=True)
if rig.pos()[1:] == (16, 6):
    before = rig.pos()
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(40)
    drain()
    print("step (16,6) down:", rig.pos() != before, rig.pos(), flush=True)
    print("text:", repr(rig.textbox()), flush=True)

print("final", rig.pos(), flush=True)
