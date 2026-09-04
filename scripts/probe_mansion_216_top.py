"""Mansion B1F past (26,17): press the (20,3) switch, take the SECRET KEY at (5,13), test 1F's pocket door from inside.

State after ONE press of 216's (18,25): (13,22)/(13,23) open, (16,16)/(17,16) shut, (26,17) open, (9,6)/(9,7) shut.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
PAIRS = rt.loaded_pairs(TRUTH)
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/mansion_216_top.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
blocked: set = {(9, 6), (9, 7), (16, 16), (17, 16)}


def journal(content):
    row = {
        "referenced_time": datetime.now(timezone.utc).isoformat(),
        "priority": "important",
        "content": content,
        "source_session": "extractor",
    }
    append_observations("pokedex/memory", [row], dedupe=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def follow(mp, goals, cap=250):
    """Walk the ROM path one press at a time; three refusals of one step is a door -- block it and re-plan."""
    goals = set(goals)
    stuck = 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp:
            return False
        if (x, y) in goals:
            return True
        path = rt.path_on_map(TRUTH, PAIRS, mp, (x, y), goals, blocked=set(blocked))
        if not path or len(path) < 2:
            print("   no path from", (x, y), "avoiding", sorted(blocked), flush=True)
            return False
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=8, release=8)
        rig.ctl.wait(30)
        drain()
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                print(f"   refused {(x, y)} -> {(nx, ny)}; blocking it", flush=True)
                blocked.add((nx, ny))
                stuck = 0
            else:
                rig.ctl.wait(60)
        else:
            stuck = 0
    return False


def press_switch(mp, stands):
    for stand, face in stands:
        if not follow(mp, {stand}):
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


def door(mp, stand, face):
    if not follow(mp, {stand}):
        return None
    before = rig.pos()
    rig.io.press(face, hold=16, release=16)
    rig.ctl.wait(40)
    drain()
    return rig.pos() != before


print("start", rig.pos(), flush=True)
r = press_switch(216, (((20, 4), "up"), ((21, 3), "left"), ((20, 2), "down")))
print("216 switch (20,3):", r, flush=True)
if r:
    rig.bank("mansion_216_top_pressed")
    blocked.clear()  # the state changed; relearn the doors
got = False
if follow(216, {(5, 12), (4, 13), (6, 13), (5, 14)}):
    if rig.bag_full():
        print("make_room:", rig.make_room(), flush=True)
    names = [n for n, _ in rig.bag_named(full=True)]
    got = rig.collect_item(5, 13)
    names2 = [n for n, _ in rig.bag_named(full=True)]
    print("collect (5,13):", got, "| new:", [n for n in names2 if n not in names], flush=True)
    rig.screenshot("secret_key")
    got = any("SECRET KEY" in n for n in names2)
    if got:
        rig.bank("secret_key")
        print("*** SECRET KEY IN THE BAG ***", rig.pos(), flush=True)
journal(
    f"map=216 (20,3) switch pressed from {r[0] if r else None} after one (18,25) press: key room reached={got}; "
    f"doors refused on the way: {sorted(blocked)}"
)
# the way out: 216 (23,22) -> 165 (21,23), inside the pocket sealed by (20,17)/(21,17)
if got:
    print("to the 216 exit:", follow(216, {(23, 21)}), rig.pos(), flush=True)
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(70)
    drain()
    print("on 165?", rig.pos(), flush=True)
    if rig.pos()[0] == 165:
        blocked.clear()
        out = {}
        for stand, face in (((20, 18), "up"), ((21, 18), "up")):
            out[stand] = door(165, stand, face)
            print(f"165 pocket door from {stand}: {out[stand]}", flush=True)
            if out[stand]:
                break
        journal(f"map=165 stairs-pocket doors (20,17)/(21,17) from inside after 216's two presses: {out}")
        if any(out.values()):
            rig.bank("secret_key_out")
            print("*** OUT OF THE POCKET ***", rig.pos(), flush=True)
        else:
            rig.bank("secret_key_pocket")
print("final", rig.pos(), "blocked", sorted(blocked), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
