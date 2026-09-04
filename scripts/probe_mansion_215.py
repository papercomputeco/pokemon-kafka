"""Press 215's switch and test the stairs door on 165. 165 (5,10) -> 214; 214 (7,10) -> 215; switch (10,5); back."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/mansion_catalog_end.state", settle_on_boot=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def stairs(mp, beside, key, want):
    drain()
    rig.walk(mp, set(beside), battle=rig.battle)
    for _ in range(3):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(70)
        drain()
    return rig.pos()[0] == want


def press_switch(mp, stands):
    for stand, face in stands:
        drain()
        rig.walk(mp, {stand}, battle=rig.battle)
        if rig.pos()[1:] != stand:
            continue
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
        drain()
        if any("switch" in p.lower() for p in pages):
            return stand, pages
    return None


def test_stairs_door():
    for stand in ((20, 16), (21, 16)):
        drain()
        rig.walk(165, {stand}, battle=rig.battle)
        if rig.pos()[1:] != stand:
            continue
        before = rig.pos()
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(40)
        drain()
        if rig.pos() != before:
            return True
    return False


print("start", rig.pos(), flush=True)
print("165 -> 214:", stairs(165, [(5, 11)], "up", 214), rig.pos(), flush=True)
# static: the (6,1) stair's landing on 215 reaches the switch stand (10,6); the (7,10) stair's does not
up = stairs(214, [(6, 2)], "up", 215) or stairs(214, [(7, 1)], "left", 215)
print("214 -> 215 via (6,1):", up, rig.pos(), flush=True)
if rig.pos()[0] == 215:
    r = press_switch(215, (((10, 6), "up"), ((9, 5), "right"), ((11, 5), "left"), ((10, 4), "down")))
    print("215 switch:", r, flush=True)
    rig.bank("mansion_215_pressed")
    back = stairs(215, [(6, 2), (5, 1), (7, 1)], "up", 214) or stairs(215, [(7, 11)], "down", 214)
    print("215 -> 214:", back, rig.pos(), flush=True)
if rig.pos()[0] == 214:
    print("214 -> 165:", stairs(214, [(5, 11)], "up", 165), rig.pos(), flush=True)
if rig.pos()[0] == 165:
    ok = test_stairs_door()
    print("stairs door (20,17)/(21,17) open after 215's switch:", ok, rig.pos(), flush=True)
    if ok:
        rig.bank("mansion_stairs_pocket")
        print("*** STAIRS POCKET ***", flush=True)
        rig.walk(165, {(21, 22)}, battle=rig.battle)
        for _ in range(3):
            if rig.pos()[0] == 216:
                break
            rig.io.press("down", hold=16, release=16)
            rig.ctl.wait(70)
            drain()
        print("216?", rig.pos(), flush=True)
        if rig.pos()[0] == 216:
            rig.bank("mansion_216")
            if rig.bag_full():
                print("make_room:", rig.make_room(), flush=True)
            names = [n for n, _ in rig.bag_named(full=True)]
            rig.walk(216, {(5, 12), (4, 13), (6, 13), (5, 14)}, battle=rig.battle)
            print("collect (5,13):", rig.collect_item(5, 13), flush=True)
            names2 = [n for n, _ in rig.bag_named(full=True)]
            print("new items:", [n for n in names2 if n not in names], flush=True)
            if any("SECRET KEY" in n for n in names2):
                rig.bank("secret_key")
                print("*** SECRET KEY IN THE BAG ***", rig.pos(), flush=True)
print("final", rig.pos(), flush=True)
