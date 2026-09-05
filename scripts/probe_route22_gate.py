"""Kit baton, Viridian -> Route 22 (33) -> the gate (193): talk to whoever stands in the way, leave by the north
mats to Route 23 (34). Bank route23_kit. What the guards say is the record."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/viridian_kit.state"
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


def drain(n=14):
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


def navigate(mp, goals, cap=200):
    """The ROM planner's path (it hops one-way ledges: Route 22's gate is behind three of them), one press per
    step; a ledge hop is one press that lands two cells on."""
    goals, blocked, stuck = set(goals), set(), 0
    for _ in range(cap):
        drain()
        cm, x, y = rig.pos()
        if cm != mp:
            return ("left-map", (cm, x, y))
        if (x, y) in goals:
            return ("reached", (x, y))
        solid = (bodies() - goals) | blocked
        path = rt.path_on_map(TRUTH, PAIRS, mp, (x, y), goals, blocked=solid)
        if not path or len(path) < 2:
            return ("no-path", (x, y))
        nx, ny = path[1]
        dx, dy = nx - x, ny - y
        key = K[(dx // abs(dx) if dx else 0, dy // abs(dy) if dy else 0)]
        rig.io.press(key, hold=12, release=8)
        if abs(dx) + abs(dy) == 2:  # a ledge hop animates longer
            rig.ctl.wait(40)
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


def talk_all(mp):
    said = {}
    for b in sorted(bodies()):
        for stand, face in (
            ((b[0], b[1] + 1), "up"),
            ((b[0] - 1, b[1]), "right"),
            ((b[0] + 1, b[1]), "left"),
            ((b[0], b[1] - 1), "down"),
        ):
            navigate(mp, {stand})
            if rig.pos()[1:] == stand:
                said[b] = rig.talk(face)
                drain()
                break
    return said


print("start", rig.pos(), flush=True)
drain()
# Viridian -> Route 22 by the west edge; the supervisor did this hop fine, so reuse its cross
if rig.pos()[0] == 1:
    print("1 -> 33:", rig.cross(1, 33), rig.pos(), flush=True)
if rig.pos()[0] == 33:
    rig.bank("route22_kit")
    r = navigate(33, {(8, 6)})
    print("to the gate door step (8,6):", r, rig.pos(), flush=True)
    for _ in range(3):
        if rig.pos()[0] == 193:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
print("in the gate?", rig.pos(), "bodies", sorted(bodies()), flush=True)
if rig.pos()[0] == 193:
    rig.io.press("up", hold=12, release=8)
    rig.ctl.wait(30)
    drain()
    said = talk_all(193)
    print("guards:", said, flush=True)
    journal(f"map=193 Route 22 gate with 8 badges: bodies {sorted(bodies())} said {said}")
    r = navigate(193, {(4, 1), (5, 1)})
    print("to the north mats' step:", r, rig.pos(), flush=True)
    for _ in range(3):
        if rig.pos()[0] != 193:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
    print("after the north door:", rig.pos(), flush=True)
if rig.pos()[0] == 34:
    rig.bank("route23_kit")
    print("*** ROUTE 23 -- banked route23_kit ***", rig.pos(), flush=True)
    journal(f"map=34 Route 23 reached from gate 193's north mats; landed {rig.pos()[1:]}")
print("final", rig.pos(), flush=True)
