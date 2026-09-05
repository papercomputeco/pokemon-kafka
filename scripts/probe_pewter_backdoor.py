"""Pewter's second museum door (19,5): the back lane (row 6) lies behind a one-way ledge and the Cut growths
(0x50) at (24..27,3); from (24,2) CUT down, walk the lane to (19,6), UP into the door, talk to the east half's
bodies. What they say is the record. Banks pewter_museum_back."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/pewter_museum_paid.state"
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


def settle():
    for _ in range(3):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
        rig.ctl.press("b")
        rig.ctl.wait(20)


def bodies():
    return {tuple(b[:2]) for b in rig.bodies()}


def navigate(mp, goals, cap=300, opens=()):
    m = TRUTH["maps"][str(mp)]
    for x, y in opens:
        row = list(m["grid"][y])
        row[x] = "1"
        m["grid"][y] = "".join(row)
    goals, blocked, stuck = set(goals), set(), 0
    for _ in range(cap):
        settle()
        cm, x, y = rig.pos()
        if cm != mp:
            return ("left-map", (cm, x, y))
        if (x, y) in goals:
            return ("reached", (x, y))
        path = rt.path_on_map(TRUTH, PAIRS, mp, (x, y), goals, blocked=(bodies() - goals) | blocked)
        if not path or len(path) < 2:
            return ("no-path", (x, y))
        nx, ny = path[1]
        dx, dy = nx - x, ny - y
        rig.io.press(K[(dx // abs(dx) if dx else 0, dy // abs(dy) if dy else 0)], hold=12, release=8)
        rig.ctl.wait(40 if abs(dx) + abs(dy) == 2 else 24)
        if rig.pos()[0] != mp:
            return ("left-map", rig.pos())
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
                print(f"  refused {(x, y)}->{(nx, ny)}", flush=True)
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


print("start", rig.pos(), flush=True)
settle()
if rig.pos()[0] == 52:  # out by the front mats: a mat warps on the second press
    navigate(52, {(10, 6)})
    for _ in range(4):
        if rig.pos()[0] != 52:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
    print("outside:", rig.pos(), flush=True)
r = navigate(2, {(27, 4)})
print("to (27,4) beside the 0x3D bush at (26,4):", r, rig.pos(), flush=True)
if rig.pos()[1:] == (27, 4):
    who = rig.knows_move("CUT")
    if who not in (None, 0):  # the roster shows nicknames (the lead reads "AAAAAAAAAA"), so name matching fails:
        print(
            "lead_swap ->", rig.lead_swap(who), [n for n, _l, _h in rig.party()], flush=True
        )  # make the cutter the lead
        settle()
        navigate(2, {(27, 4)})
    rig.io.press("left", hold=4, release=8)
    rig.ctl.wait(16)
    ok = rig.use_field_move("CUT")
    rig.ctl.wait(60)
    for _ in range(4):
        rig.ctl.press("a")
        rig.ctl.wait(40)
    for _ in range(6):
        rig.ctl.press("b")
        rig.ctl.wait(25)
    rig.io.press("left", hold=12, release=8)
    rig.ctl.wait(30)
    if rig.pos()[1:] != (26, 4):
        ok = rig.cut("left")
    settle()
    print("CUT left through the 0x3D bush (26,4):", ok, rig.pos(), flush=True)
    journal(f"map=2 Pewter: CUT the 0x3D bush at (26,4) from (27,4): {ok}; pos {rig.pos()}")
    r = navigate(2, {(19, 6)}, opens=[(26, 4)])
    print("to the back door's step (19,6):", r, rig.pos(), flush=True)
    if rig.pos()[1:] == (19, 6):
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
        print("back door (19,5):", rig.pos(), flush=True)
if rig.pos()[0] == 52:
    rig.bank("pewter_museum_back")
    said = {}
    for b in sorted(bodies()):
        if b[0] < 12:
            continue
        for stand, face in (
            ((b[0], b[1] + 1), "up"),
            ((b[0] - 1, b[1]), "right"),
            ((b[0] + 1, b[1]), "left"),
            ((b[0], b[1] - 1), "down"),
        ):
            navigate(52, {stand})
            if rig.pos()[1:] == stand:
                said[b] = rig.talk(face)
                settle()
                print(f"  east body {b}: {said[b][:140]!r}", flush=True)
                break
        else:
            print(f"  east body {b}: no stand reached", flush=True)
    journal(f"map=52 museum east half (back door (19,5)): bodies said {said}")
    rig.screenshot("museum_east")
print("final", rig.pos(), flush=True)
