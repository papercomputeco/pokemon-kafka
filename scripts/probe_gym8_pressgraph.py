"""Viridian gym (45): the floor as a PRESS GRAPH. From each reached position, save the state, press each direction,
let the spinners carry the player, record the landing (fighting any trainer that challenges). BFS over that measured
graph to the target cells, then execute the press path live. Target: beside the top-left body (2,1) -- the
leader's room, which the x=6 corridor cannot reach (a beaten trainer keeps standing on (6,5))."""

import io
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

K = ["up", "down", "left", "right"]
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/badge8.state"
GOALS = {(2, 2), (3, 1), (1, 1)}
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


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


def snap():
    drain()
    b = io.BytesIO()
    rig.pb.save_state(b)
    return b


def load(b):
    rig.pb.load_state(io.BytesIO(b.getvalue()))
    rig.ctl.wait(8)


def press_and_settle(key):
    rig.io.press(key, hold=12, release=8)
    rig.ctl.wait(24)
    for _ in range(40):
        p = rig.pos()
        rig.ctl.wait(6)
        if rig.pos() == p:
            break
    drain()
    return rig.pos()


print("start", rig.pos(), "badges", bin(rig.badges()), flush=True)
start = rig.pos()[1:]
states = {start: snap()}
edges = {}  # (pos, key) -> landing
prev = {start: None}
q = deque([start])
probes = 0
found = None
while q and probes < 1600:
    cur = q.popleft()
    if cur in GOALS:
        found = cur
        break
    for key in K:
        load(states[cur])
        p = press_and_settle(key)
        probes += 1
        if p[0] != 45:
            edges[(cur, key)] = ("left-map", p)
            continue
        land = p[1:]
        edges[(cur, key)] = land
        if land != cur and land not in states:
            states[land] = snap()
            prev[land] = (cur, key)
            q.append(land)
    if probes % 100 == 0:
        print(f"  {probes} presses, {len(states)} positions, frontier {len(q)}", flush=True)
print(f"explored {len(states)} positions with {probes} presses; goal found: {found}", flush=True)
spins = {
    k: v
    for k, v in edges.items()
    if isinstance(v, tuple)
    and len(v) == 2
    and not isinstance(v[0], str)
    and abs(v[0] - k[0][0]) + abs(v[1] - k[0][1]) > 1
}
print("slides (press -> far landing):", dict(list(spins.items())[:20]), flush=True)
journal(
    f"map=45 press-graph: {len(states)} positions reachable from {start} with {probes} presses; "
    f"goal {found}; slides {len(spins)}: " + "; ".join(f"{k[0]} {k[1]} -> {v}" for k, v in list(spins.items())[:24])
)
if found:
    path = []
    c = found
    while prev[c]:
        pc, key = prev[c]
        path.append((pc, key, c))
        c = pc
    path.reverse()
    print("press path:", [(a, k) for a, k, _b in path], flush=True)
    load(states[found])  # the measured state beside the body: continue from it
    rig.bank("gym8_topleft")
    face = {(2, 2): "up", (3, 1): "left", (1, 1): "right"}[found]
    b0 = rig.badges()
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(16)
    pages = []
    for i in range(30):
        rig.ctl.press("a")
        rig.ctl.wait(60)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
        if rig.mem[qm.ADDR_IN_BATTLE]:
            print(f"  battle after {i + 1} presses: {pages[-4:]}", flush=True)
            rig.battle()
            drain()
            break
    rig.ctl.wait(60)
    drain()
    b1 = rig.badges()
    print(f"(2,1) said {pages[:5]} | badges {b0:#010b} -> {b1:#010b}", flush=True)
    journal(f"map=45 body (2,1) from {found}: {pages[:5]}; badges {b0:#010b} -> {b1:#010b}")
    rig.screenshot("gym8_leader")
    if b1 != b0:
        rig.bank("badge8_won")
        print("*** BADGE 8 ***", bin(b1), flush=True)
    else:
        rig.bank("gym8_after_leader_talk")
print("final", rig.pos(), "badges", bin(rig.badges()), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
