"""Teach SURF to the four-move Gyarados on the merged branch and bank a baton that has both HMs usable."""

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/surf_strength_hm03.state", settle_on_boot=False)
who = rig.teach("HM03", "Gyarados")
surfer, strong = rig.knows_move("SURF"), rig.knows_move("STRENGTH")
print(f"teach -> {who} | surfer index: {surfer} | strength index: {strong} | party: {rig.party()}", flush=True)
if surfer is None:
    print("SURF did not land; not banking", flush=True)
    sys.exit(2)
rig.bank("surf_and_strength")
print("banked surf_and_strength at", rig.pos(), flush=True)
