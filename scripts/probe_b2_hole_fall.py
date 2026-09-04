"""From B2 (19,7): step UP into the hole (19,6) and measure where B3 puts us, then walk toward the (25,14) stair."""

import json
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import road  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/b2_after_b1_drop.state", settle_on_boot=False)
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


print("start", rig.pos(), flush=True)
for _ in range(3):
    if rig.pos()[0] != 160:
        break
    rig.io.press("up", hold=16, release=16)
    rig.ctl.wait(90)
    drain()
print("after the hole:", rig.pos(), repr(rig.textbox()), flush=True)
rig.screenshot("b3_after_hole")
if rig.pos()[0] == 161:
    mp, x, y = rig.pos()
    region = road.reachable(truth, set(), 161, (x, y))
    has = ((25, 14) in region, (23, 12) in region)
    print(f"B3 land region from {(x, y)}: {len(region)} cells; (25,14)/(23,12) in it: {has}", flush=True)
    rig.bank("b3_after_hole")
    if (25, 14) in region:
        print("walk to (25,13):", rig.walk(161, {(25, 13)}, battle=rig.battle), rig.pos(), flush=True)
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(60)
        print("into the stair:", rig.pos(), flush=True)
        if rig.pos()[0] == 160:
            rig.bank("b2_east_pocket")
            print("*** B2 EAST POCKET ***", rig.pos(), flush=True)
print("final", rig.pos(), flush=True)
