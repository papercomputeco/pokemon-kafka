"""Is Route 20's divider (0x3a at x=62 rows 10-16, 0x32 rows 2-9) a wall Surf refuses, or water?

Nobody has stood on one in 28 days of telemetry, the collision flag reads 0 for water AND walls,
and every 'Cinnabar is sealed' verdict rests on assuming it is solid. This asks the game: the
verdict is the position after the step and the sentence on screen if it refuses.
"""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/merged_on_31.state"
rig = Rig(STATE, settle_on_boot=True)
print("start", rig.pos(), "| surfer:", rig.knows_move("SURF"), flush=True)
assert rig.pos()[0] == 31, "not on Route 20"


def surf_toward(tx, ty, cap=200):
    """Greedy straight-line surfing; battles go to the rig's handler. Returns the cell reached."""
    stalls = 0
    axis_first = "x"
    for _ in range(cap):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        mp, x, y = rig.pos()
        if (x, y) == (tx, ty) or mp != 31:
            return (mp, x, y)
        dx, dy = tx - x, ty - y
        keys = []
        if dx:
            keys.append("left" if dx < 0 else "right")
        if dy:
            keys.append("down" if dy > 0 else "up")
        if axis_first == "y":
            keys.reverse()
        rig.ctl.press(keys[0])
        rig.ctl.wait(24)
        if rig.pos() == (mp, x, y):
            stalls += 1
            if stalls >= 3:
                axis_first = "y" if axis_first == "x" else "x"
                stalls = 0
        else:
            stalls = 0
    return rig.pos()


for (tx, ty), tile in (((63, 14), "0x3a"), ((63, 4), "0x32")):
    reached = surf_toward(tx, ty)
    print(f"toward {(tx, ty)}: reached {reached}", flush=True)
    for _ in range(3):  # three honest presses into the divider
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
        before = rig.pos()
        rig.ctl.press("left")
        rig.ctl.wait(40)
        after = rig.pos()
        said = rig.textbox()
        print(f"  LEFT into {tile} from {before[1:]}: moved={after != before} now={after[1:]}", said, flush=True)
        rig.screenshot(f"divider_{tile}_{_}")
        for _b in range(4):
            rig.ctl.press("b")
            rig.ctl.wait(20)
print("final", rig.pos(), flush=True)
