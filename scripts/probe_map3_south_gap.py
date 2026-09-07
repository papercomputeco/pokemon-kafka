"""Map 3's tree line (row 28) has a two-cell gap at (16,28)/(17,28) that opens onto tiles 0x55/0x56,
which the extracted ledge table does not list. What happens when the player steps down there?
Boots fuchsia_west_entry.state (3,0,18), walks to the gap, presses down, reads position and text.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/fuchsia_west_entry.state", live_label="probe — map 3 south gap tiles 0x55/0x56")
io = rig.io
for _ in range(4):
    io.press("b")
    io.wait(20)
print("start", rig.pos(), flush=True)
for stand in ((16, 28), (17, 28)):
    r = rig.walk(3, {stand}, cap=400)
    print(f"walk to {stand} -> {r} at {rig.pos()}", flush=True)
    if rig.pos()[1:] != stand:
        continue
    for k in ("down", "down"):
        before = rig.pos()
        io.press(k, hold=15, release=15)
        io.wait(90)
        if io.read(ADDR_IN_BATTLE):
            rig.battle()
        print(f"  {k}: {before} -> {rig.pos()}  text={rig.textbox()!r}", flush=True)
    if rig.pos()[1:] != stand:
        print("  moved off the gap; where the step leads:", rig.pos(), flush=True)
        # try to come back up (a ledge is one-way; a plain tile is not)
        io.press("up", hold=15, release=15)
        io.wait(90)
        print("  up again ->", rig.pos(), flush=True)
        break
rig.finish(outcome="probe map 3 south gap", goals="0x55/0x56")
