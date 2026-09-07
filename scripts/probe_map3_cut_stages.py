"""The field-Cut flow on map 3's tree at (11,28) did nothing (probe_map3_cut). Read the screen at
each stage of the flow - after START, after POKeMON, after picking the lead, after the submenu -
so the refusal is a sentence, not a guess. Boots fuchsia_west_entry.state (3,0,18).
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE, ADDR_MENU_CUR  # noqa: E402

rig = Rig("data/local_runs/roster-bench/fuchsia_west_entry.state", live_label="probe — map 3 cut, stage by stage")
io = rig.io
for _ in range(4):
    io.press("b")
    io.wait(20)
print("start", rig.pos(), flush=True)
r = rig.walk(3, {(11, 27)}, cap=500)
print("walk to (11,27) ->", r, rig.pos(), flush=True)
if io.read(ADDR_IN_BATTLE):
    rig.battle()
io.press("down")
io.wait(30)


def screen(tag):
    rows = [rig.window_row(i).strip() for i in range(18)]
    print(f"  [{tag}] menu_cur={io.read(ADDR_MENU_CUR)} rows: {[r for r in rows if r]}", flush=True)


screen("facing the tree")
io.press("start")
io.wait(60)
screen("after START")
for _ in range(6):
    if io.read(ADDR_MENU_CUR) == 1:
        break
    io.press("down" if io.read(ADDR_MENU_CUR) < 1 else "up")
    io.wait(20)
io.press("a")
io.wait(60)
screen("after POKeMON")
io.press("a")
io.wait(60)
screen("after picking the lead")
io.press("a")
io.wait(90)
screen("after the first submenu row")
for _ in range(4):
    io.press("a")
    io.wait(60)
screen("after more A presses")
for _ in range(6):
    io.press("b")
    io.wait(25)
before = rig.pos()
io.press("down", hold=15, release=15)
io.wait(60)
print("step down:", before, "->", rig.pos(), flush=True)
rig.finish(outcome="probe map 3 cut stages", goals="what the menu says")
