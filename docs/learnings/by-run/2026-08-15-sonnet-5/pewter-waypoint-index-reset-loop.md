obstacle:      pewter-waypoint-index-reset-loop
category:      navigation
symptom:       Launching `pewter_to_badge` directly from the `forest_to_pewter` baton (a fresh
               `agent.py` process, `--load-state` landing mid-Pewter-City at (18,35), quest
               phase already `DONE`) sent every lane backward out of the city: `agent.log`
               showed `OVERWORLD | Map: 2 | Pos: (18,35) ... WP: 0→(13,25)` as the very first
               line, i.e. `Navigator.current_waypoint` started at 0 — the map's "Enter from
               forest" door coordinate — even though the party was already deep inside Pewter,
               well past that door. Walking back onto it re-triggered the door, and the
               parcel-quest phase logic (which derives its target purely from the *current* map,
               not from any persisted "already done this" state) correctly-but-expensively
               decided the way forward from Pallet Town is to re-walk the entire early game
               (Pallet → Viridian → Route 1 → Route 2 → Forest → Pewter), burning the whole
               turn budget before ever reaching the Gym. `report.json` showed both attempts
               (4000 and 8000 max_turns) ending with `final_map_id: 13` or `2`, badges 0, no
               baton produced.
failed:        (1) Re-running with double turns (relay's automatic retry) — no effect, since
               the lane wasn't slow, it was doing a full valid-but-wasteful backtrack every
               single time a fresh process started mid-map. (2) All 6 BATTLE_SPREAD variants —
               irrelevant, since none of them touch `Navigator.current_waypoint` or its
               map-change reset logic.
winner:        `Navigator.__init__` sets `self.current_map = None`; `next_direction`'s first
               call always sees `map_key != self.current_map` (true on process start) and used
               to unconditionally reset `current_waypoint = 0`. Added
               `Navigator._initial_waypoint_index(state)`, called only on that first-ever call
               (distinguished from later, in-session map-change resets, which still correctly
               reset to 0): it picks the nearest waypoint for the current map, by Manhattan
               distance from the actual load-state position, while skipping any waypoint whose
               `note` starts with "enter" (the map's entry/door marker, which is what actually
               caused the backward walk) — falling back to the entry waypoint only if every
               waypoint on that map is one. Genome diff: none — this is a `scripts/agent.py`
               code fix (`Navigator._initial_waypoint_index` + the `is_startup` branch in
               `next_direction`), not a variant tune. Verified in isolation: the very next probe
               run from the same baton logged `WP: 1→(19,17)` (the Pokemon Center waypoint) as
               its first line instead of `WP: 0→(13,25)`, and no full-game replay occurred in
               that run.
why it worked: A relay baton's `agent.py` process always starts fresh — the Python `Navigator`
               object has no memory of a *previous* segment's progress, only the emulator save
               state does. Blindly trusting waypoint index 0 assumes every fresh process begins
               adjacent to the map's entry point, which is only true for the FIRST segment that
               enters a map, never for a segment whose baton was captured well after entry (as
               `forest_to_pewter`'s stop-state was, once the lane had already wandered into the
               city). Nearest-by-distance is the right general fix once the entry-marked
               waypoint is deprioritized, since routes.json already documents which waypoints
               are map-entry markers (the "Enter from X" convention) versus real in-map
               destinations (Pokemon Center, Gym, Mart door, etc.) — this reuses that existing
               data convention rather than inventing new metadata.
generalizes:   Any relay segment whose baton lands a *fresh* agent.py process mid-map (which is
               every non-first segment touching a given map) should never trust waypoint index 0
               by construction — check `Navigator._initial_waypoint_index` behavior first before
               assuming the plain waypoint Navigator "just needs more turns." More generally:
               when a fresh process's first action after `--load-state` walks it BACKWARD out of
               where it already is (a map-boundary door, a "gate" tile, an "Enter from" marker),
               suspect stateless-on-process-restart logic (waypoint indices, quest phase
               counters, anything reset in `__init__` rather than derived from the save state)
               before touching genome knobs.
artifacts:     data/relay/seg3b/ and data/relay/seg3c/ (early pewter_to_badge attempts still
               showing the backward-replay symptom in report.json / agent.log). Code fix:
               scripts/agent.py (`Navigator._initial_waypoint_index`, `next_direction`'s
               `is_startup` branch). Probe confirming the fix: data/relay/seg3_probe2/,
               data/relay/seg3_probe3/ (first line `WP: 1→(19,17)`, no Pallet-Town replay).
