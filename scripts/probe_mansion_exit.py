"""With the SECRET KEY: reopen (26,17) by pressing (20,3) again, climb to 165's stairs pocket, and measure its doors
(20,17)/(21,17) from inside in both switch parities. If they open, leave the mansion and read the gym door (8 (18,3)).
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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/secret_key.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
blocked: set = set()


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
        bodies = set()
        try:
            bodies = set(rig.bodies())
        except Exception:
            pass
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


def press_switch(mp, stands):
    for stand, face in stands:
        if not follow(mp, {stand}):
            continue
        rig.io.press(face, hold=4, release=8)
        rig.ctl.wait(20)
        drain()
        pages = []
        for _ in range(5):
            rig.ctl.press("a")
            rig.ctl.wait(50)
            t = rig.textbox()
            if t and (not pages or t != pages[-1]):
                pages.append(t)
        drain()
        if any("switch" in p.lower() for p in pages):
            blocked.clear()
            return stand, pages
    return None


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


def pocket_doors():
    out = {}
    for stand in ((20, 18), (21, 18)):
        if not follow(165, {stand}):
            out[stand] = None
            continue
        before = rig.pos()
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(40)
        drain()
        out[stand] = rig.pos() != before
        if out[stand]:
            break
    return out


print("start", rig.pos(), "bag:", [n for n, _ in rig.bag_named(full=True)], flush=True)
parity = 1  # presses since the baton: 215 once, 216 (18,25) once, 216 (20,3) once
r = press_switch(216, (((20, 4), "up"), ((21, 3), "left"), ((20, 2), "down")))
print("216 (20,3) pressed again:", r, flush=True)
parity ^= 1 if r else 0
print("216 -> 165:", warp(216, (23, 21), "down", 165), rig.pos(), flush=True)
results = {}
for attempt in range(2):
    if rig.pos()[0] != 165:
        break
    d = pocket_doors()
    results[parity] = d
    print(f"165 pocket doors (parity {parity}): {d}", flush=True)
    if any(d.values()):
        break
    # flip the parity from B1F's nearest switch and come back
    if not warp(165, (21, 22), "down", 216):
        break
    r2 = press_switch(216, (((18, 26), "up"), ((18, 24), "down"), ((17, 25), "right"), ((19, 25), "left")))
    print("216 (18,25) pressed:", r2, flush=True)
    if not r2:
        break
    parity ^= 1
    print("216 -> 165:", warp(216, (23, 21), "down", 165), rig.pos(), flush=True)
journal(f"map=165 stairs-pocket doors (20,17)/(21,17) tested from INSIDE ((20,18)/(21,18) UP) by parity: {results}")
if rig.pos()[0] == 165 and any(any(v for v in d.values() if v) for d in results.values()):
    rig.bank("secret_key_out")
    print("*** OUT OF THE POCKET ***", rig.pos(), flush=True)
    print("165 -> 8:", warp(165, (5, 26), "down", 8), rig.pos(), flush=True)
    if rig.pos()[0] == 8:
        rig.bank("secret_key_cinnabar")
        ok = follow(8, {(18, 4)})
        print("beside the gym door:", ok, rig.pos(), flush=True)
        before = rig.pos()
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        said = rig.textbox()
        print("gym door: now", rig.pos(), "said", repr(said), flush=True)
        rig.screenshot("gym_door_with_key")
        drain()
        journal(f"map=8 gym door (18,3) with the SECRET KEY: pos {before}->{rig.pos()}, said {said!r}")
        if rig.pos()[0] == 166:
            rig.bank("gym7_inside")
            print("*** INSIDE THE CINNABAR GYM (166) ***", flush=True)
else:
    rig.bank("secret_key_pocket")
print("final", rig.pos(), "blocked", sorted(blocked), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
