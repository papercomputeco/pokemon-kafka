"""Mansion B1F after its (18,25) switch: route AROUND the doors it shut, test (26,17)/(27,17), take the SECRET KEY."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/mansion_216_pressed.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
blocked = {(16, 16), (17, 16)}  # shut by 216's (18,25) switch (step (17,17)->(17,16) refused)


def journal(content):
    row = {
        "referenced_time": datetime.now(timezone.utc).isoformat(),
        "priority": "important",
        "content": content,
        "source_session": "extractor",
    }
    append_observations("pokedex/memory", [row], dedupe=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def follow(mp, goals, cap=200):
    """Walk the ROM path one press at a time; a refused step is a door -- block it and re-plan."""
    goals = set(goals)
    stuck = 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp:
            return False
        if (x, y) in goals:
            return True
        path = rt.path_on_map(TRUTH, PAIRS, mp, (x, y), goals, blocked=set(blocked))
        if not path or len(path) < 2:
            print("   no path from", (x, y), "avoiding", sorted(blocked), flush=True)
            return False
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=8, release=8)
        rig.ctl.wait(30)
        drain()
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:  # three refusals in a row from the same cell: a door, not a body
                print(f"   refused {(x, y)} -> {(nx, ny)}; blocking it", flush=True)
                blocked.add((nx, ny))
                stuck = 0
            else:
                rig.ctl.wait(60)
        else:
            stuck = 0
    return False


def test_door(stand, face):
    if not follow(216, {stand}):
        return None
    before = rig.pos()
    rig.io.press(face, hold=16, release=16)
    rig.ctl.wait(40)
    drain()
    return rig.pos() != before


print("start", rig.pos(), flush=True)
res = {}
for stand, face in (((26, 18), "up"), ((27, 18), "up")):
    res[stand] = test_door(stand, face)
    print(f"door above {stand}: {res[stand]}", flush=True)
    if res[stand]:
        break
journal(
    f"map=216 after the (18,25) switch: (17,17)->(17,16) refused (shut), route west via (13,22); "
    f"doors above (26,18)/(27,18): {res}"
)
if any(res.values()):
    rig.bank("mansion_216_top")
    print("to the key room:", follow(216, {(5, 12), (4, 13), (6, 13), (5, 14)}), rig.pos(), flush=True)
    if rig.bag_full():
        print("make_room:", rig.make_room(), flush=True)
    names = [n for n, _ in rig.bag_named(full=True)]
    got = rig.collect_item(5, 13)
    names2 = [n for n, _ in rig.bag_named(full=True)]
    print("collect (5,13):", got, "| new:", [n for n in names2 if n not in names], flush=True)
    rig.screenshot("secret_key")
    if any("SECRET KEY" in n for n in names2):
        rig.bank("secret_key")
        print("*** SECRET KEY IN THE BAG ***", rig.pos(), flush=True)
        journal(
            f"map=216 SECRET KEY collected at (5,13); banked secret_key.state at {rig.pos()}; "
            f"doors blocked on the way: {sorted(blocked)}"
        )
    else:
        print("said:", repr(rig.textbox()), "blocked:", sorted(blocked), flush=True)
        journal(f"map=216 key NOT collected: pos {rig.pos()}, blocked {sorted(blocked)}, said {rig.textbox()!r}")
print("final", rig.pos(), "blocked", sorted(blocked), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
