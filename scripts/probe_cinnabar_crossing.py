"""The Route 20 crossing, one tile at a time, judged by position: arrival water -> island (row 4)
-> the (58,9) cave door from the pond above it -> straight back out onto the south shore -> the
Cinnabar-side water -> map 8. Every tile is a measured fact (journal, 2026-09-04); every verdict is RAM.
"""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/merged_on_31.state"
rig = Rig(STATE, settle_on_boot=True)
print("start", rig.pos(), "| surfer:", rig.knows_move("SURF"), flush=True)


def drain(limit=14):
    """A battle ends before its EXP pages do, and a page blocks every step. Empty the screen."""
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def step(key):
    """One tile, or a refusal. Returns (moved, position)."""
    drain()
    before = rig.pos()
    rig.io.press(key, hold=8, release=8)
    rig.ctl.wait(30)
    drain()
    return rig.pos() != before, rig.pos()


def run(key, until, cap=120):
    """Step ``key`` until ``until(pos)`` or the game refuses three times in a row."""
    refusals = 0
    for _ in range(cap):
        if until(rig.pos()):
            return True
        moved, _p = step(key)
        refusals = 0 if moved else refusals + 1
        if refusals >= 3:
            return until(rig.pos())
    return until(rig.pos())


# 1. west along row 4 to the island
ok = run("left", lambda p: p[1] <= 61)
print("1. island landing:", ok, rig.pos(), flush=True)
rig.screenshot("island_landing")
assert ok, f"did not land on the island; at {rig.pos()} said {rig.textbox()!r}"

# 2. to the cell above the pond, face down, arm SURF, down the pond to the door
print("2. walk to (58,5):", rig.walk(31, {(58, 5)}, battle=rig.battle), rig.pos(), flush=True)
drain()
rig.io.press("down", hold=4, release=8)
rig.ctl.wait(20)
print("   arm surf facing the pond:", rig._arm_surf(), rig.pos(), flush=True)
ok = run("down", lambda p: p[0] != 31 or p[2] >= 9, cap=12)
print("   pond -> door:", ok, rig.pos(), flush=True)
rig.screenshot("after_door")

# 3. through the door and straight back out onto the south side
if rig.pos()[0] == 192:
    print("3. inside Seafoam at", rig.pos()[1:], "- stepping back out", flush=True)
    run("down", lambda p: p[0] == 31, cap=6)
    print("   back on 31 at", rig.pos(), flush=True)
    rig.screenshot("exit_south")
if rig.pos()[0] == 31 and rig.pos()[2] == 9:
    step("down")
    print("   off the door:", rig.pos(), flush=True)
if rig.pos()[0] == 31 and rig.pos()[2] >= 10:
    rig.bank("island_south")

# 4. from the south shore into the Cinnabar water and west to x=0
if rig.pos()[0] == 31 and rig.pos()[2] >= 10:
    print("4. walk to (59,11):", rig.walk(31, {(59, 11)}, battle=rig.battle), rig.pos(), flush=True)
    drain()
    rig.io.press("down", hold=4, release=8)
    rig.ctl.wait(20)
    print("   arm surf facing Cinnabar water:", rig._arm_surf(), rig.pos(), flush=True)
    run("down", lambda p: p[2] >= 12, cap=4)
    print("   in the water:", rig.pos(), flush=True)
    ok = run("left", lambda p: p[0] != 31, cap=160)
    if not ok:  # a rock on this row: drop a row and keep going
        for row in (13, 14, 15, 16):
            run("down", lambda p, r=row: p[2] >= r, cap=3)
            ok = run("left", lambda p: p[0] != 31, cap=160)
            if ok:
                break
    print("   west:", ok, rig.pos(), "said:", repr(rig.textbox()), flush=True)
    rig.screenshot("cinnabar_arrival" if ok else "stuck_west")
    rig.bank("cinnabar_arrival" if ok else "cinnabar_side_stuck")
    if ok:
        print("*** CINNABAR:", rig.pos(), "***", flush=True)
print("final", rig.pos(), flush=True)
