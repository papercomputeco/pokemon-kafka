---
name: route1-speedrun-demo
description: Use when running a 5-minute live demo of the Pokemon Kafka agent. Reproduces a clean 20-battle Route 1 speedrun with real-time Confluent Cloud event streaming. Requires ROM, Confluent API keys, and uv.
---

# Route 1 Speedrun Demo

## Overview

Reproducible 5-minute demo: agent boots Pokemon Red, navigates to Route 1, grinds 20 battles, streams every event to Confluent Cloud in real-time. Audience sees the agent level from 5 to 10, fighting Rattata and Pidgey while telemetry flows into Kafka.

## Prerequisites

| Check | How to verify |
|-------|---------------|
| ROM | `ls rom/*.gb` — need Pokemon Red `.gb` file |
| Confluent keys | `echo $CONFLUENT_API_KEY` — must be SET |
| uv | `uv --version` |
| confluent-kafka | `uv run python -c "import confluent_kafka"` |
| config.toml | `cat config.toml` — `enabled = true`, correct bootstrap server |

If Confluent isn't configured, use the `confluent-cloud-setup` skill first.

## Demo Steps

### 1. Clean state

```bash
rm -f "rom/Pokemon - Red Version (USA, Europe) (SGB Enhanced).gb.ram"
rm -rf frames/
```

The `.gb.ram` file is a save state — if present, the title screen shows CONTINUE instead of NEW GAME and the intro sequence fails.

### 2. Patch routes.json for grass grinding

Replace the Route 1 entry in `references/routes.json` with a south-grass grind loop. This keeps the agent walking back and forth through tall grass below the y=25 ledge, triggering wild encounters without getting stuck on navigation.

```json
"12": {
  "name": "Route 1",
  "loop": true,
  "waypoints": [
    {"x": 5, "y": 33, "note": "Enter from Pallet Town — south grass"},
    {"x": 4, "y": 30, "note": "Walk north through grass"},
    {"x": 5, "y": 27, "note": "Top of south grass zone"},
    {"x": 4, "y": 30, "note": "Back south through grass"},
    {"x": 5, "y": 33, "note": "South end — loop back"},
    {"x": 4, "y": 30, "note": "North again through grass"},
    {"x": 5, "y": 27, "note": "Top of grind zone"},
    {"x": 4, "y": 30, "note": "South through grass"},
    {"x": 5, "y": 33, "note": "South end again"}
  ]
}
```

The `"loop": true` field requires the Navigator loop support (added alongside this skill). Without it, the agent exhausts waypoints and stops moving.

### 3. Add Navigator loop support

In `scripts/agent.py`, in the `Navigator.next_direction` method, change the waypoint-exhaustion check:

```python
# Before:
if self.current_waypoint >= len(waypoints):
    return None  # Route complete

# After:
is_loop = isinstance(route, dict) and route.get("loop", False)
if self.current_waypoint >= len(waypoints):
    if is_loop:
        self.current_waypoint = 0
    else:
        return None  # Route complete
```

### 4. Run the agent

```bash
uv run python scripts/agent.py \
  "rom/Pokemon - Red Version (USA, Europe) (SGB Enhanced).gb" \
  --battle-limit 20 \
  --save-screenshots \
  --telemetry-dir data/telemetry
```

Requires PRs merged:
- `fix/battle-timing` — prevents input spam during battle animations
- `feat/battle-limit` — `--battle-limit` flag
- `feat/realtime-confluent-publishing` — events stream during run

### 5. Expected output

| Metric | Expected |
|--------|----------|
| Battles won | 20 |
| Level-ups | ~4 (Lv5 to Lv10) |
| Encounters | Rattata (majority), Pidgey, 1 Bulbasaur (rival) |
| Turns | ~500-600 |
| Wall-clock time | ~10 seconds (headless) |
| Events to JSONL | ~190 |
| Confluent | No delivery errors in output |

Key log lines to watch for:
```
Battle ended. Total wins: 20
LEVEL UP | Lv9 -> Lv10
Battle limit reached (20). Stopping.
Session complete. Turns: 587 | Wins: 20
```

### 6. Verify Confluent

Check the `pokemon.game.events` topic in the Confluent Cloud UI — the Messages tab should show real-time events with `event_type` values: `battle`, `overworld`, `map_change`, `stuck`, `session`.

### 7. Cleanup

```bash
git checkout -- references/routes.json
git checkout -- scripts/agent.py
```

Revert the routes.json grind patch and Navigator loop — these are demo-only modifications.

## Talking Points

- **Headless PyBoy** runs at ~100x real-time — the full demo takes seconds
- **Every game event** (battles, movement, map changes, stuck detection) streams to Kafka in real-time
- **Type effectiveness** scoring drives battle decisions — the agent picks super-effective moves
- **Stuck detection** logs navigation failures as events — observable in the Confluent topic
- **Pokedex log** written to `pokedex/logNN.md` with full session summary

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Intro failed: still at map=0` | Delete `.gb.ram` save file |
| Stuck at y=24 on Route 1 | Routes.json not patched — agent hits the ledge |
| 0 events in Confluent | Real-time publishing PR not merged, or env vars not set |
| `SASL authentication error` | Check `$CONFLUENT_API_KEY` and `$CONFLUENT_API_SECRET` |
| Agent loops in battle forever | Battle timing PR not merged — frame waits too short |
