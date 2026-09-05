"""Capture gym door text by pressing UP and monitoring textbox until warp."""

import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
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


print("start", rig.pos(), "bag:", [n for n, _ in rig.bag_named(full=True)], flush=True)

# Walk to gym door
print("walking to (18,4)...", flush=True)
for _ in range(30):
    if rig.textbox():
        rig.ctl.press("b")
        rig.ctl.wait(24)
    else:
        break
rig.walk(8, {(18, 4)}, battle=rig.battle)
print("at", rig.pos(), flush=True)

if rig.pos()[1:] == (18, 4):
    # Press UP
    print("pressing up...", flush=True)
    rig.io.press("up", hold=4, release=8)
    # Poll textbox for up to 5 seconds
    captured = None
    for i in range(200):
        t = rig.textbox()
        if t and t != "Got away safely!":
            captured = t
            print(f"  NEW TEXT [{i}]: {t!r}", flush=True)
            rig.screenshot("gym_door_text")
            break
        if rig.pos()[0] == 166:
            print(f"  warped to 166 at frame {i}", flush=True)
            break
        rig.ctl.wait(3)

    if captured:
        journal(f"map=8 gym door (18,3) with SECRET KEY in bag: said {captured!r}")
    else:
        journal(
            f"map=8 gym door (18,3) with SECRET KEY in bag: warp fired before new text captured; pos now {rig.pos()}"
        )

    # If still on 8, warp hasn't fired yet; dismiss text and let it warp
    if rig.pos()[0] == 8:
        for _ in range(20):
            if rig.textbox():
                rig.ctl.press("b")
                rig.ctl.wait(24)
            else:
                break
        rig.ctl.wait(60)
        print("after text dismissal:", rig.pos(), flush=True)

print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
