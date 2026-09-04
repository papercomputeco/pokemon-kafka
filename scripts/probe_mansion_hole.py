"""Step onto 215's block of tile 0x11 (x 12-21, y 14-17) and follow the map wherever the game sends the player.

The ROM puts that tile on no other floor's walkable region except 214's warp-less 171-cell pocket, and both sit
above 165's sealed stairs pocket (x 12-23, y 14-26). If it drops, follow it down to 216 and the SECRET KEY ball.
"""

import json
import subprocess
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/mansion_215_pressed.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
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


def tile(mp, x, y):
    t = TRUTH["maps"][str(mp)]["tiles"]
    return int(t[y][2 * x : 2 * x + 2], 16)


def step(key, wait=60):
    before = rig.pos()
    rig.io.press(key, hold=16, release=16)
    rig.ctl.wait(wait)
    drain()
    after = rig.pos()
    t = hex(tile(after[0], after[1], after[2]))
    print(f"  {key}: {before} -> {after} tile={t} said={rig.textbox()!r}", flush=True)
    return before, after


def take_key():
    if rig.pos()[0] != 216:
        return False
    rig.bank("mansion_216")
    if rig.bag_full():
        print("make_room:", rig.make_room(), flush=True)
    names = [n for n, _ in rig.bag_named(full=True)]
    w = rig.walk(216, {(5, 12), (4, 13), (6, 13), (5, 14)}, battle=rig.battle)
    print("walk beside the ball:", w, rig.pos(), flush=True)
    print("collect (5,13):", rig.collect_item(5, 13), flush=True)
    names2 = [n for n, _ in rig.bag_named(full=True)]
    print("new items:", [n for n in names2 if n not in names], flush=True)
    rig.screenshot("secret_key")
    if any("SECRET KEY" in n for n in names2):
        rig.bank("secret_key")
        print("*** SECRET KEY IN THE BAG ***", rig.pos(), flush=True)
        return True
    print("said:", repr(rig.textbox()), flush=True)
    return False


def descend_from_165():
    """Inside 165's stairs pocket: (21,22) then DOWN through the (21,23) stairs to 216."""
    print("165 walk to (21,22):", rig.walk(165, {(21, 22)}, battle=rig.battle), rig.pos(), flush=True)
    for _ in range(3):
        if rig.pos()[0] == 216:
            break
        step("down", 70)
    return take_key()


print("start", rig.pos(), flush=True)
m0 = rig.pos()[0]
if m0 == 215:
    print("215 walk to (16,13):", rig.walk(215, {(16, 13)}, battle=rig.battle), rig.pos(), flush=True)
    if rig.pos()[1:] != (16, 13):
        print("215 walk to (17,13):", rig.walk(215, {(17, 13)}, battle=rig.battle), rig.pos(), flush=True)
    rig.screenshot("mansion_hole_before")
    step("down", 90)
    rig.screenshot("mansion_hole_after")
    # keep walking into the block until the map changes or the block is crossed
    for _ in range(6):
        if rig.pos()[0] != 215:
            break
        step("down", 90)
    if rig.pos()[0] == 215:
        # no drop on this column; sweep the whole 0x11 block row by row
        seen = set()
        for y in (14, 15, 16, 17):
            for x in range(12, 22):
                if rig.pos()[0] != 215:
                    break
                w = rig.walk(215, {(x, y)}, battle=rig.battle)
                p = rig.pos()
                if p[0] != 215:
                    print("  map changed while walking to", (x, y), "->", p, flush=True)
                    break
                seen.add(p[1:])
        print("0x11 cells stood on without a drop:", sorted(seen), flush=True)
print("after the block:", rig.pos(), flush=True)
if rig.pos()[0] == 214:
    rig.bank("mansion_fell_214")
    print("*** ON 214 at", rig.pos()[1:], "***", flush=True)
    # walk around the pocket; any step may drop again
    x, y = rig.pos()[1:]
    for key in ("down", "down", "left", "right", "up"):
        if rig.pos()[0] != 214:
            break
        step(key, 90)
if rig.pos()[0] == 165:
    rig.bank("mansion_fell_165")
    print("*** ON 165 at", rig.pos()[1:], "***", flush=True)
    descend_from_165()
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
