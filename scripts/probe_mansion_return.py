"""After 215's switch: get back to 165 by either stair, test the stairs door (20,17)/(21,17), take the key."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/mansion_215_pressed.state", settle_on_boot=True)


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


def to_165():
    # way 1: 215 (7,11) -> 214 (7,10) -> (5,11) -> up
    if rig.pos()[0] == 215 and stairs(215, [(7, 11)], "up", 214) is False:
        pass
    if rig.pos()[0] == 215:
        stairs(215, [(6, 2), (5, 1), (7, 1)], "up", 214)
    print("on 214?", rig.pos(), flush=True)
    for attempt in range(3):
        if rig.pos()[0] != 214:
            break
        w = rig.walk(214, {(5, 11)}, battle=rig.battle)
        print(f"  214 walk to (5,11) [{attempt}]: {w} {rig.pos()}", flush=True)
        if rig.pos()[1:] == (5, 11):
            rig.io.press("up", hold=16, release=16)
            rig.ctl.wait(70)
            drain()
            break
        rig.ctl.wait(90)
    return rig.pos()[0] == 165


print("start", rig.pos(), flush=True)
print("back on 165:", to_165(), rig.pos(), flush=True)
if rig.pos()[0] == 165:
    rig.bank("mansion_after_215")
    opened = False
    for stand in ((20, 16), (21, 16)):
        drain()
        rig.walk(165, {stand}, battle=rig.battle)
        if rig.pos()[1:] != stand:
            print("  cannot stand at", stand, "now at", rig.pos()[1:], flush=True)
            continue
        before = rig.pos()
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(40)
        drain()
        opened = rig.pos() != before
        print(f"  {stand} DOWN -> moved={opened}", flush=True)
        if opened:
            break
    if opened:
        rig.bank("mansion_stairs_pocket")
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
