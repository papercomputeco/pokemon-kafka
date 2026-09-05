"""Step-by-step deposit of one bag item into the Center PC's item storage, every screen dumped.

Measured 2026-09-04 at Cinnabar's Center: pc_store_item reported 'could not store' twice while the bag lost the
S.S.TICKET and the SECRET KEY -- the item list scrolls, and a text-matched cursor is the wrong tool for it.
This drives the same menus by the bag index (cursor 0xCC26 + scroll 0xCC36) and prints what each press shows."""

import subprocess
import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/lab_pc_stored.state"
NAME = sys.argv[2] if len(sys.argv) > 2 else "TM27 FISSURE"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=False)


def rows(tag):
    print(f"  [{tag}] idx={rig.list_index()} rows={rig.menu_rows()}", flush=True)


print("start", rig.pos(), "bag", rig.bag_named(full=True), flush=True)
spot = rig.center_pc(rig.pos()[0])
print("pc spot", spot, "approach", rig.approach({spot[0]}), rig.pos(), flush=True)
rig.ctl.press(spot[1])
rig.ctl.wait(25)
for i in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(55)
    rows(f"a{i}")
    if rig.menu_rows():
        break
own = next(
    (t for _i, t in rig.menu_rows() if "PC" in t.upper() and "BILL" not in t.upper() and "OAK" not in t.upper()), None
)
print("own pc entry:", own, "choose:", rig.menu_choose(own) if own else None, flush=True)
rows("after own")
print("advance to DEPOSIT:", rig.advance_text("DEPOSIT"), flush=True)
rows("deposit menu")
print("choose DEPOSIT ITEM:", rig.menu_choose("DEPOSIT ITEM"), flush=True)
rig.ctl.wait(40)
rows("item list")
names = [n for n, _q in rig.bag_named(full=True)]
idx = names.index(NAME) if NAME in names else -1
print("bag index of", NAME, "=", idx, flush=True)
before = len(rig.bag())
if idx >= 0:
    print("cursor:", rig.menu_cursor_to(idx), "idx now", rig.list_index(), flush=True)
    rows("on item")
    rig.ctl.press("a")
    rig.ctl.wait(45)
    rows("after A (quantity?)")
    rig.ctl.press("a")
    rig.ctl.wait(60)
    rows("after A (confirm)")
    print("bag", len(rig.bag()), "was", before, rig.bag_named(full=True), flush=True)
for _ in range(8):
    rig.ctl.press("b")
    rig.ctl.wait(25)
rig.ctl.wait(40)
print("final bag", len(rig.bag()), rig.bag_named(full=True), "pos", rig.pos(), flush=True)
if len(rig.bag()) < before:
    rig.bank("lab_pc_stored2")
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
