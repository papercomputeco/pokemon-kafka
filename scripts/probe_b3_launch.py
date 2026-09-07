"""Seafoam B3 (161): is SURF launched only from a 0x15 tile facing water, and where does the water
carry the surfer? Boots b3_east_landing.state (banked at (161,25,13) by the crossing probe), gets to
B3 via the (25,14) stairs if needed, walks to the 0x15 tile at (23,9), faces the water at (23,10),
arms, then rides the water step by step reporting the position after each press.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/b3_east_landing.state", live_label="probe — B3 launch tile and current")
io = rig.io
for _ in range(4):
    io.press("b")
    io.wait(20)
print("start", rig.pos(), "text", repr(rig.textbox()), flush=True)
if rig.pos()[0] == 160:
    print("160 -> 161 via (25,14):", rig.warp(160, 25, 14), "at", rig.pos(), flush=True)
if rig.pos()[0] != 161:
    print("NOT ON B3 — probe invalid", rig.pos(), flush=True)
    rig.finish(outcome="probe b3 launch: not on 161", goals="launch?")
    sys.exit(1)
for stand, face in (((23, 12), "up"), ((23, 9), "down")):
    r = rig.walk(161, {stand}, cap=300)
    print(f"walk to {stand} -> {r} at {rig.pos()}", flush=True)
    if rig.pos()[1:] != stand:
        continue
    io.press(face)
    io.wait(30)
    if io.read(ADDR_IN_BATTLE):
        rig.battle()
    before = rig.pos()
    armed = rig._arm_surf()
    print(f"ARM at {stand} facing {face}: {armed}; {before} -> {rig.pos()} text={rig.textbox()!r}", flush=True)
    if armed:
        break
if rig.pos()[0] == 161 and rig.pos()[1:] == (23, 10):
    print("afloat; riding west along row 11 to (15,8), then landing UP onto the 0x15 at (15,7)", flush=True)
    ride = ["down"] + ["left"] * 8 + ["up"] * 3 + ["up"]
    for k in ride:
        before = rig.pos()
        io.press(k, hold=15, release=15)
        io.wait(60)
        if io.read(ADDR_IN_BATTLE):
            rig.battle()
        now = rig.pos()
        print(f"  {k}: {before} -> {now}  text={rig.textbox()!r}", flush=True)
        if now[0] != 161:
            print("  carried to map", now[0], "at", now[1:], flush=True)
            break
    if rig.pos()[1:] == (15, 7):
        print("LANDED on the 0x15 at (15,7): water<->land through 0x15 confirmed both ways", flush=True)
        r = rig.walk(161, {(5, 12)}, cap=400)
        print("walk (15,7) -> (5,12):", r, "at", rig.pos(), flush=True)
    elif rig.pos()[1:] == (15, 8):
        # also try a plain-floor landing for contrast: (14,8)? no - try left onto x=13 if land
        io.press("left", hold=15, release=15)
        io.wait(60)
        print("  left from (15,8):", rig.pos(), flush=True)
rig.finish(outcome="probe b3 launch", goals="161 launch + landing")
