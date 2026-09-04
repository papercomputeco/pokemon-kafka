"""Pallet -> Route 21 -> Cinnabar by water: stand at (5,13), arm SURF facing down, surf south until map 8."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/all_hms_pallet.state"
rig = Rig(STATE, settle_on_boot=True)


def drain(limit=14):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def go(key, until, cap=200):
    refusals = 0
    for _ in range(cap):
        drain()
        p = rig.pos()
        if until(p):
            return True
        rig.io.press(key, hold=8, release=8)
        rig.ctl.wait(30)
        refusals = 0 if rig.pos() != p else refusals + 1
        if refusals >= 4:
            return False
    return until(rig.pos())


print("start", rig.pos(), "| surfer:", rig.knows_move("SURF"), flush=True)
print("walk to (5,13):", rig.walk(0, {(5, 13)}, battle=rig.battle), rig.pos(), flush=True)
drain()
rig.io.press("down", hold=4, release=8)
rig.ctl.wait(20)
print("arm surf facing the channel:", rig._arm_surf(), rig.pos(), flush=True)
print("south off Pallet:", go("down", lambda p: p[0] != 0, cap=12), rig.pos(), flush=True)
rig.screenshot("route21_entry")
if rig.pos()[0] == 32:
    rig.bank("route21_north")
    # straight down; on a refusal, sidestep within the channel and keep going
    for _ in range(40):
        if rig.pos()[0] != 32:
            break
        if go("down", lambda p: p[0] != 32, cap=60):
            break
        # Measured: the column crosses a land island at rows 24-25; the surfer lands on it and the
        # step back into the water below needs SURF armed again, from land, facing the water.
        mp, x, y = rig.pos()
        m = rig.truth["maps"][str(mp)]
        on_land = m["grid"][y][x] == "1"
        below_water = y + 1 < m["height"] and int(m["tiles"][y + 1][2 * x : 2 * x + 2], 16) in (0x14, 0x11)
        if on_land and below_water:
            drain()
            rig.io.press("down", hold=4, release=8)
            rig.ctl.wait(20)
            armed = rig._arm_surf()
            print("  on the island at", (x, y), "- re-armed SURF facing down:", armed, rig.pos(), flush=True)
            if not armed:
                rig.screenshot(f"route21_no_surf_{x}_{y}")
                break
            continue
        side = "right" if x < 10 else "left"
        print("  refused at", (x, y), repr(rig.textbox()), "- sidestep", side, flush=True)
        rig.screenshot(f"route21_refused_{x}_{y}")
        if not go(side, lambda p, x0=x: p[1] != x0, cap=3):
            other = "left" if side == "right" else "right"
            go(other, lambda p, x0=x: p[1] != x0, cap=3)
print("end:", rig.pos(), repr(rig.textbox()), flush=True)
rig.screenshot("route21_end")
if rig.pos()[0] == 8:
    rig.bank("cinnabar")
    print("*** CINNABAR ISLAND ***", rig.pos(), flush=True)
else:
    rig.bank("route21_stuck")
