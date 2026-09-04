"""East-hole passage: 1F (25,3) -> B1, push (22,6) onto (23,6), fall to B2, up into (22,6), fall to B3, stair."""

import json
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import road  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/seafoam_1f_str.state", settle_on_boot=True)
truth = json.load(open("references/rom_truth.json"))


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def press_until(key, want_map, tries=3, wait=80):
    for _ in range(tries):
        if rig.pos()[0] == want_map:
            return True
        drain()
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(wait)
    drain()
    return rig.pos()[0] == want_map


print("start", rig.pos(), flush=True)
print("1F: walk to (25,4):", rig.walk(192, {(25, 4)}, battle=rig.battle), rig.pos(), flush=True)
print("up the (25,3) stair:", press_until("up", 159), rig.pos(), flush=True)
if rig.pos()[0] != 159:
    sys.exit(2)
rig.bank("b1_east_region")
drain()
who = rig.knows_move("STRENGTH")
print("activate:", rig.use_field_move("STRENGTH", species=rig.party()[who][0]), flush=True)
for _ in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(40)
drain()
w = rig.walk(159, {(21, 6)}, battle=rig.battle)
print("B1: walk to (21,6):", w, rig.pos(), "sprites", sorted(rig.bodies()), flush=True)
drain()
rig.io.press("right", hold=4, release=8)
rig.ctl.wait(20)
drain()
rig.io.press("right", hold=16, release=16)
rig.ctl.wait(90)
drain()
print("after the push:", rig.pos(), flush=True)
rig.screenshot("b1_east_push")
if rig.pos()[0] == 160:
    rig.bank("b2_east_after_drop")
    w2 = rig.walk(160, {(22, 7)}, battle=rig.battle)
    print("B2: sprites", sorted(rig.bodies()), "| walk to (22,7):", w2, rig.pos(), flush=True)
    print("up into the (22,6) hole:", press_until("up", 161), rig.pos(), flush=True)
    rig.screenshot("b3_after_east_hole")
if rig.pos()[0] == 161:
    mp, x, y = rig.pos()
    region = road.reachable(truth, set(), 161, (x, y))
    print(f"B3 region from {(x, y)}: {len(region)} cells; (25,13) in it? {(25, 13) in region}", flush=True)
    rig.bank("b3_east_region")
    print("walk to (25,13):", rig.walk(161, {(25, 13)}, battle=rig.battle), rig.pos(), flush=True)
    print("down the (25,14) stair:", press_until("down", 160), rig.pos(), flush=True)
    if rig.pos()[0] == 160:
        rig.bank("b2_east_pocket")
        print("*** B2 EAST POCKET ***", rig.pos(), flush=True)
print("final", rig.pos(), repr(rig.textbox()), flush=True)
