"""Door state B on mansion 1F: through (24,13) to the (21,23) stairs, down to 216, the SECRET KEY ball at (5,13)."""

import sys

sys.path.insert(0, "scripts")
import json

import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
SHUT = {(20, 17), (21, 17), (16, 7)}  # state B's shut doors; the ROM grid calls them floor
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/mansion_catalog_end.state"
rig = Rig(STATE, settle_on_boot=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


print("start", rig.pos(), flush=True)


def press_switch():
    drain()
    rig.walk(165, {(2, 6)}, battle=rig.battle)
    rig.io.press("up", hold=4, release=8)
    rig.ctl.wait(20)
    drain()
    for _ in range(5):
        rig.ctl.press("a")
        rig.ctl.wait(50)
    drain()


def follow(mp, goal, blocked, cap=80):
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp or (x, y) == goal:
            return (x, y) == goal
        path = rt.path_on_map(TRUTH, rt.loaded_pairs(TRUTH), mp, (x, y), {goal}, blocked=set(blocked))
        if not path or len(path) < 2:
            print("  no path from", (x, y), "avoiding", sorted(blocked), flush=True)
            return False
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=8, release=8)
        rig.ctl.wait(30)
        if rig.pos()[1:] == (x, y):
            print("  refused", (x, y), "->", (nx, ny), repr(rig.textbox()), flush=True)
            blocked = set(blocked) | {(nx, ny)}
    return False


# The stairs pocket is bounded only by the doors (20,17)/(21,17) (ROM regions with the doors shut).
# They are shut in state B (the banked state); flip to A and test them properly, standing at (20,16).
press_switch()
opened = False
for stand in ((20, 16), (21, 16)):
    for attempt in range(4):
        drain()
        rig.walk(165, {stand}, battle=rig.battle)
        if rig.pos()[1:] != stand:
            rig.ctl.wait(60)  # a wandering body may be in the way; wait it out and retry
            continue
        before = rig.pos()
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(40)
        drain()
        print(f"state A: {stand} DOWN -> moved={rig.pos() != before} now {rig.pos()[1:]}", flush=True)
        opened = rig.pos() != before
        break
    if opened:
        break
if not opened:
    press_switch()  # back to B and try once more, in case A/B were mislabelled
    for stand in ((20, 16), (21, 16)):
        drain()
        rig.walk(165, {stand}, battle=rig.battle)
        if rig.pos()[1:] == stand:
            before = rig.pos()
            rig.io.press("down", hold=16, release=16)
            rig.ctl.wait(40)
            drain()
            print(f"state B: {stand} DOWN -> moved={rig.pos() != before} now {rig.pos()[1:]}", flush=True)
            opened = rig.pos() != before
            if opened:
                break
print("door (20,17)/(21,17) open:", opened, rig.pos(), flush=True)
if opened:
    rig.bank("mansion_stairs_pocket")
    print("follow to (21,22):", follow(165, (21, 22), set()), rig.pos(), flush=True)
for _ in range(3):
    if rig.pos()[0] == 216:
        break
    drain()
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(70)
print("after the stairs:", rig.pos(), flush=True)
if rig.pos()[0] == 216:
    rig.bank("mansion_216")
    names = [n for n, _ in rig.bag_named(full=True)]
    if rig.bag_full():
        print("bag full -> make_room:", rig.make_room(), flush=True)
    w = rig.walk(216, {(5, 12), (4, 13), (6, 13), (5, 14)}, battle=rig.battle)
    print("walk beside the ball:", w, rig.pos(), flush=True)
    got = rig.collect_item(5, 13)
    names2 = [n for n, _ in rig.bag_named(full=True)]
    print("collect (5,13):", got, "| new:", [n for n in names2 if n not in names], flush=True)
    rig.screenshot("secret_key")
    if any("SECRET KEY" in n for n in names2):
        rig.bank("secret_key")
        print("*** SECRET KEY IN THE BAG ***", rig.pos(), flush=True)
    else:
        print("said:", repr(rig.textbox()), flush=True)
        rig.bank("mansion_216_no_key")
print("final", rig.pos(), flush=True)
