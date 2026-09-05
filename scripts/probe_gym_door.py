"""Load secret_key_out.state and walk to the Cinnabar gym door."""

import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig("data/local_runs/roster-bench/secret_key_out.state", settle_on_boot=True)


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


print("start", rig.pos(), "bag:", [n for n, _ in rig.bag_named(full=True)], flush=True)

# Walk out of the mansion to map 8 (Cinnabar)
# Exit is at bottom of 165: (4,27), (5,27), (6,27), (7,27)
# From (20,17), we need to navigate through 165 to the exit.
# The main area of 165 in state B has (24,13) open.
print("walking to exit...", flush=True)
for target in [(24, 12), (24, 13), (20, 27), (18, 27), (10, 27), (6, 27)]:
    drain()
    w = rig.walk(165, {target}, battle=rig.battle)
    print(f"  walk to {target}: {w} {rig.pos()}", flush=True)
    if rig.pos()[0] == 8:
        break

if rig.pos()[0] == 165:
    # Try stepping down through the exit
    for _ in range(3):
        if rig.pos()[0] == 8:
            break
        drain()
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(70)
        drain()
        print(f"  step down: {rig.pos()}", flush=True)

print("on map 8?", rig.pos(), flush=True)

if rig.pos()[0] == 8:
    rig.bank("secret_key_cinnabar")
    print("on Cinnabar, walking to gym door...", flush=True)
    drain()
    w = rig.walk(8, {(18, 4)}, battle=rig.battle)
    print("beside gym door:", w, rig.pos(), flush=True)
    if rig.pos()[1:] == (18, 4):
        before = rig.pos()
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
        said = rig.textbox()
        print("gym door said:", repr(said), flush=True)
        rig.screenshot("gym_door_with_key")
        journal(f"map=8 gym door (18,3) with SECRET KEY in bag: pos {before}->{rig.pos()}, said {said!r}")
        if rig.pos()[0] == 166:
            rig.bank("gym7_inside")
            print("*** INSIDE CINNABAR GYM ***", flush=True)

print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
