"""From mansion_catalog_end.state, test if (16,14) is reachable in state B."""

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig

rig = Rig("data/local_runs/roster-bench/mansion_catalog_end.state", settle_on_boot=True)
print("start", rig.pos(), flush=True)
print("walk to (16,14):", rig.walk(165, {(16, 14)}, battle=rig.battle), rig.pos(), flush=True)
