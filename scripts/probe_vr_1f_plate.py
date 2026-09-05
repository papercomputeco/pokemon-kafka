"""Victory Road 1F: push the plateau boulder (7,5) RIGHT x4, DOWN x7, LEFT x2 onto the lone 0x24 tile at (9,12), then
test the two 0x04 cliff gaps (4,9)/(4,4) and walk to the 2F stair (1,1). Every push is judged by the sprite table."""

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
D = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/victory_road_1f_kit.state"
MAP = 108
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


def walk_to(cell, cap=150):
    blocked, stuck = set(), 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != MAP:
            return "left-map"
        if (x, y) == cell:
            return "reached"
        path = rt.path_on_map(TRUTH, PAIRS, MAP, (x, y), {cell}, blocked=(bodies() - {cell}) | blocked)
        if not path or len(path) < 2:
            return "no-path"
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
        rig.ctl.wait(24)
        drain()
        if rig.pos()[0] != MAP:
            return "left-map"
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
    return "cap"


def push(boulder, face):
    dx, dy = D[face]
    stand = (boulder[0] - dx, boulder[1] - dy)
    r = walk_to(stand)
    if r != "reached":
        return f"stand {stand} {r}", boulder
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(16)
    drain()
    rig.strength_push(face)
    drain()
    new = (boulder[0] + dx, boulder[1] + dy)
    moved = new in bodies() and boulder not in bodies()
    return ("moved" if moved else "refused"), (new if moved else boulder)


print("start", rig.pos(), "bodies", sorted(bodies()), flush=True)
drain()
# the plate (9,12) is the chokepoint between the lower plateau arm and the top; the grid calls it solid.
# Measure: walk to (8,12) and step RIGHT. If the game allows it, tell the planner the cell is floor.
M = TRUTH["maps"][str(MAP)]
print("to (8,12):", walk_to((8, 12)), rig.pos(), flush=True)
if rig.pos()[1:] == (8, 12):
    rig.io.press("right", hold=16, release=16)
    rig.ctl.wait(40)
    drain()
    print("step onto the plate (9,12):", rig.pos(), repr(rig.textbox()[:50]), flush=True)
    if rig.pos()[1:] == (9, 12):
        row = list(M["grid"][12])
        row[9] = "1"
        M["grid"][12] = "".join(row)
        journal(
            "map=108 the 0x24 tile (9,12) is walkable for the player (grid said solid); it is the plateau's chokepoint"
        )
who = rig.knows_move("STRENGTH")
rig.use_field_move("STRENGTH", species=rig.party()[who][0])
for _ in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(40)
drain()
b = (7, 5)
log = []
for face, n in (("right", 4), ("down", 7), ("left", 2)):
    for _ in range(n):
        r, b = push(b, face)
        log.append((face, r, b))
        print(f"  push {face}: {r} -> boulder at {b}", flush=True)
        if r != "moved":
            break
    if log[-1][1] != "moved":
        break
rig.screenshot("vr1f_plate")
print("boulder now at", b, "bodies", sorted(bodies()), flush=True)
rig.bank("vr_1f_plate")
# the cliff gaps: step into (4,9) from (5,9) and (4,4) from (5,4)
gaps = {}
for gap, stand, face in (((4, 9), (5, 9), "left"), ((4, 4), (5, 4), "left")):
    r = walk_to(stand)
    if r == "reached":
        before = rig.pos()
        rig.io.press(face, hold=16, release=16)
        rig.ctl.wait(40)
        drain()
        gaps[gap] = "open" if rig.pos() != before else f"shut ({rig.textbox()[:40]!r})"
    else:
        gaps[gap] = f"stand {r}"
    print(f"  gap {gap}: {gaps[gap]}", flush=True)
r = walk_to((1, 1))
print("to the stair (1,1):", r, rig.pos(), flush=True)
journal(
    f"map=108 VR 1F: boulder (7,5) pushed to {b} ({log[-1]}); cliff gaps {gaps}; stair (1,1) walk={r}; pos {rig.pos()}"
)
if rig.pos()[0] == 194 or rig.pos()[1:] == (1, 1):
    for _ in range(3):
        if rig.pos()[0] == 194:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
    if rig.pos()[0] == 194:
        rig.bank("vr_2f_landing")
        print("*** VR 2F -- banked vr_2f_landing ***", rig.pos(), sorted(bodies()), flush=True)
print("final", rig.pos(), flush=True)
