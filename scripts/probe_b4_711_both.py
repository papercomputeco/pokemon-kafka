"""B4 with BOTH B3 holes filled (b4_after_both_holes.state, player at (5,14)): reach shore (7,11) with the walker
that reached it before (land + water BFS, holes solid, SURF armed only on a water step), then SURF DOWN and read.
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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/b4_after_both_holes.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def tile(x, y):
    return int(TRUTH["maps"]["162"]["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(x, y):
    m = TRUTH["maps"]["162"]
    if not (0 <= x < m["width"] and 0 <= y < m["height"]) or tile(x, y) == 0x22:
        return False
    return m["grid"][y][x] == "1" or tile(x, y) in (0x14, 0x15)


def drain(n=14):
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


def surf_down():
    rig.io.press("down", hold=6, release=8)
    rig.ctl.wait(16)
    drain()
    before = rig.pos()
    rig.use_field_move("SURF", species="Gyarados")
    said = rig.textbox()
    drain()  # the mount animates after the text; judge the position once it settles
    rig.ctl.wait(30)
    moved = rig.pos() != before
    return moved, said


def navigate(goals, cap=300):
    goals = set(goals)
    blocked = set()
    stuck = 0
    notes = []
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != 162:
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
                if n not in prev and n not in blocked and enterable(*n):
                    prev[n] = c
                    q.append(n)
        if not path or len(path) < 2:
            return ("no-path", (x, y), notes)
        nx, ny = path[1]
        if tile(nx, ny) == 0x14 and tile(x, y) != 0x14:
            rig.io.press(K[(nx - x, ny - y)], hold=4, release=8)
            rig.ctl.wait(12)
            before = rig.pos()
            rig.use_field_move("SURF", species="Gyarados")
            said = rig.textbox()
            drain()
            rig.ctl.wait(30)
            if rig.pos() == before:
                notes.append(f"{(x, y)}->{(nx, ny)}: {said!r}")
                print(f"  surf blocked {(x, y)}->{(nx, ny)}: {said!r}", flush=True)
                blocked.add((nx, ny))
                continue
        else:
            rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
            rig.ctl.wait(24)
            drain()
        if rig.pos()[0] != 162:
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


print("start", rig.pos(), "sprites", sorted(tuple(b[:2]) for b in rig.bodies()), flush=True)
drain()
r = navigate({(7, 11)})
print("to (7,11):", r[0], r[1], r[2][:6], flush=True)
if rig.pos()[1:] == (7, 11):
    moved, said = surf_down()
    print(
        f"*** (7,11) SURF DOWN, both B3 holes filled: moved={moved} now={rig.pos()[1:]} said={said!r} ***", flush=True
    )
    rig.screenshot("b4_711_both_holes")
    journal(f"map=162 (7,11) SURF DOWN with BOTH B3 holes filled ((3,16) and (6,16)): moved={moved} said={said!r}")
    if moved:
        rig.bank("b4_current_cleared")
        r3 = navigate({(6, 2), (7, 1), (5, 1), (7, 2)})
        print("to the platform:", r3[0], r3[1], r3[2][:4], flush=True)
        rig.screenshot("b4_platform")
        if rig.pos()[0] == 162 and rig.pos()[2] <= 3:
            rig.bank("b4_platform_edge")
            for cell, face in (((6, 2), "up"), ((7, 1), "left"), ((5, 1), "right"), ((7, 2), "up")):
                navigate({cell})
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
