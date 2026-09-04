"""Fly to Fuchsia from Route 16 and bank; the HM03 hunt leg starts from there."""

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/fly_taught_outside.state", settle_on_boot=True)
print("start", rig.pos(), flush=True)
ok = rig.fly_to("FUCHSIA CITY")
print("fly_to Fuchsia:", ok, rig.pos(), flush=True)
rig.screenshot("after_fly")
if ok:
    rig.bank("fly_at_fuchsia")
