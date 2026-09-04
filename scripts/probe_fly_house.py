"""Route 16 to the Fly house, the measured way: Cut (34,9), the gate's UPPER doors, the house at (7,5).

The engine leg tried the gate's lower doors from the lower road twenty times. Static (bush cut):
(25,10) reaches (25,4) beside the upper east door (24,4) -> 186 -> its west doors (0,2)/(0,3) ->
27 (17,4)/(17,5) -> the house door (7,5) from (7,6). Bag engine first: the branch is at 20 stacks.
"""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/fly_house-186.state"
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


def step(key):
    drain()
    before = rig.pos()
    rig.io.press(key, hold=8, release=8)
    rig.ctl.wait(30)
    drain()
    return rig.pos() != before


def through(key, want_map):
    """A route-gate warp sits on the path tile in front of the wall (24,4 is 0x39, 23,4 is 0x4b):
    it fires when you press INTO the building from that tile, not when you step onto it."""
    for _ in range(3):
        if rig.pos()[0] == want_map:
            return True
        drain()
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(60)
    drain()
    return rig.pos()[0] == want_map


print("start", rig.pos(), "| bag stacks:", len(rig.bag()), flush=True)
if rig.bag_full():
    print("bag full -> make_room:", rig.make_room(), "| stacks now", len(rig.bag()), flush=True)
drain()
# The Snorlax that left (26,10) still occupies its sprite slot, so walk() calls the road east
# body-blocked. The cartridge lets us through: step past it by hand, then plan from there.
while rig.pos()[1] < 27 and step("right"):
    pass
print("past the phantom body:", rig.pos(), flush=True)
print("walk to (34,10):", rig.walk(27, {(34, 10)}, battle=rig.battle), rig.pos(), flush=True)
drain()
rig.io.press("up", hold=4, release=8)
rig.ctl.wait(20)
print("cut up:", rig.cut("up"), "| step up:", step("up"), rig.pos(), flush=True)
rig.screenshot("route16_after_cut")
print("walk to (25,4):", rig.walk(27, {(25, 4)}, battle=rig.battle), rig.pos(), flush=True)
rig.bank("route16_upper")
step("left")
print("through the upper east door:", through("left", 186), rig.pos(), flush=True)
if rig.pos()[0] == 186:
    print("gate: walk to (1,2):", rig.walk(186, {(1, 2), (1, 3)}, battle=rig.battle), rig.pos(), flush=True)
    step("left")
    print("through the upper west door:", through("left", 27), rig.pos(), flush=True)
    rig.screenshot("route16_upper_west")
if rig.pos()[0] == 27:
    w = rig.walk(27, {(7, 6)}, battle=rig.battle)
    print("walk to (7,6):", w, rig.pos(), flush=True)
    if rig.pos()[1:] == (7, 6):
        step("up")
        print("through the house door:", through("up", 188), rig.pos(), flush=True)
if rig.pos()[0] == 188:
    rig.bank("fly_house_inside")
    for body, stand, face in (((2, 3), (2, 4), "up"), ((6, 4), (5, 4), "right")):
        drain()
        print(f"walk to {stand}:", rig.walk(188, {stand}, battle=rig.battle), rig.pos(), flush=True)
        before = len(rig.bag())
        said = rig.talk(face)
        for _ in range(10):
            rig.ctl.press("a")
            rig.ctl.wait(35)
        drain()
        hms = [n for n, _ in rig.bag_named(full=True) if n.startswith("HM")]
        print(f"  body {body} said {said[:120]!r}; bag {before}->{len(rig.bag())}; HMs {hms}", flush=True)
        rig.screenshot(f"fly_house_talk_{body[0]}_{body[1]}")
        if any(n.startswith("HM02") for n in hms):
            rig.bank("fly_won_real")
            print("*** HM02 FLY IN THE BAG ***", rig.pos(), flush=True)
            break
print("final", rig.pos(), "HMs:", [n for n, _ in rig.bag_named(full=True) if n.startswith("HM")], flush=True)
