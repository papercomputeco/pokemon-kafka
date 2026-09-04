"""Press the secret switch at (2,5), re-test the secret doors, walk to the stairs, get the SECRET KEY."""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/mansion_1f.state", settle_on_boot=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def press_switch():
    drain()
    print("walk to (2,6):", rig.walk(165, {(2, 6)}, battle=rig.battle), rig.pos(), flush=True)
    rig.io.press("up", hold=4, release=8)
    rig.ctl.wait(20)
    drain()
    rig.ctl.press("a")
    rig.ctl.wait(50)
    pages = [rig.textbox()]
    for _ in range(4):  # 'A secret switch!' -> a YES/NO prompt; YES is the highlighted default
        rig.ctl.press("a")
        rig.ctl.wait(50)
        t = rig.textbox()
        if t != pages[-1]:
            pages.append(t)
        if not t:
            break
    rig.screenshot("mansion_switch_pressed")
    print("switch pages:", pages, flush=True)
    drain()


def try_step(cell, face):
    drain()
    rig.walk(165, {cell}, battle=rig.battle)
    if rig.pos()[1:] != cell:
        return None
    before = rig.pos()
    rig.io.press(face, hold=16, release=16)
    rig.ctl.wait(40)
    drain()
    return rig.pos() != before


press_switch()
opened = {d: try_step(*d) for d in (((16, 6), "down"), ((20, 16), "down"))}
print("doors after the switch:", opened, flush=True)
if not any(opened.values()):
    press_switch()  # a toggle: press again in case the first press closed rather than opened
    opened = {d: try_step(*d) for d in (((16, 6), "down"), ((20, 16), "down"))}
    print("doors after a second press:", opened, flush=True)
if any(opened.values()):
    rig.bank("mansion_doors_open")
    print("walk to (21,22):", rig.walk(165, {(21, 22)}, battle=rig.battle), rig.pos(), flush=True)
    for _ in range(3):
        if rig.pos()[0] == 216:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(70)
        drain()
    print("stairs:", rig.pos(), flush=True)
if rig.pos()[0] == 216:
    rig.bank("mansion_216")
    before = len(rig.bag())
    print("collect the ball at (5,13):", rig.collect_item(5, 13), "| bag", before, "->", len(rig.bag()), flush=True)
    names = [n for n, _ in rig.bag_named(full=True)]
    print("SECRET KEY in the bag?", any("SECRET KEY" in n for n in names), flush=True)
    if any("SECRET KEY" in n for n in names):
        rig.bank("secret_key")
        print("*** SECRET KEY ***", rig.pos(), flush=True)
print("final", rig.pos(), repr(rig.textbox()), flush=True)
