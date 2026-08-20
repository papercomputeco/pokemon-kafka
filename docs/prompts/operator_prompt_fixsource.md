# Fix-source mission: one wall, one patch

You are the escalation tier of an expedition (docs/expedition-spec.md). A wall has eaten
repeated operator attempts; your job is the *fix*, not the run. Precedent: the Brock wall fell
to a 14-minute fix-source pass after four operator runs stopped at it.

## The wall

The `## Supervisor` section appended below this mission names the wall fingerprint (a map-pair
spring like `2<->58`, or a stall), the worktree holding the failed attempts' learnings and lane
logs, and — when the maps are routable — the ROM-truth hop chain past it.

## Ground rules

1. **Read before you write.** The failed attempts' `docs/learnings/*` and lane logs are the
   spec: they contain measured failures (what was tried, what it did). Do not re-run their
   experiments; cite their numbers.
2. **Consult ROM truth first.** `uv run python scripts/rom_truth.py route <src> <dst>` gives the
   real topology; `references/rom_truth.json` has every map's warps, connections, and collision
   grid. Most walls in this repo's history were topology guesses that a lookup refutes.
3. **Fix the general mechanism, not the tile.** The door-mat spring class has recurred on three
   buildings; a fix keyed to one coordinate will be back next map. Prefer `agent.py` mechanism
   fixes with the map data as data.
4. **Verify cheaply, then stop.** One short probe (`scripts/agent.py`, a few thousand turns) to
   show the wall no longer reproduces. Do not start relay campaigns; the expedition resumes the
   moment you commit.
5. **Deliverables:** committed code + tests green (`uv run pytest --cov` — CI holds 100 %), one
   learnings file naming the mechanism, and a one-paragraph summary. Commit as you go; an
   uncommitted diff is a lost diff.
