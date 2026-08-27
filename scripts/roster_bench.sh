#!/usr/bin/env bash
# Roster-engine benchmark (2026-08-26): measured rows for the quartermaster and the catalog.
#
#   scripts/roster_bench.sh          # ~15 min, writes rows to data/local_runs/roster-bench/
#
# Three elements, three row families — engine rows (deterministic harness capability), not model
# rows; the operator leg that tests whether a MODEL wields these tools is a separate matrix slot.
#
#   SUPPLY   the mart+heal errand from the same Cerulean seed, 3 reps: wall seconds, money delta,
#            bag delta, post-heal HP — and whether the reps agree (a settle-loop that isn't
#            deterministic would show here first).
#   CATCH    the opportunistic catch across Route 4's grass band, 4 stagings (different tiles =
#            different encounter RNG): encounters met, catches landed, balls spent, turns.
#   CATALOG  the encounter scan over every stream on the box, twice: wall seconds and whether
#            the two catalogs agree (aggregation must be a pure function of the streams).
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$REPO/data/local_runs/roster-bench"
mkdir -p "$OUT"
LOG="$OUT/bench.log"
say() { echo "[roster-bench $(date -u +%H:%M:%SZ)] $*" | tee -a "$LOG"; }

read_state() { # $1=state -> "money=N balls=N potions=N party=species:lv:hp/max,... "
  uv run python - "$1" <<'EOF' 2>/dev/null | tail -1
import sys
sys.path.insert(0, "scripts")
from pyboy import PyBoy

import quartermaster as qm
from memory_reader import SPECIES_ID_MAP

pb = PyBoy("rom/pokemon_red.gb", window="null")
with open(sys.argv[1], "rb") as f:
    pb.load_state(f)
io = qm.EmuIO(pb)
bag = dict(qm.read_bag(io))
party = ",".join(
    f"{SPECIES_ID_MAP.get(p['species'], hex(p['species']))}:L{p['level']}:{p['hp']}/{p['max_hp']}"
    for p in qm.read_party(io)
)
print(f"money={qm.read_money(io)} balls={sum(bag.get(b,0) for b in qm.BALL_IDS)} "
      f"potions={bag.get(qm.POTION,0)} party={party}")
pb.stop()
EOF
}

say "=== roster-engine bench start @ $(git -C "$REPO" rev-parse --short HEAD) ==="

# Seed: the deterministic 96-turn drive from the Mt. Moon baton into Cerulean.
if [ ! -f "$OUT/cerulean.state" ]; then
  say "seeding cerulean.state (route4_east baton -> map 3)"
  uv run python scripts/agent.py rom/pokemon_red.gb \
    --load-state demo-runs/states/mtmoon_seeds/route4_east_hp25.state \
    --max-turns 3000 --stop-on-map 3 --save-state-on-map "3:$OUT/cerulean.state" \
    --output-json "$OUT/seed_fit.json" --no-self-heal >>"$LOG" 2>&1
fi
say "seed: $(read_state "$OUT/cerulean.state")"

say "--- SUPPLY: errand x3 from the same seed ---"
for i in 1 2 3; do
  t0=$(date +%s)
  uv run python scripts/quartermaster.py errand --state "$OUT/cerulean.state" \
    --out "$OUT/supplied_$i.state" --buy poke_ball=6,potion=4 --heal >>"$LOG" 2>&1
  rc=$?
  say "SUPPLY rep $i: rc=$rc wall=$(( $(date +%s) - t0 ))s $(read_state "$OUT/supplied_$i.state")"
done

say "--- CATCH: 4 stagings across the grass band, --catch on the early-route wilds ---"
# One pre-grass state (east of the band, out of encounter range), then walk each lane to its own
# staging tile: the walk itself rolls the RNG differently per tile.
if [ ! -f "$OUT/pregrass.state" ]; then
  uv run python - <<EOF >>"$LOG" 2>&1
import sys
sys.path.insert(0, "scripts")
from pyboy import PyBoy

import quartermaster as qm
import rom_truth as rt

pb = PyBoy("rom/pokemon_red.gb", window="null")
with open("$OUT/supplied_1.state", "rb") as f:
    pb.load_state(f)
io = qm.EmuIO(pb)
truth = rt.load_truth()
pairs = rt.loaded_pairs(truth)
qm.walk_to(io, truth, pairs, 3, (0, 18))
for _ in range(4):
    if qm.read_pos(io)[0] == 15:
        break
    io.press("left"); io.wait(30)
qm.walk_to(io, truth, pairs, 15, (76, 10))
with open("$OUT/pregrass.state", "wb") as f:
    pb.save_state(f)
pb.stop()
EOF
fi
for x in 64 66 68 70; do
  uv run python - <<EOF >>"$LOG" 2>&1
import sys
sys.path.insert(0, "scripts")
from pyboy import PyBoy

import quartermaster as qm
import rom_truth as rt

pb = PyBoy("rom/pokemon_red.gb", window="null")
with open("$OUT/pregrass.state", "rb") as f:
    pb.load_state(f)
io = qm.EmuIO(pb)
truth = rt.load_truth()
qm.walk_to(io, truth, rt.loaded_pairs(truth), 15, ($x, 10))
with open("$OUT/stage_$x.state", "wb") as f:
    pb.save_state(f)
pb.stop()
EOF
  before=$(read_state "$OUT/stage_$x.state")
  timeout 300 uv run python scripts/agent.py rom/pokemon_red.gb \
    --load-state "$OUT/stage_$x.state" \
    --catch "Rattata,Spearow,Ekans,Sandshrew,Mankey,Oddish" \
    --max-turns 3000 --stop-on-map 3 --save-state-on-map "3:$OUT/caught_$x.state" \
    --output-json "$OUT/catch_fit_$x.json" --no-self-heal >>"$LOG" 2>&1
  turns=$(uv run python -c "import json; print(json.load(open('$OUT/catch_fit_$x.json')).get('turns','?'))" 2>/dev/null | tail -1)
  throws=$(grep -c 'CATCH |' "$LOG" || true)
  say "CATCH stage x=$x: turns=$turns before[$before] after[$(read_state "$OUT/caught_$x.state" 2>/dev/null || echo 'NO ARRIVAL')]"
done

say "--- CATALOG: full scan x2 ---"
for i in 1 2; do
  t0=$(date +%s)
  uv run python scripts/encounters.py scan --out "$OUT/catalog_$i.json" >>"$LOG" 2>&1
  say "CATALOG scan $i: wall=$(( $(date +%s) - t0 ))s rows=$(uv run python -c "
import json; c=json.load(open('$OUT/catalog_$i.json')); print(sum(len(v) for v in c['maps'].values()), c['events'])" | tail -1)"
done
if uv run python -c "
import json
a=json.load(open('$OUT/catalog_1.json')); b=json.load(open('$OUT/catalog_2.json'))
raise SystemExit(0 if (a['maps']==b['maps'] and a['types']==b['types']) else 1)"; then
  say "CATALOG: two scans agree (pure function of the streams)"
else
  say "CATALOG: SCANS DISAGREE — aggregation is not deterministic"
fi
say "recommend --vs water: $(uv run python scripts/encounters.py recommend --vs water --top 2 | head -2 | tr '\n' ';')"
say "=== roster-engine bench done ==="
