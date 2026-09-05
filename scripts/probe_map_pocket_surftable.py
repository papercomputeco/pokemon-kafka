"""Map Route 20's (map 31) surfable region around the baton by live behaviour, not by tile id.

The lesson in surf-is-armed-and-the-water-is-not-a-tile-id.md is exactly this: the game refuses
surf into a same-id tile one way and allows it the other. So the only ground truth is what the
body actually does. From the baton cell we press along each axis until the game refuses, record
the farthest reached cell and the tile+sentence of the wall, then from each reached cell try the
two perpendicular turns. Anything that reaches x=0 (west edge) or is adjacent to walkable land is
the escape.
"""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/m31_manual.state"
rig = Rig(STATE, settle_on_boot=True)
print("start", rig.pos(), "| surfer:", rig.knows_move("SURF"), "| party lead:", rig.party()[0], flush=True)
mp0, x0, y0 = rig.pos()
assert mp0 == 31, "not on Route 20"


def clean_text():
    for _ in range(5):
        rig.ctl.press("b")
        rig.ctl.wait(15)
    return rig.textbox()


def press(key, hold=30):
    if rig.mem[qm.ADDR_IN_BATTLE]:
        rig.battle()
        return rig.pos()
    before = rig.pos()
    rig.ctl.press(key)
    rig.ctl.wait(hold)
    if rig.mem[qm.ADDR_IN_BATTLE]:
        rig.battle()
    return before, rig.pos()


def surf_axis(key, max_steps=24):
    """Press along one axis until the game refuses; return the farthest cell and the wall."""
    last = rig.pos()
    wall = None
    for i in range(max_steps):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            break
        before = rig.pos()
        rig.ctl.press(key)
        rig.ctl.wait(30)
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
        after = rig.pos()
        if after != before:
            last = after
        else:
            said = clean_text()
            wall = (before, after, said)
            break
        clean_text()
    return last, wall


AXES = [("up", "N"), ("down", "S"), ("left", "W"), ("right", "E")]
frontier = [(x0, y0)]
reached = set()
walls = []

# Phase 1: from the baton, run each axis to its wall.
from_cell = (x0, y0)
print(f"\n=== From baton {from_cell} ===", flush=True)
for key, name in AXES:
    last, wall = surf_axis(key)
    reached.add((last[1], last[2]))
    if wall:
        b, a, said = wall
        walls.append(f"{name} wall from {b[1:]}: stopped at {a[1:]} | {said!r}")
        print(f"  {name}: reached {last[1:]}  wall={said!r}", flush=True)
    else:
        print(f"  {name}: reached {last[1:]} (no wall / map edge)", flush=True)
    rig.screenshot(f"pool_{name}_far")
    # steer back to the baton by pressing the opposite axis
    opp = {"up": "down", "down": "up", "left": "right", "right": "left"}[key]
    surf_axis(opp)
    clean_text()


# Phase 2: from each reached frontier cell, try the perpendicular axes (turns), one step at a time.
def opp(k):
    return {"up": "down", "down": "up", "left": "right", "right": "left"}[k]


print(f"\n=== Turns from frontier {sorted(reached)} ===", flush=True)
for cx, cy in sorted(reached):
    if (cx, cy) == (x0, y0):
        continue
    # steer to this cell: it is along an axis from the baton
    key = "up" if cy < y0 else ("down" if cy > y0 else ("left" if cx < x0 else "right"))
    surf_axis(key)
    clean_text()
    here = rig.pos()
    print(f"  at {here[1:]}", flush=True)
    for k2, n2 in AXES:
        if k2 in (key, opp(key)):
            continue  # already along this axis
        last, wall = surf_axis(k2, max_steps=24)
        reached.add((last[1], last[2]))
        if wall:
            print(f"    turn {n2} from {here[1:]}: reached {last[1:]} wall={wall[2]!r}", flush=True)
        else:
            print(f"    turn {n2} from {here[1:]}: reached {last[1:]} (edge)", flush=True)
        surf_axis(opp(k2))
        clean_text()

print("\n=== RESULT ===")
print("reached set:", sorted(reached))
xs = [c for c, r in reached]
ys = [r for c, r in reached]
print("x range:", min(xs), "..", max(xs), " y range:", min(ys), "..", max(ys))
print("touches WEST edge x=0?", any(c == 0 for c in reached))
print("touches EAST edge x=99?", any(c == 99 for c in reached))
print("walls:")
for w in walls:
    print("  ", w)
rig.screenshot("pocket_final")
print("final", rig.pos())
