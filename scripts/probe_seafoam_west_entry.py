"""Main baton, Route 20 east end (31 (99,4), surfing): cross west, step ashore on the island's 0x32 beach at
x=62, walk to the west cave door (48,5) -> 192 (4,17) west pocket, then the measured west descent
192 (7,5) -> 159 (13,7) -> 160 (5,13) -> 161 (5,12): B3's boulder pocket. Banks each floor."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/seafoam_west-31.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def tile(mp, x, y):
    return int(TRUTH["maps"][str(mp)]["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(mp, x, y, water):
    m = TRUTH["maps"][str(mp)]
    if not (0 <= x < m["width"] and 0 <= y < m["height"]) or tile(mp, x, y) == 0x22:
        return False
    t = tile(mp, x, y)
    return m["grid"][y][x] == "1" or (water and t in (0x14, 0x11, 0x15, 0x32))


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


def navigate(mp, goals, water=True, cap=500, solid=()):
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
        if tile(mp, nx, ny) in (0x14, 0x11) and tile(mp, x, y) not in (0x14, 0x11):
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
                print(f"  wall {(x, y)}->{(nx, ny)}", flush=True)
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


print("start", rig.pos(), flush=True)
drain()
if rig.pos()[0] == 31:
    r = navigate(31, {(48, 6)})
    print("to the west door's step (48,6):", r, flush=True)
    rig.screenshot("route20_west_door")
    if rig.pos()[1:] == (48, 6):
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
    print("after the door:", rig.pos(), flush=True)
    journal(f"map=31 main baton from (99,4): nav to (48,6) = {r}; door -> {rig.pos()}")
if rig.pos()[0] == 192:
    rig.bank("seafoam_1f_main")
    chain = [(192, (7, 5), 159), (159, (13, 7), 160), (160, (5, 13), 161)]
    for mp, stair, nxt in chain:
        solid = set(tuple(b[:2]) for b in rig.bodies())
        r = navigate(mp, {stair}, water=False, solid=solid)
        for _ in range(3):
            if rig.pos()[0] == nxt:
                break
            for key in ("up", "down", "left", "right"):
                if rig.pos()[0] == nxt:
                    break
                rig.io.press(key, hold=16, release=16)
                rig.ctl.wait(70)
                drain()
        print(f"{mp} -> {nxt} via {stair}: nav={r} now {rig.pos()}", flush=True)
        if rig.pos()[0] != nxt:
            break
        rig.bank(f"seafoam_{nxt}_main")
if rig.pos()[0] == 161:
    print("*** MAIN BATON ON B3 ***", rig.pos(), "boulders", sorted(tuple(b[:2]) for b in rig.bodies()), flush=True)
    rig.bank("seafoam_b3_main")
    journal(f"map=161 MAIN 7-badge baton reached B3 at {rig.pos()[1:]} via the west descent; bank seafoam_b3_main")
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
