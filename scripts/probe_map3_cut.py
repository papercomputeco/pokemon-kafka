"""Are map 3's 0x50 trees cuttable? The leg's cut at (25,9) from (24,9) was refused (run fwd_l12_70).
Boots fuchsia_west_entry.state (3,0,18); at each stand faces the tree, runs the field-Cut flow, and
reads the position and the text box; then tries to step through.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
import road  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/probe_strip-3.state", live_label="probe — map 3 x=10 tree column: cuttable?")
io = rig.io
for _ in range(4):
    io.press("b")
    io.wait(20)
print("start", rig.pos(), "lead moves:", rig.party()[0], "knows CUT idx:", rig.knows_move("CUT"), flush=True)
if rig.pos()[0] == 16:  # the bank settles onto Route 16's edge cell; cross back up into map 3
    print("cross 16 -> 3:", rig.cross(16, 3), "at", rig.pos(), flush=True)
if rig.pos()[0] != 3:
    print("NOT ON MAP 3 - probe invalid", rig.pos(), flush=True)
    rig.finish(outcome="probe map 3 cut: not on 3", goals="x=10 trees")
    sys.exit(1)
for stand, face in (((11, 35), "left"), ((11, 34), "left")):
    r = rig.walk(3, {stand}, cap=500)
    print(f"walk to {stand} -> {r} at {rig.pos()}", flush=True)
    if rig.pos()[1:] != stand:
        continue
    if io.read(ADDR_IN_BATTLE):
        rig.battle()
    io.press(face)
    io.wait(25)
    road.cut_facing(io, face)
    print(f"  after cut flow facing {face}: pos {rig.pos()} text={rig.textbox()!r}", flush=True)
    for _ in range(6):
        io.press("b")
        io.wait(25)
    before = rig.pos()
    io.press(face, hold=15, release=15)
    io.wait(60)
    print(f"  step {face}: {before} -> {rig.pos()}  text={rig.textbox()!r}", flush=True)
rig.finish(outcome="probe map 3 cut", goals="0x50 trees")
