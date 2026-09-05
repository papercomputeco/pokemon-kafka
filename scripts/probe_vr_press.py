"""Victory Road press survey: from the floor's reachable region, face every distinct wall tile id and every rare
tile (the mansion's method found its switches this way) and press A; record what the game says. argv: state, map."""

import json
import subprocess
import sys
from collections import defaultdict, deque

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
PAIRS = rt.loaded_pairs(TRUTH)
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE, MAP = sys.argv[1], int(sys.argv[2])
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
M = TRUTH["maps"][str(MAP)]


def tile(x, y):
    return int(M["tiles"][y][2 * x : 2 * x + 2], 16)


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


def region(start):
    seen, q = {start}, deque([start])
    solid = bodies()
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in seen or n in solid or not (0 <= n[0] < M["width"] and 0 <= n[1] < M["height"]):
                continue
            if M["grid"][n[1]][n[0]] == "1" and rt.passable(M, PAIRS, x, y, *n):
                seen.add(n)
                q.append(n)
    return seen


def walk_to(cell, cap=120):
    blocked, stuck = set(), 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != MAP:
            return False
        if (x, y) == cell:
            return True
        path = rt.path_on_map(TRUTH, PAIRS, MAP, (x, y), {cell}, blocked=(bodies() - {cell}) | blocked)
        if not path or len(path) < 2:
            return False
        nx, ny = path[1]
        rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
        rig.ctl.wait(24)
        drain()
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
    return False


def press(cell, face):
    if not walk_to(cell):
        return None
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(20)
    drain()
    pages = []
    for _ in range(3):
        rig.ctl.press("a")
        rig.ctl.wait(50)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
    drain()
    return " | ".join(pages)


print("start", rig.pos(), flush=True)
drain()
live = region(rig.pos()[1:])
print("pairs-aware region:", len(live), flush=True)
targets = defaultdict(list)  # tile id -> [(stand, face, cell)]
for x, y in sorted(live):
    for (dx, dy), face in K.items():
        n = (x + dx, y + dy)
        if not (0 <= n[0] < M["width"] and 0 <= n[1] < M["height"]) or n in live:
            continue
        targets[tile(*n)].append(((x, y), face, n))
said = {}
for tid, spots in sorted(targets.items()):
    common = tid in (0x10, 0x12, 0x2A, 0x1C, 0x17, 0x31)
    for stand, face, cell in spots[: 1 if common else 6]:
        s = press(stand, face)
        said[(hex(tid), cell)] = s
        if s:
            print(f"  tile {hex(tid)} at {cell} from {stand} {face}: {s!r}", flush=True)
talkers = {k: v for k, v in said.items() if v}
print("talking tiles:", talkers, flush=True)
silent = sorted(hex(t) for t in targets if not any(k[0] == hex(t) for k in talkers))
append_observations(
    "pokedex/memory",
    [
        {
            "referenced_time": "2026-09-05",
            "priority": "important",
            "source_session": "extractor",
            "content": f"map={MAP} Victory Road press survey ({len(live)} pairs-aware cells): talking tiles {talkers}; "
            f"silent tile ids {silent}",
        }
    ],
    dedupe=True,
)
print("final", rig.pos(), flush=True)
