"""Load secret_key_cinnabar.state and carefully read the gym door text."""

import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig("data/local_runs/roster-bench/secret_key_cinnabar.state", settle_on_boot=True)


def journal(content):
    row = {
        "referenced_time": datetime.now(timezone.utc).isoformat(),
        "priority": "important",
        "content": content,
        "source_session": "extractor",
    }
    append_observations("pokedex/memory", [row], dedupe=True)


def drain(limit=20):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


print("start", rig.pos(), "bag:", [n for n, _ in rig.bag_named(full=True)], flush=True)

# Ensure all text is drained
drain(30)
print("textbox after drain:", repr(rig.textbox()), flush=True)

# Walk to gym door
print("walking to (18,4)...", flush=True)
drain()
rig.walk(8, {(18, 4)}, battle=rig.battle)
print("at", rig.pos(), flush=True)

if rig.pos()[1:] == (18, 4):
    # Press UP but watch for text BEFORE warping
    drain()
    print("pressing up...", flush=True)
    rig.io.press("up", hold=4, release=8)
    rig.ctl.wait(40)
    # Check text multiple times
    for i in range(10):
        t = rig.textbox()
        print(f"  text check {i}: {t!r}", flush=True)
        if t:
            rig.screenshot("gym_door_text")
            journal(f"map=8 gym door (18,3) with SECRET KEY: said {t!r}")
            print("*** GYM DOOR TEXT CAPTURED ***", t, flush=True)
            break
        rig.ctl.wait(20)
    # Now let the warp happen
    rig.ctl.wait(60)
    drain()
    print("after warp:", rig.pos(), flush=True)
    if rig.pos()[0] == 166:
        print("*** INSIDE GYM ***", flush=True)

print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
