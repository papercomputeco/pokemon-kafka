"""Saffron -> Route 7 on a row that reaches the gate -> through gate 76 -> Celadon. Bank there."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/strength_route16-10.state"
rig = Rig(STATE, settle_on_boot=True)


def drain(limit=12):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def through(key, want_map, tries=4):
    for _ in range(tries):
        if rig.pos()[0] == want_map:
            return True
        drain()
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(70)
    drain()
    return rig.pos()[0] == want_map


print("start", rig.pos(), flush=True)
if rig.pos()[0] == 10:
    w = rig.walk(10, {(0, 17), (0, 18), (1, 17)}, battle=rig.battle)
    print("Saffron: walk to (0,17):", w, rig.pos(), flush=True)
    print("west into Route 7:", through("left", 18), rig.pos(), flush=True)
if rig.pos()[0] == 18:
    w = rig.walk(18, {(19, 9), (19, 10)}, battle=rig.battle)
    print("Route 7: beside the east door:", w, rig.pos(), flush=True)
    print("into gate 76:", through("left", 76), rig.pos(), flush=True)
if rig.pos()[0] == 76:
    print("gate: walk to (1,3)/(1,4):", rig.walk(76, {(1, 3), (1, 4)}, battle=rig.battle), rig.pos(), flush=True)
    print("out the west door:", through("left", 18), rig.pos(), flush=True)
if rig.pos()[0] == 18 and rig.pos()[1] <= 11:
    w = rig.walk(18, {(0, 2), (0, 3), (1, 2), (1, 3)}, battle=rig.battle)
    print("Route 7 west: to the Celadon edge:", w, rig.pos(), flush=True)
    print("into Celadon:", through("left", 6), rig.pos(), flush=True)
if rig.pos()[0] == 6:
    rig.bank("strength_celadon")
    print("*** CELADON ***", rig.pos(), flush=True)
print("final", rig.pos(), repr(rig.textbox()), flush=True)
