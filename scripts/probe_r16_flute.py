"""Play the POKe FLUTE at Route 16's sleeper from (27,10), reading the menus at each stage: the
wake-up is the position of the body and the region afterwards, not the menu having been walked.
Boots fly_won-27.state (27,27,10), the sleeper at (26,10).
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
import road  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/fly_won-27.state", live_label="probe — Route 16 flute at the sleeper")
io = rig.io
for _ in range(4):
    io.press("b")
    io.wait(20)
flute = [n for n, _q in rig.bag_named() if "FLUTE" in n.upper()]
print("start", rig.pos(), "bodies", sorted(rig.bodies()), "bag flute:", flute, "bag size", len(rig.bag()), flush=True)
before = len(road.reachable(rig.truth, rig.pairs, 27, rig.pos()[1:], rig.bodies()))
print("region before:", before, flush=True)
io.press("left")
io.wait(25)
print("talk left ->", repr(rig.talk("left")), flush=True)
io.press("start")
io.wait(60)
print("START menu rows:", rig.menu_rows(), flush=True)
for _ in range(6):
    io.press("b")
    io.wait(25)
# walk the ITEM list by hand first, dumping the window each press, to see where the flute is drawn
io.press("start")
io.wait(60)
rows = rig.menu_rows()
item_row = next((i for i, t in rows if "ITEM" in t.upper()), None)
anchor = next((i for i, t in rows if "DEX" in t.upper()), None)
print("ITEM row", item_row, "anchor", anchor, flush=True)
if item_row is not None and rig.start_menu_cursor_to((item_row - anchor) // 2):
    io.press("a")
    io.wait(110)
    from quartermaster import ADDR_MENU_CUR  # noqa: E402

    for i in range(26):
        cur = io.read(ADDR_MENU_CUR)
        shown = [(r, rig.window_row(r).strip()) for r in range(18) if rig.window_row(r).strip()]
        print(f"  press {i}: cursor {cur} rows {shown}", flush=True)
        if any("FLUTE" in t.upper() for _r, t in shown):
            print("  FLUTE is on screen at rows", [r for r, t in shown if "FLUTE" in t.upper()], flush=True)
        io.press("down")
        io.wait(18)
for _ in range(8):
    io.press("b")
    io.wait(25)
ok = rig.use_item("POKe FLUTE", face="left")
print("use_item ->", ok, "text now:", repr(rig.textbox()), "pos", rig.pos(), flush=True)
for i in range(12):
    io.wait(60)
    if io.read(ADDR_IN_BATTLE):
        print("  a battle opened; fighting", flush=True)
        rig.battle()
        break
    io.press("a")
    io.wait(40)
print("after: text", repr(rig.textbox()), "bodies", sorted(rig.bodies()), "pos", rig.pos(), flush=True)
after = len(road.reachable(rig.truth, rig.pairs, 27, rig.pos()[1:], rig.bodies()))
print("region after:", after, flush=True)
rig.finish(outcome=f"probe r16 flute: use_item={ok} region {before}->{after}", goals="wake the sleeper")
