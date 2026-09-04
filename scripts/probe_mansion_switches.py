"""Catalog which switch opens which door in the mansion: toggle each reachable switch, re-test each door."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

DOORS = {"D16_7": ((16, 6), "down"), "D24_13": ((24, 12), "down"), "D20_17": ((20, 16), "down")}
rig = Rig("data/local_runs/roster-bench/mansion_doors_open.state", settle_on_boot=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def press_switch(mp, stand, face):
    drain()
    if rig.walk(mp, {stand}, battle=rig.battle) is not True or rig.pos()[1:] != stand:
        return f"could not reach {stand} on {mp} (at {rig.pos()})"
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(20)
    drain()
    pages = []
    for _ in range(5):
        rig.ctl.press("a")
        rig.ctl.wait(50)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
        if pages and not t:
            break
    drain()
    return pages


def test_doors():
    out = {}
    for name, (cell, face) in DOORS.items():
        drain()
        if rig.walk(165, {cell}, battle=rig.battle) is not True or rig.pos()[1:] != cell:
            out[name] = "unreachable"
            continue
        before = rig.pos()
        rig.io.press(face, hold=16, release=16)
        rig.ctl.wait(40)
        drain()
        out[name] = "open" if rig.pos() != before else "shut"
        if rig.pos() != before:  # step back so the next test starts from a known side
            rig.walk(165, {cell}, battle=rig.battle)
    return out


print("start", rig.pos(), "| doors now:", test_doors(), flush=True)
print("press 165's switch again:", press_switch(165, (2, 6), "up"), "| doors:", test_doors(), flush=True)
print("press 165's switch a third time:", press_switch(165, (2, 6), "up"), "| doors:", test_doors(), flush=True)
# now the 214 switch: down the (5,10) stair, press (2,11) from below/beside, come back up
drain()
rig.walk(165, {(5, 11)}, battle=rig.battle)
rig.io.press("up", hold=16, release=16)
rig.ctl.wait(70)
drain()
print("on 214?", rig.pos(), flush=True)
if rig.pos()[0] == 214:
    for stand, face in (((2, 12), "up"), ((3, 11), "left"), ((1, 11), "right")):
        r = press_switch(214, stand, face)
        print(f"214 switch from {stand} {face}:", r, flush=True)
        if isinstance(r, list) and any("switch" in p.lower() for p in r):
            break
    rig.walk(214, {(5, 11)}, battle=rig.battle)
    rig.io.press("up", hold=16, release=16)
    rig.ctl.wait(70)
    drain()
    print("back on", rig.pos(), "| doors:", test_doors(), flush=True)
rig.bank("mansion_catalog_end")
print("final", rig.pos(), flush=True)
