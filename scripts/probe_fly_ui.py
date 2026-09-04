"""Teach HM02 to an ABLE member, then measure the FLY town-map screen: rows, cursor, names."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/fly_taught.state", settle_on_boot=True)
print("start", rig.pos(), "party", [f"{n}L{lv}" for n, lv, _ in rig.party()], flush=True)
if rig.knows_move("FLY") is None:
    sys.exit(2)
# "PIDGEOT can't FLY here." indoors: leave through the house door (2,7) first.
print("walk to (2,6):", rig.walk(188, {(2, 6)}, battle=rig.battle), rig.pos(), flush=True)
for _ in range(3):
    if rig.pos()[0] != 188:
        break
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(60)
print("outside:", rig.pos(), flush=True)
rig.bank("fly_taught_outside")
flyer = rig.party()[rig.knows_move("FLY")][0]
ok = rig.use_field_move("FLY", species=flyer)
rig.ctl.wait(60)
print("use FLY ->", ok, "| textbox:", repr(rig.textbox()), flush=True)
rig.screenshot("fly_map_0")
rows = [(i, t) for i, t in rig.menu_rows(0, 18) if t.strip()]
print("rows:", rows, "| cursor reg:", rig.mem[qm.ADDR_MENU_CUR], flush=True)
for i, key in enumerate(("down", "down", "up", "right", "left")):
    rig.ctl.press(key)
    rig.ctl.wait(30)
    rows = [(r, t) for r, t in rig.menu_rows(0, 18) if t.strip()]
    print(f"after {key}: rows {rows} cursor {rig.mem[qm.ADDR_MENU_CUR]} pos {rig.pos()}", flush=True)
    rig.screenshot(f"fly_map_{i + 1}")
for _ in range(6):
    rig.ctl.press("b")
    rig.ctl.wait(25)
print("final", rig.pos(), flush=True)
