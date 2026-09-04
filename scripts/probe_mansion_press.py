"""Mansion 1F (165): the ROM says the stair pocket is connected, the live survey says it is not.
Find the frontier between the two, then press A on every distinct wall tile bordering the live
region and on every frontier cell -- a tileset-22 switch is a tile you face and press."""

import json
import sys
from collections import defaultdict

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import road  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

truth = json.load(open("references/rom_truth.json"))
m = truth["maps"]["165"]
survey = json.load(open("data/local_runs/roster-bench/survey_165.json"))
live = {tuple(c) for c in survey["cells"]}
rom = road.reachable(truth, rt.loaded_pairs(truth), 165, (6, 11))
tile = lambda x, y: m["tiles"][y][2 * x : 2 * x + 2]  # noqa: E731
D = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

frontier = []  # (live cell, facing, target) where the ROM calls the target walkable and the survey never stood there
walls = defaultdict(list)  # tile id -> [(live cell, facing)] for non-walkable neighbours
for x, y in sorted(live):
    for face, (dx, dy) in D.items():
        n = (x + dx, y + dy)
        if not (0 <= n[0] < m["width"] and 0 <= n[1] < m["height"]):
            continue
        if n in rom and n not in live:
            frontier.append(((x, y), face, n))
        elif m["grid"][n[1]][n[0]] != "1":
            walls[tile(*n)].append(((x, y), face))
print(f"live {len(live)} cells, ROM {len(rom)}; frontier steps: {len(frontier)} -> {frontier[:6]}", flush=True)
print("wall tile ids bordering the live region:", {k: len(v) for k, v in walls.items()}, flush=True)

rig = Rig("data/local_runs/roster-bench/mansion_1f.state", settle_on_boot=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def press_at(cell, face):
    drain()
    if rig.walk(165, {cell}, battle=rig.battle) is not True or rig.pos()[1:] != cell:
        return None
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(20)
    drain()
    rig.ctl.press("a")
    rig.ctl.wait(50)
    said = rig.textbox()
    rig.ctl.press("a")
    rig.ctl.wait(30)
    said2 = rig.textbox()
    drain()
    return (said + " | " + said2).strip(" |")


for tid, spots in sorted(walls.items(), key=lambda kv: -len(kv[1])):
    cell, face = spots[0]
    said = press_at(cell, face)
    print(f"tile 0x{tid} at {cell} facing {face}: {said!r}", flush=True)
    if said and "SWITCH" in said.upper():
        rig.screenshot(f"mansion_switch_0x{tid}")
for cell, face, target in frontier[:8]:
    said = press_at(cell, face)
    before = rig.pos()
    rig.io.press(face, hold=8, release=8)
    rig.ctl.wait(30)
    moved = rig.pos() != before
    print(f"frontier {cell} {face} -> {target} (0x{tile(*target)}): A says {said!r}; moved={moved}", flush=True)
    drain()
print("final", rig.pos(), flush=True)
