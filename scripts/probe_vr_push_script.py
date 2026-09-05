"""Victory Road: push one boulder along a scripted sequence, then test cells and walk to a target.
argv: state map bx by "face:n,face:n,..." tx ty bank [probe cells "x,y;x,y"]. Every push judged by the sprite table."""

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
STATE, MAP = sys.argv[1], int(sys.argv[2])
B0 = (int(sys.argv[3]), int(sys.argv[4]))
SCRIPT = [(s.split(":")[0], int(s.split(":")[1])) for s in sys.argv[5].split(",")]
TX, TY, BANK = int(sys.argv[6]), int(sys.argv[7]), sys.argv[8]
PROBE = [tuple(map(int, c.split(","))) for c in sys.argv[9].split(";")] if len(sys.argv) > 9 and sys.argv[9] else []
OPEN = [tuple(map(int, c.split(","))) for c in sys.argv[10].split(";")] if len(sys.argv) > 10 and sys.argv[10] else []
AVOID = (
    {tuple(map(int, c.split(","))) for c in sys.argv[11].split(";")} if len(sys.argv) > 11 and sys.argv[11] else set()
)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
for _x, _y in OPEN:  # doors a plate already opened: floor to the planner
    _row = list(TRUTH["maps"][str(MAP)]["grid"][_y])
    _row[_x] = "1"
    TRUTH["maps"][str(MAP)]["grid"][_y] = "".join(_row)


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


def drain(n=3):
    """Bounded: the window text is stale after menus (measured 'OPTION EXIT' while steps worked), so the verdict is
    the battle flag plus a couple of B presses, never the text."""
    for _ in range(n):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
        rig.ctl.press("b")
        rig.ctl.wait(20)


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
        path = rt.path_on_map(TRUTH, PAIRS, MAP, (x, y), {cell}, blocked=(bodies() - {cell}) | blocked | AVOID)
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
                print(f"    refused {(x, y)}->{(nx, ny)} said={rig.textbox()[:40]!r}", flush=True)
        else:
            stuck = 0
    return "cap"


def close_menus():
    for _ in range(6):
        rig.ctl.press("b")
        rig.ctl.wait(25)
    drain()


def push(boulder, face):
    dx, dy = D[face]
    if boulder not in bodies():  # re-sync from the sprite table: the last push may have landed after the read
        near = sorted(bodies(), key=lambda b: abs(b[0] - boulder[0]) + abs(b[1] - boulder[1]))
        if near and abs(near[0][0] - boulder[0]) + abs(near[0][1] - boulder[1]) <= 2:
            boulder = near[0]
    stand = (boulder[0] - dx, boulder[1] - dy)
    r = walk_to(stand)
    if r != "reached":
        return f"stand {stand} {r}", boulder
    new = (boulder[0] + dx, boulder[1] + dy)
    for attempt in range(4):  # STRENGTH is already active: a 16-frame hold is the measured push
        drain()
        if rig.pos()[1:] != stand and walk_to(stand) != "reached":  # a wild fight can move the turn along
            continue
        rig.io.press(face, hold=4, release=8)
        rig.ctl.wait(16)
        drain()
        close_menus()
        rig.io.press(face, hold=16, release=16)
        rig.ctl.wait(90)
        drain()
        rig.ctl.wait(20)
        if new in bodies() and boulder not in bodies():
            return "moved", new
    return f"refused ({rig.textbox()[:40]!r})", boulder


print("start", rig.pos(), "bodies", sorted(bodies()), flush=True)
drain()
if "MAX REPEL" in dict(rig.bag_named(full=True)):
    print("MAX REPEL:", rig.use_item("MAX REPEL"), flush=True)
    for _ in range(4):
        rig.ctl.press("a")
        rig.ctl.wait(40)
    close_menus()
who = rig.knows_move("STRENGTH")
rig.use_field_move("STRENGTH", species=rig.party()[who][0])
for _ in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(40)
close_menus()
print("bodies after setup:", sorted(bodies()), flush=True)
b, log, ok = B0, [], True
for face, n in SCRIPT:
    for _ in range(n):
        r, b = push(b, face)
        log.append(f"{face}:{r}->{b}")
        print(f"  push {face}: {r} -> {b}", flush=True)
        if r != "moved":
            ok = False
            break
    if not ok:
        break
rig.screenshot(f"vr{MAP}_script")
rig.bank(f"{BANK}_pushed")
probes = {}
for cell in PROBE:
    for (dx, dy), face in K.items():
        stand = (cell[0] - dx, cell[1] - dy)
        if walk_to(stand) == "reached":
            before = rig.pos()
            rig.io.press(face, hold=16, release=16)
            rig.ctl.wait(40)
            drain()
            probes[cell] = "open" if rig.pos() != before else "shut"
            break
    else:
        probes[cell] = "no stand"
    print(f"  probe {cell}: {probes[cell]}", flush=True)
r = walk_to((TX, TY))
print(f"to {(TX, TY)}: {r} at {rig.pos()}", flush=True)
journal(f"map={MAP} push script {B0} {SCRIPT}: {log}; probes {probes}; target {(TX, TY)} {r}")
if r == "reached":
    rig.bank(BANK)
    print(f"*** {BANK} banked at {rig.pos()} ***", flush=True)
print("final", rig.pos(), flush=True)
