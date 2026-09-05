"""Victory Road floor oracle: BFS over STRENGTH pushes with save-states; after every new boulder configuration try to
WALK to the target cell (the game decides what opened). Stands are planned with the tile-pair model, which measured
real on this tileset (1F refused (5,9)->(5,8), a 0x05->0x20 pair). argv: state, map, tx, ty, bank, [max pushes]."""

import io
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
STATE, MAP, TX, TY, BANK = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
MAXP = int(sys.argv[6]) if len(sys.argv) > 6 else 60
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
M = TRUTH["maps"][str(MAP)]


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


def boulders():
    return (
        sorted(tuple(b[:2]) for b in rig.bodies() if b[2] == 63)
        if rig.bodies() and len(next(iter(rig.bodies()))) > 2
        else sorted(tuple(b[:2]) for b in rig.bodies())
    )


def bodies():
    return {tuple(b[:2]) for b in rig.bodies()}


def walk_to(cell, cap=120):
    """Planner path (pairs honoured), pressed one step at a time; refused steps are learned as walls."""
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


def snap():
    b = io.BytesIO()
    rig.pb.save_state(b)
    return b.getvalue()


def load(blob):
    rig.pb.load_state(io.BytesIO(blob))
    rig.ctl.wait(10)


def key():
    return ";".join(f"{x},{y}" for x, y in boulders())


print("start", rig.pos(), "boulders", boulders(), "bodies", sorted(bodies()), flush=True)
drain()
who = rig.knows_move("STRENGTH")
print("STRENGTH:", rig.use_field_move("STRENGTH", species=rig.party()[who][0]), flush=True)
for _ in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(40)
drain()
root = snap()
seen = {key(): root}
frontier = [key()]
pushes = 0
won = None
tried = set()
# the target may already be open
if walk_to((TX, TY)) == "reached":
    won = key()
while frontier and pushes < MAXP and won is None:
    k = frontier.pop(0)
    for b in [tuple(map(int, c.split(","))) for c in k.split(";")]:
        for face, (dx, dy) in D.items():
            stand = (b[0] - dx, b[1] - dy)
            if (k, b, face) in tried:
                continue
            tried.add((k, b, face))
            load(seen[k])
            drain()
            if walk_to(stand) != "reached":
                continue
            rig.io.press(face, hold=4, release=8)
            rig.ctl.wait(16)
            drain()
            ok = rig.strength_push(face)
            pushes += 1
            drain()
            nk = key()
            moved = nk != k
            print(
                f"push {pushes}: {b} {face} from {stand}: moved={moved} -> {nk} said={rig.textbox()[:40]!r}", flush=True
            )
            if not moved or nk in seen:
                continue
            seen[nk] = snap()
            frontier.append(nk)
            r = walk_to((TX, TY))
            print(f"   target {(TX, TY)} from config {nk}: {r} at {rig.pos()}", flush=True)
            if r == "reached":
                won = nk
                break
            load(seen[nk])
        if won:
            break
print("pushes", pushes, "configs", len(seen), "won", won, flush=True)
journal(
    f"map={MAP} VR oracle: target {(TX, TY)} from {rig.pos()}: pushes {pushes}, configs {len(seen)}, "
    f"opening config {won}"
)
if won:
    load(seen[won])
    walk_to((TX, TY))
    rig.bank(f"{BANK}_open")
    print(f"*** at {(TX, TY)} on {MAP}; banked {BANK}_open ***", rig.pos(), flush=True)
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
