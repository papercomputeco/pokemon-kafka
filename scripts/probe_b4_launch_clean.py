"""Clean B4 (7,11) launch: navigate to the shore, drain, face down, and try SURF -- first as index-5 Gyarados,
then with Gyarados swapped to lead -- reading the true on-screen sentence each way. Decides arm-bug vs one-way shore.
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
rig = Rig(
    sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/b4_from_conveyor.state", settle_on_boot=True
)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)


def tile(x, y):
    return int(TRUTH["maps"]["162"]["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(x, y):
    m = TRUTH["maps"]["162"]
    return 0 <= x < m["width"] and 0 <= y < m["height"] and (m["grid"][y][x] == "1" or tile(x, y) in (0x14, 0x15))


def drain(limit=14):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def navigate(goals, cap=400):
    goals = set(goals)
    blocked = set()
    stuck = 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != 162 or (x, y) in goals:
            return (x, y) if (x, y) in goals else ("left", (m, x, y))
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
            return ("no-path", (x, y))
        nx, ny = path[1]
        if tile(nx, ny) == 0x14 and tile(x, y) != 0x14:
            rig.io.press(K[(nx - x, ny - y)], hold=4, release=8)
            rig.ctl.wait(12)
            rig._arm_surf()
            drain()
        rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
        rig.ctl.wait(24)
        drain()
        if rig.pos()[0] != 162:
            return ("left", rig.pos())
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


r = navigate({(7, 11)})
print("nav to (7,11):", r, "pos", rig.pos(), flush=True)
notes = {}
if rig.pos()[1:] == (7, 11):
    drain()
    rig.io.press("down", hold=6, release=8)
    rig.ctl.wait(16)
    rig.screenshot("launch_faced_down")
    before = rig.pos()
    used = rig.use_field_move("SURF", species="Gyarados")
    said = rig.textbox()
    notes["idx5"] = f"used={used} moved={rig.pos() != before} now={rig.pos()[1:]} said={said!r}"
    print("idx5 SURF:", notes["idx5"], flush=True)
    drain()
    if rig.pos()[1:] == (7, 11):  # still on the shore: try with Gyarados as lead
        sw = rig.lead_swap(5)
        print("lead_swap(5):", sw, "party", [p[0] for p in rig.party()], flush=True)
        drain()
        rig.io.press("down", hold=6, release=8)
        rig.ctl.wait(16)
        before = rig.pos()
        armed = rig._arm_surf()
        said = rig.textbox()
        notes["lead"] = f"armed={armed} moved={rig.pos() != before} now={rig.pos()[1:]} said={said!r}"
        print("lead SURF:", notes["lead"], flush=True)
        rig.screenshot("launch_lead")
        if rig.pos()[1:] != (7, 11) and rig.pos()[0] == 162:
            rig.bank("b4_launched_711_lead")
append_observations(
    "pokedex/memory",
    [
        {
            "referenced_time": datetime.now(timezone.utc).isoformat(),
            "priority": "important",
            "source_session": "extractor",
            "content": f"map=162 B4 shore (7,11) launch DOWN into (7,12): {notes}",
        }
    ],
    dedupe=True,
)
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
