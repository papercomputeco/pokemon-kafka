"""With the SECRET KEY, outside 165's stairs pocket (parity 1: (24,13)/(25,13) shut): leave by the east column's
exits (26,27)/(27,27) -> map 8, then walk to the gym door (8 (18,3), stand (18,4) UP) and read what it says now.
"""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/secret_key_out.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
blocked: set = {(24, 13), (25, 13)}


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


def follow(mp, goals, cap=300):
    goals = set(goals)
    stuck = 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp:
            return False
        if (x, y) in goals:
            return True
        try:
            bodies = set(rig.bodies())
        except Exception:
            bodies = set()
        path = rt.path_on_map(TRUTH, PAIRS, mp, (x, y), goals, blocked=set(blocked) | (bodies - goals))
        if not path or len(path) < 2:
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
            if stuck >= 3:
                print(f"   refused {(x, y)} -> {(nx, ny)}; blocking it", flush=True)
                blocked.add((nx, ny))
                stuck = 0
            else:
                rig.ctl.wait(60)
        else:
            stuck = 0
    return False


def warp(mp, stand, key, want):
    if not follow(mp, {stand}):
        return False
    for _ in range(3):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(70)
        drain()
    return rig.pos()[0] == want


print("start", rig.pos(), flush=True)
print(
    "165 -> 8 by the east exits:",
    warp(165, (26, 26), "down", 8) or warp(165, (27, 26), "down", 8),
    rig.pos(),
    flush=True,
)
if rig.pos()[0] == 8:
    rig.bank("secret_key_cinnabar")
    journal(
        f"map=165 with (24,13)/(25,13) shut the east column's exits (26,27)/(27,27) lead to map=8 at {rig.pos()[1:]}"
    )
    blocked.clear()
    print("beside the gym door:", follow(8, {(18, 4)}), rig.pos(), flush=True)
    before = rig.pos()
    rig.io.press("up", hold=16, release=16)
    rig.ctl.wait(90)
    said = rig.textbox()
    print("gym door: now", rig.pos(), "said", repr(said), flush=True)
    rig.screenshot("gym_door_with_key")
    drain()
    journal(f"map=8 gym door (18,3) with the SECRET KEY in the bag: {before} -> {rig.pos()}, said {said!r}")
    if rig.pos()[0] == 166:
        rig.bank("gym7_inside")
        print("*** INSIDE THE CINNABAR GYM (166) ***", flush=True)
print("final", rig.pos(), "blocked", sorted(blocked), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
