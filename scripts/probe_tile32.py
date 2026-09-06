"""Is tile 0x32 surfable? Route 21 (map 32) has a column of it at x=4 beside the x=5 water column;
Route 20's tile model splits its sea at a column of it (x=62), so the answer decides whether the
31 -> 30 crossing exists in the model. Boots probe_r21.state (banked on the 8->32 edge; it reads
as Cinnabar (8, 11, 0) on reload), crosses north into 32, boards the water, surfs to (5, y) and
presses left into the 0x32 column, reading the position and the text box.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
import road  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/probe_r21.state", live_label="probe — is tile 0x32 surfable")
io, truth = rig.io, rig.truth
print("start", rig.pos(), "text", repr(rig.textbox()), flush=True)
for _ in range(4):
    io.press("b")
    io.wait(20)
if rig.pos()[0] == 8:
    print("cross 8->32 ->", rig.cross(8, 32), "at", rig.pos(), flush=True)
if rig.pos()[0] != 32:
    print("NOT ON MAP 32 — probe invalid", rig.pos(), flush=True)
    rig.finish(outcome="probe tile 0x32: not on 32", goals="surfable?")
    sys.exit(1)
m = truth["maps"]["32"]


def step(k):
    io.press(k, hold=15, release=15)
    io.wait(45)
    if io.read(ADDR_IN_BATTLE):
        rig.battle()
        io.press(k, hold=15, release=15)
        io.wait(45)
    return rig.pos()


mp, x, y = rig.pos()
print("on water per model:", road._water_model(m, x, y), "tile", m["tiles"][y][2 * x : 2 * x + 2], flush=True)
if not road._water_model(m, x, y):
    ok = road._board_water(io, truth, rig.pairs, 32, 0, rig._arm_surf, rig.battle)
    print("board water ->", ok, "at", rig.pos(), flush=True)
mp, x, y = rig.pos()
prev = road._water_reach(m, x, y, set())
tgt = (5, 11)
print("water route to", tgt, "exists:", tgt in prev, flush=True)
if tgt in prev:
    path = [tgt]
    while prev[path[-1]] is not None:
        path.append(prev[path[-1]])
    path.reverse()
    for a, b in zip(path, path[1:]):
        k = "right" if b[0] > a[0] else "left" if b[0] < a[0] else "down" if b[1] > a[1] else "up"
        now = step(k)
        if now[0] != 32 or now[1:] != b:
            print("  refused", k, "at", now, repr(rig.textbox()), flush=True)
            break
print("at", rig.pos(), flush=True)
for row in (11, 10, 3):
    mp, x, y = rig.pos()
    if mp != 32 or x != 5:
        break
    while rig.pos()[2] != row:
        before = rig.pos()
        step("up" if row < rig.pos()[2] else "down")
        if rig.pos() == before:
            print("  cannot reach row", row, "from", before, flush=True)
            break
    before = rig.pos()
    now = step("left")
    tile = m["tiles"][row][8:10]
    print(f"row {row}: {before} -left-> {now}  tile at (4,{row})={tile} text={rig.textbox()!r}", flush=True)
    if now[1:] != before[1:]:
        print("0x32 IS passable while surfing", flush=True)
        step("right")
rig.finish(outcome="probe tile 0x32", goals="surfable?")
