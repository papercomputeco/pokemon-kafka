"""Stage B on the main baton (seafoam_b3_main.state, 161 (6,12), clean boulders): replay the catalog's 11-push chain
to '0,14;3,16;6,15;9,12;18,6;19,6', make the (6,15)-DOWN push from (6,14), fall through (6,16) to B4 (5,14), surf to
shore (7,11), SURF DOWN (the current is stopped), round the left channel to (7,4)->(7,3)->(7,2). Bank platform_main."""

import json
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/seafoam_b3_main.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)

# (stand, face, boulder, expected boulder cell after) -- the catalog chain, then the unmade push
CHAIN = [
    ((9, 15), "up", (9, 14), (9, 13)),
    ((6, 14), "left", (5, 14), (4, 14)),
    ((5, 14), "left", (4, 14), (3, 14)),
    ((4, 14), "left", (3, 14), (2, 14)),
    ((3, 14), "left", (2, 14), (1, 14)),
    ((2, 14), "left", (1, 14), (0, 14)),
    ((3, 14), "down", (3, 15), (3, 16)),
    ((9, 14), "up", (9, 13), (9, 12)),
    ((8, 13), "down", (8, 14), (8, 15)),
    ((9, 15), "left", (8, 15), (7, 15)),
    ((8, 15), "left", (7, 15), (6, 15)),
    ((6, 14), "down", (6, 15), (6, 16)),
]


def tile(mp, x, y):
    return int(TRUTH["maps"][str(mp)]["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(mp, x, y, water):
    m = TRUTH["maps"][str(mp)]
    if not (0 <= x < m["width"] and 0 <= y < m["height"]) or tile(mp, x, y) == 0x22:
        return False
    return m["grid"][y][x] == "1" or (water and tile(mp, x, y) in (0x14, 0x15))


def drain(n=16):
    for _ in range(n):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def journal(c):
    append_observations(
        "pokedex/memory",
        [
            {
                "referenced_time": datetime.now(timezone.utc).isoformat(),
                "priority": "important",
                "source_session": "extractor",
                "content": c,
            }
        ],
        dedupe=True,
    )


def boulders():
    return sorted(tuple(b[:2]) for b in rig.bodies())


def navigate(mp, goals, water=True, cap=400, solid=()):
    goals = set(goals)
    blocked = set(solid)
    stuck = 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp:
            return ("left-map", (m, x, y))
        if (x, y) in goals:
            return ("reached", (x, y))
        prev = {(x, y): None}
        q = deque([(x, y)])
        path = None
        while q:
            c = q.popleft()
            if c in goals:
                path = [c]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                path = path[::-1]
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if n not in prev and n not in blocked and enterable(mp, *n, water):
                    prev[n] = c
                    q.append(n)
        if not path or len(path) < 2:
            return ("no-path", (x, y))
        nx, ny = path[1]
        if tile(mp, nx, ny) == 0x14 and tile(mp, x, y) != 0x14:
            rig.io.press(K[(nx - x, ny - y)], hold=4, release=8)
            rig.ctl.wait(12)
            before = rig.pos()
            rig.use_field_move("SURF", species="Gyarados")
            said = rig.textbox()
            drain()
            rig.ctl.wait(30)
            if rig.pos() == before:
                print(f"  surf blocked {(x, y)}->{(nx, ny)}: {said!r}", flush=True)
                blocked.add((nx, ny))
                continue
        else:
            rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
            rig.ctl.wait(24)
            drain()
        if rig.pos()[0] != mp:
            return ("left-map", rig.pos())
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


print("start", rig.pos(), "boulders", boulders(), flush=True)
drain()
rig.use_field_move("STRENGTH", species="Gyarados")
drain()
ok = True
for i, (stand, face, boulder, expect) in enumerate(CHAIN):
    r = navigate(161, {stand}, water=False, solid=set(boulders()))
    if rig.pos()[1:] != stand:
        print(f"step {i}: cannot stand {stand}: {r}", flush=True)
        ok = False
        break
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(16)
    drain()
    before = boulders()
    rig.io.press(face, hold=16, release=16)
    rig.ctl.wait(80)
    drain()
    after = boulders()
    moved = boulder not in after and expect in after
    print(f"step {i}: {boulder} {face} from {stand} -> expect {expect}: {'OK' if moved else 'NO'} {after}", flush=True)
    if not moved:
        rig.screenshot(f"holes_main_fail_{i}")
        ok = False
        break
journal(f"map=161 main baton push chain: ok={ok}, boulders {boulders()}")
if ok:
    rig.bank("b3_holes_main")
    # fall through (6,16)
    for stand, face in (((6, 15), "down"), ((5, 16), "right"), ((7, 16), "left")):
        navigate(161, {stand}, water=False, solid=set(boulders()))
        if rig.pos()[1:] == stand:
            rig.io.press(face, hold=16, release=16)
            rig.ctl.wait(80)
            drain()
        if rig.pos()[0] == 162:
            break
    print("after (6,16):", rig.pos(), flush=True)
if rig.pos()[0] == 162:
    rig.bank("b4_main")
    r = navigate(162, {(7, 11)})
    print("to (7,11):", r, flush=True)
    if rig.pos()[1:] == (7, 11):
        rig.io.press("down", hold=6, release=8)
        rig.ctl.wait(16)
        drain()
        before = rig.pos()
        rig.use_field_move("SURF", species="Gyarados")
        said = rig.textbox()
        drain()
        rig.ctl.wait(30)
        print(f"(7,11) SURF: moved={rig.pos() != before} said={said!r}", flush=True)
        if rig.pos() != before:
            r = navigate(162, {(7, 2)})
            print("to the platform (7,2):", r, flush=True)
            if rig.pos()[1:] == (7, 2):
                rig.bank("platform_main")
                print("*** MAIN BATON AT THE PLATFORM ***", flush=True)
                journal(
                    "map=162 MAIN 7-badge baton at the platform (7,2), one tile from the (6,1) legendary; "
                    "bank platform_main"
                )
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
