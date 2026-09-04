"""Live test of the map-31 (Route 20) west-pocket hypothesis.

Baton ``m31_manual.state`` stands at (44,12), inside the 49-cell water component the
static tile model calls a pocket. The model only proposes; the game answers. This probe
presses each direction once from the baton cell (state restored between tries), records
what moved, what the textbox said, and screenshots every refusal -- so the artifact is the
refusal sentence at the exact cell, not a guess.
"""

from __future__ import annotations

import io as _io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import expedition_rig  # noqa: E402

BATON = "data/local_runs/roster-bench/m31_manual.state"
DIRS = (("left", "west"), ("down", "south"), ("up", "north"), ("right", "east"))


def snap(rig) -> _io.BytesIO:
    buf = _io.BytesIO()
    rig.pb.save_state(buf)
    return buf


def main() -> int:
    rig = expedition_rig.Rig(BATON)
    if not rig.settle():
        print("BATON WOULD NOT SETTLE", flush=True)
    mp, x, y = rig.settled_pos()
    print(f"pos=({mp},{x},{y}) badges={rig.badges()} party={rig.party()}", flush=True)
    print(f"surf={rig.knows_move('SURF')}", flush=True)
    print(f"bag={rig.bag_named(full=True)}", flush=True)
    base = (mp, x, y)

    for key, name in DIRS:
        before = snap(rig)
        rig.ctl.press(key)
        rig.ctl.wait(40)
        try:
            rig.battle(rig.io)
        except Exception as exc:  # a wild cancelled the step; record and move on
            print(f"{name}: battle ({exc})", flush=True)
        here = rig.settled_pos()
        said = rig.textbox()
        moved = tuple(here) != base
        verdict = "MOVED" if moved else "REFUSED"
        print(f"{name:6s} {verdict:8s} from {base} -> {tuple(here)}  said: {said!r}", flush=True)
        if not moved and said:
            rig.say(said, "probe.refused")
            rig.screenshot(f"pocket_{name}_refused")
        before.seek(0)
        rig.pb.load_state(before)

    # The model's own water view from this cell: which component do we stand in, and what
    # are the four neighbours -- tile id, grid bit, component -- so the live answers above
    # line up with the static hypothesis cell for cell.
    m = rig.truth["maps"][str(mp)]
    tiles, grid = m["tiles"], m["grid"]

    def describe(x: int, y: int) -> str:
        return f"({x},{y}) tile={int(tiles[y][2 * x:2 * x + 2], 16):#04x} grid={grid[y][x]}"

    print("cell  :", describe(*base[1:]), flush=True)
    for key, name in DIRS:
        dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}[key]
        print(f"{name:6s}:", describe(base[1] + dx, base[2] + dy), flush=True)
    rig.emit("probe.route20_west", pos=list(base))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
