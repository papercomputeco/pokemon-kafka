"""Victory Road: walk to a target with named cells declared open (doors a plate opened), step through the warp.
argv: state map tx ty bank face ["x,y;x,y" open cells]."""

import json
import subprocess
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
PAIRS = rt.loaded_pairs(TRUTH)
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE, MAP, TX, TY, BANK, FACE = (
    sys.argv[1],
    int(sys.argv[2]),
    int(sys.argv[3]),
    int(sys.argv[4]),
    sys.argv[5],
    sys.argv[6],
)
OPEN = [tuple(map(int, c.split(","))) for c in sys.argv[7].split(";")] if len(sys.argv) > 7 and sys.argv[7] else []
AVOID = {tuple(map(int, c.split(","))) for c in sys.argv[8].split(";")} if len(sys.argv) > 8 else set()
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
M = TRUTH["maps"][str(MAP)]
for x, y in OPEN:
    row = list(M["grid"][y])
    row[x] = "1"
    M["grid"][y] = "".join(row)


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


def walk_to(cell, cap=200):
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
            return f"no-path (blocked {sorted(blocked)})"
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
                print(f"  wall {(x, y)}->{(nx, ny)}", flush=True)
        else:
            stuck = 0
    return "cap"


print("start", rig.pos(), "bodies", sorted(bodies()), flush=True)
drain()
r = walk_to((TX, TY))
print("walk:", r, rig.pos(), flush=True)
if rig.pos()[0] == MAP and rig.pos()[1:] == (TX, TY) and FACE in ("up", "down", "left", "right"):
    rig.io.press(FACE, hold=16, release=16)
    rig.ctl.wait(90)
    drain()
if rig.pos()[0] != MAP or rig.pos()[1:] == (TX, TY):
    rig.bank(BANK)
    print(f"*** {BANK}: {rig.pos()} bodies {sorted(bodies())} ***", flush=True)
else:
    rig.screenshot(f"vr{MAP}_walk_stuck")
print("final", rig.pos(), flush=True)
