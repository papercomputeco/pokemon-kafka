"""From secret_key_out.state, exit the mansion and walk to the Cinnabar gym door."""

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

# Exit mansion via right side
print("walking to (26,27)...", flush=True)
drain()
rig.walk(165, {(26, 27)}, battle=rig.battle)
print("at", rig.pos(), flush=True)
if rig.pos()[1:] == (26, 27):
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(70)
    drain()
    print("after exit:", rig.pos(), flush=True)

if rig.pos()[0] == 8:
    rig.bank("secret_key_cinnabar")
    print("on Cinnabar, walking to gym door (18,3)...", flush=True)
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
