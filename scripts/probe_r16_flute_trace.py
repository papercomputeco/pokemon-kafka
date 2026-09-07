"""Trace Rig.use_item("POKe FLUTE") on Route 16 beside the sleeper: every row it reads and the key
it compares, so the miss (run 20260907-022454-d545: "no bag item called 'POKe FLUTE'" with the
flute drawn at press 16 of the same list) is a sentence, not a guess.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
import expedition_rig as er  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_MENU_CUR  # noqa: E402

rig = Rig("data/local_runs/roster-bench/fly_won-27.state", live_label="probe — use_item trace at the sleeper")
io = rig.io
orig_key = er._menu_key
seen = []


def traced_key(text):
    k = orig_key(text)
    seen.append((io.read(ADDR_MENU_CUR), text, k))
    return k


er._menu_key = traced_key
orig_row = rig.window_row


def traced_row(row, cursor=False):
    t = orig_row(row, cursor=cursor)
    seen.append(("row", row, t))
    return t


rig.window_row = traced_row
io.press("left")
io.wait(25)
print("talk:", repr(rig.talk("left")), flush=True)
ok = rig.use_item("POKe FLUTE", face="left")
print("use_item ->", ok, flush=True)
for s in seen[:80]:
    print("  ", s, flush=True)
rig.finish(outcome=f"use_item trace {ok}", goals="flute")
