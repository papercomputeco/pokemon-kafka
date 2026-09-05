"""Index the banked batons: boot each .state once and record where it stands and what it carries.

    uv run python scripts/probe_baton_index.py [roster-bench dir] [out json]

Writes {name: {"map": m, "x": x, "y": y, "party": [[species, level, hp], ...], "bag": n}} so a
catalog sweep can pick, for any map, a save that already stands on it — without booting 700 states
again. Boots settled: five saves banked on warp pads reported the destination map when read
unsettled (measured 2026-09-05: 148 vs 147, 74 vs 17, 85 vs 22, 192 vs 31, 220 vs 156).
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

BENCH = Path(sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else BENCH / "index.json")

index: dict = json.loads(OUT.read_text()) if OUT.exists() else {}
states = sorted(BENCH.glob("*.state"))
t0 = time.time()
for i, path in enumerate(states, 1):
    if path.stem in index:
        continue
    try:
        rig = Rig(str(path), settle_on_boot=True)  # a save banked on a warp pad reads the wrong map unsettled
        mp, x, y = rig.pos()
        index[path.stem] = {
            "map": mp,
            "x": x,
            "y": y,
            "party": [list(p) for p in rig.party()],
            "bag": len(rig.bag()),
            "mtime": int(path.stat().st_mtime),
        }
        try:
            rig.pb.stop(save=False)
        except Exception:
            pass
    except Exception as exc:  # a corrupt or foreign state: record it, keep going
        index[path.stem] = {"error": str(exc)[:200]}
    if i % 10 == 0 or i == len(states):
        OUT.write_text(json.dumps(index, indent=1, sort_keys=True))
        print(f"{i}/{len(states)} {path.stem} -> {index[path.stem].get('map')} ({time.time() - t0:.0f}s)", flush=True)
OUT.write_text(json.dumps(index, indent=1, sort_keys=True))
print("wrote", OUT, len(index), "batons")
