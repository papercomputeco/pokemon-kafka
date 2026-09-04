"""Cinnabar gym (166): read what the 0x4c wall tile at (1,13) says when pressed from (1,14) -- screenshot every page."""

import subprocess
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/badge7.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


print("start", rig.pos(), flush=True)
drain()
print("walk (1,14):", rig.walk(166, {(1, 14)}, battle=rig.battle), rig.pos(), flush=True)
rig.io.press("up", hold=4, release=8)
rig.ctl.wait(20)
drain()
for i in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(60)
    print(f"A#{i}: pos {rig.pos()} battle={rig.mem[qm.ADDR_IN_BATTLE]} text={rig.textbox()!r}", flush=True)
    rig.screenshot(f"gym7_machine_{i}")
    if rig.mem[qm.ADDR_IN_BATTLE]:
        break
print("final", rig.pos(), flush=True)
