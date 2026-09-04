"""The push the oracle never made: a boulder sits at (6,15) above B3's second hole (6,16) with (3,16) already
filled, and every catalog entry for '(6,15) down' says 'unreachable' -- the static pair model's verdict, never
the game's. Step to the stand (6,14) by hand (no pair model), STRENGTH-push DOWN, and follow the boulder to B4:
retest the (7,11) current, and if it has slowed, surf to the (6,1) platform and read what stands there.
"""

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
STATE = (
    sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/oracle/161_0-14_3-16_6-15_9-12_18-6_19-6.state"
)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def tile(mp, x, y):
    return int(TRUTH["maps"][str(mp)]["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(mp, x, y, water=True):
    m = TRUTH["maps"][str(mp)]
    if not (0 <= x < m["width"] and 0 <= y < m["height"]):
        return False
    if tile(mp, x, y) == 0x22:  # an open hole drops the player a floor; never a step on the way somewhere
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


def navigate(mp, goals, cap=300, water=True, solid=()):
    """Grid BFS with no tile-pair model; boulders solid; arms SURF (use_field_move) on water entry."""
    goals = set(goals)
    blocked = set(solid)
    stuck = 0
    notes = []
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp:
            return ("left-map", (m, x, y), notes)
        if (x, y) in goals:
            return ("reached", (x, y), notes)
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
                if n not in prev and n not in blocked and enterable(mp, *n, water=water):
                    prev[n] = c
                    q.append(n)
        if not path or len(path) < 2:
            return ("no-path", (x, y), notes)
        nx, ny = path[1]
        if tile(mp, nx, ny) == 0x14 and tile(mp, x, y) != 0x14:
            rig.io.press(K[(nx - x, ny - y)], hold=4, release=8)
            rig.ctl.wait(12)
            before = rig.pos()
            rig.use_field_move("SURF", species="Gyarados")
            said = rig.textbox()
            drain()
            if rig.pos() == before:
                notes.append(f"{(x, y)}->{(nx, ny)}: {said!r}")
                print(f"  surf blocked {(x, y)}->{(nx, ny)}: {said!r}", flush=True)
                blocked.add((nx, ny))
                continue
        else:
            rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
            rig.ctl.wait(24)
            drain()
        if rig.pos()[0] != mp:
            return ("left-map", rig.pos(), notes)
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
                print(f"  wall {(x, y)}->{(nx, ny)}", flush=True)
        else:
            stuck = 0
    return ("cap", rig.pos()[1:], notes)


print("start", rig.pos(), "boulders", boulders(), flush=True)
drain()
rig.use_field_move("STRENGTH", species="Gyarados")
drain()
b0 = boulders()
# stand at (6,14): walk the grid with the boulders solid and NO pair model
r = navigate(161, {(6, 14)}, water=False, solid=set(b0))
print("to the stand (6,14):", r[0], r[1], flush=True)
rig.screenshot("stand_6_14")
result = None
if rig.pos()[1:] == (6, 14):
    rig.io.press("down", hold=4, release=8)
    rig.ctl.wait(16)
    drain()
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(80)
    said = rig.textbox()
    drain()
    b1 = boulders()
    result = f"push (6,15) DOWN from (6,14): before {b0} after {b1} pos {rig.pos()} said {said!r}"
    print(result, flush=True)
    rig.screenshot("push_615_down")
    rig.bank("b3_after_615_down")
journal(f"map=161 THE UNMADE PUSH: stand (6,14) reach={r[0]} at {r[1]}; {result}")
# follow it down: step onto the (6,16) hole
if rig.pos()[0] == 161 and result:
    for stand, face in (((6, 15), "down"), ((5, 16), "right"), ((7, 16), "left")):
        rr = navigate(161, {stand}, water=False, solid=set(boulders()))
        if rig.pos()[1:] == stand:
            rig.io.press(face, hold=16, release=16)
            rig.ctl.wait(70)
            drain()
        if rig.pos()[0] == 162:
            break
    print("after (6,16):", rig.pos(), "B4 boulders", boulders(), flush=True)
if rig.pos()[0] == 162:
    rig.bank("b4_after_both_holes")
    rig.screenshot("b4_after_both_holes")
    journal(f"map=162 after (3,16)+(6,16): landed {rig.pos()[1:]}, B4 sprites {boulders()}")
    # the (7,11) test, then the platform
    r2 = navigate(162, {(7, 11)}, water=False)
    if rig.pos()[1:] == (7, 11):
        rig.io.press("down", hold=6, release=8)
        rig.ctl.wait(16)
        before = rig.pos()
        rig.use_field_move("SURF", species="Gyarados")
        said = rig.textbox()
        moved = rig.pos() != before
        print(f"*** (7,11) after both holes: moved={moved} now={rig.pos()[1:]} said={said!r} ***", flush=True)
        rig.screenshot("b4_711_after_both")
        journal(f"map=162 (7,11) current after BOTH B3 holes filled: moved={moved} said={said!r}")
        drain()
        if moved:
            rig.bank("b4_current_cleared")
            r3 = navigate(162, {(6, 2), (7, 1), (5, 1), (7, 2)})
            print("to the platform:", r3[0], r3[1], r3[2][:4], flush=True)
            rig.screenshot("b4_platform")
            if rig.pos()[0] == 162 and rig.pos()[2] <= 3:
                rig.bank("b4_platform_edge")
                for cell, face in (((6, 2), "up"), ((7, 1), "left"), ((5, 1), "right"), ((7, 2), "up")):
                    navigate(162, {cell}, water=False)
                    if rig.pos()[1:] == cell:
                        said = rig.talk(face)
                        inb = rig.mem[qm.ADDR_IN_BATTLE]
                        print(f"*** (6,1) from {cell}: {said!r} in_battle={inb} ***", flush=True)
                        rig.screenshot("b4_legendary")
                        journal(f"map=162 THE (6,1) SPRITE from {cell} facing {face}: {said!r}; in_battle={inb}")
                        if inb:
                            rig.bank("b4_legendary_battle")
                        break
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
