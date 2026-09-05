"""Viridian gym (45) hand-drive: from badge8.state, up the x=6 corridor to the gatekeeper at (6,5), through to the
top-left room, talk to the body at (2,1) and read the BADGES byte. Spinner tiles are driven one press at a time and
the plan restarts from wherever the game puts the player."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/badge8.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
M = TRUTH["maps"]["45"]


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


def drain(n=16):
    for _ in range(n):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def bodies():
    return {tuple(b[:2]) for b in rig.bodies()}


def navigate(goals, cap=300, keep=()):
    goals = set(goals)
    blocked = set()
    stuck = 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != 45:
            return ("left-map", (m, x, y))
        if (x, y) in goals:
            return ("reached", (x, y))
        solid = (bodies() - goals - set(keep)) | blocked
        prev, q, path = {(x, y): None}, deque([(x, y)]), None
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
                if n in prev or n in solid or not (0 <= n[0] < 20 and 0 <= n[1] < 18):
                    continue
                if M["grid"][n[1]][n[0]] == "1":
                    prev[n] = c
                    q.append(n)
        if not path or len(path) < 2:
            return ("no-path", (x, y))
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
        rig.ctl.wait(24)
        for _ in range(30):  # a spinner keeps moving us; wait until the position settles
            p = rig.pos()[1:]
            rig.ctl.wait(6)
            if rig.pos()[1:] == p:
                break
        drain()
        if rig.pos()[0] != 45:
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


def talk_to(body, stand, face):
    r = navigate({stand})
    print(f"to {stand} beside {body}: {r}", flush=True)
    if rig.pos()[1:] != stand:
        return None
    b0 = rig.badges()
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(16)
    pages = []
    for i in range(24):
        rig.ctl.press("a")
        rig.ctl.wait(60)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
        if rig.mem[qm.ADDR_IN_BATTLE]:
            print(f"  battle after {i + 1} presses: {pages[-3:]}", flush=True)
            rig.battle()
            drain()
            break
    drain()
    rig.ctl.wait(60)
    drain()
    print(f"  {body}: {pages[:4]} | badges {b0:#010b} -> {rig.badges():#010b}", flush=True)
    return pages


print("start", rig.pos(), "badges", bin(rig.badges()), "bodies", sorted(bodies()), flush=True)
drain()
b0 = rig.badges()
# 1) the gatekeeper at (6,5) from (6,6)
talk_to((6, 5), (6, 6), "up")
rig.bank("gym8_gate")
# 2) into the top-left room: (6,4) then beside (2,1)
r = navigate({(2, 2), (3, 1), (1, 1)})
print("to the top-left room:", r, rig.pos(), flush=True)
rig.screenshot("gym8_topleft")
if rig.pos()[1:] in ((2, 2), (3, 1), (1, 1)):
    face = {(2, 2): "up", (3, 1): "left", (1, 1): "right"}[rig.pos()[1:]]
    talk_to((2, 1), rig.pos()[1:], face)
b1 = rig.badges()
journal(f"map=45 hand-drive: (6,5) then (2,1); badges {b0:#010b} -> {b1:#010b}; pos {rig.pos()}")
if b1 != b0:
    rig.bank("badge8_won")
    print("*** BADGE 8 ***", bin(b1), rig.pos(), flush=True)
else:
    rig.bank("gym8_after_topleft")
print("final", rig.pos(), "badges", bin(rig.badges()), "party", [(n, lv, hp) for n, lv, hp in rig.party()], flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
