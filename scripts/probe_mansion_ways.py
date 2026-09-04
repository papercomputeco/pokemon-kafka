"""Two ways back to 165 after 215's switch: 214's own switch from (8,4), or 215's (7,11) stair from (10,6)."""

import json
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}


def drain(rig, limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def step_path(rig, mp, goal, cap=80):
    """Walk the ROM path one press at a time; report the first refused step."""
    for _ in range(cap):
        drain(rig)
        m, x, y = rig.pos()
        if m != mp or (x, y) == goal:
            return True
        path = rt.path_on_map(TRUTH, rt.loaded_pairs(TRUTH), mp, (x, y), {goal})
        if not path or len(path) < 2:
            print("   no ROM path from", (x, y), flush=True)
            return False
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=8, release=8)
        rig.ctl.wait(30)
        if rig.pos()[1:] == (x, y):
            print(f"   REFUSED {(x, y)} -> {(nx, ny)} on {mp}", flush=True)
            return False
    return False


def stairs(rig, mp, beside, key, want):
    drain(rig)
    rig.walk(mp, set(beside), battle=rig.battle)
    for _ in range(3):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(70)
        drain(rig)
    return rig.pos()[0] == want


# after 215's press: up the (6,1) stair, then to 214's (5,11) routing AROUND the shut (9,4), then 165
def follow(rig, mp, goal, blocked, cap=120):
    blocked = set(blocked)
    for _ in range(cap):
        drain(rig)
        m, x, y = rig.pos()
        if m != mp or (x, y) == goal:
            return (x, y) == goal
        path = rt.path_on_map(TRUTH, rt.loaded_pairs(TRUTH), mp, (x, y), {goal}, blocked=blocked)
        if not path or len(path) < 2:
            print("   no path from", (x, y), "avoiding", sorted(blocked), flush=True)
            return False
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=8, release=8)
        rig.ctl.wait(30)
        if rig.pos()[1:] == (x, y):
            print(f"   refused {(x, y)} -> {(nx, ny)}; blocking it", flush=True)
            blocked.add((nx, ny))
    return False


r = Rig("data/local_runs/roster-bench/mansion_215_pressed.state", settle_on_boot=True)
print("start", r.pos(), flush=True)
print("215 -> 214 via (6,1):", stairs(r, 215, [(6, 2), (5, 1), (7, 1)], "up", 214), r.pos(), flush=True)
if r.pos()[0] == 214:
    print("214: to (5,11) around (9,4):", follow(r, 214, (5, 11), {(9, 4)}), r.pos(), flush=True)
    if r.pos()[1:] == (5, 11):
        r.io.press("up", hold=16, release=16)
        r.ctl.wait(70)
        drain(r)
print("165?", r.pos(), flush=True)
if r.pos()[0] == 165:
    r.bank("mansion_after_215")
    for stand in ((20, 16), (21, 16)):
        print("   to", stand, ":", follow(r, 165, stand, set()), r.pos()[1:], flush=True)
        if r.pos()[1:] != stand:
            continue
        before = r.pos()
        r.io.press("down", hold=16, release=16)
        r.ctl.wait(40)
        drain(r)
        print(f"   stairs door from {stand}: moved={r.pos() != before}", flush=True)
        if r.pos() != before:
            r.bank("mansion_stairs_pocket")
            print("*** STAIRS POCKET ***", r.pos(), flush=True)
            break
print("final", r.pos(), flush=True)
