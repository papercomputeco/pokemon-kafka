---
name: pokemon-agent
description: "Play turn-based RPGs autonomously via Game Boy emulation. Use when the user asks to 'play pokemon', 'emulate a game boy game', 'automate pokemon battles', 'grind pokemon', 'run a pokemon nuzlocke', 'play an RPG for me', or mentions headless emulation, PyBoy, or turn-based game automation."
version: 0.1.0
metadata:
  { "openclaw": { "emoji": "🎮", "requires": { "bins": ["python3"], "env": [] }, "install": [{ "id": "pip", "kind": "node", "label": "Install PyBoy + dependencies (pip)" }] } }
---

# Pokemon Agent

Autonomous turn-based RPG player using headless Game Boy emulation via PyBoy.

## Overview

This skill runs a Game Boy / Game Boy Color ROM headlessly using PyBoy's Python API. The agent reads game state from emulator memory, makes strategic decisions (via LLM or heuristics), and sends button inputs back. No display server required — runs fully headless inside a terminal, container, or stereOS VM.

## Requirements

- Python 3.10+
- PyBoy (`pip install pyboy`)
- A legally obtained ROM file (`.gb` or `.gbc`)
- Optional: `Pillow` for screenshot capture and frame export

## Setup

Run the install script to set up the Python environment:

```bash
cd {baseDir}
bash scripts/install.sh
```

Place your ROM file in the skill directory or provide an absolute path when starting.

## Usage

### Start a game session

```
Play Pokemon Red for me
Start a new pokemon playthrough
Grind my team on Route 3
```

### Battle automation

```
Auto-battle wild encounters
Use the best move against the current opponent
Grind until my starter reaches level 16
```

### Navigation

```
Walk to Pewter City
Navigate to the next gym
Find and heal at the nearest Pokemon Center
```

## How It Works

### Game Loop

1. **Boot**: Launch PyBoy in headless mode (`window="null"`)
2. **Read state**: Extract game data from known memory addresses
3. **Decide**: Choose action based on current context (battle, overworld, menu)
4. **Act**: Send button inputs to the emulator
5. **Advance**: Tick the emulator forward, wait for state change
6. **Repeat**

### Memory Map (Pokemon Red/Blue)

The agent reads game state from these memory addresses:

| Address | Data |
|---------|------|
| `0xD057` | Battle type (0 = none, 1 = wild, 2 = trainer) |
| `0xCFE6` | Enemy current HP |
| `0xCFE7` | Enemy max HP |
| `0xD015` | Player lead Pokemon current HP (high byte) |
| `0xD016` | Player lead Pokemon current HP (low byte) |
| `0xD014` | Player lead Pokemon level |
| `0xD163` | Number of Pokemon in party |
| `0xD01C` | Player Pokemon move 1 ID |
| `0xD01D` | Player Pokemon move 2 ID |
| `0xD01E` | Player Pokemon move 3 ID |
| `0xD01F` | Player Pokemon move 4 ID |
| `0xD02C` | Player Pokemon move 1 PP |
| `0xD02D` | Player Pokemon move 2 PP |
| `0xD35E` | Current map ID |
| `0xD361` | Player X position |
| `0xD362` | Player Y position |
| `0xD31D` | Number of badges |
| `0xFF44` | Current scanline (use to detect vblank for frame sync) |

### Battle Strategy

When in battle (`0xD057 != 0`):

1. Read enemy HP and player HP
2. If player HP < 20% max → use best healing item
3. If all moves have PP → pick highest-power move with type advantage
4. If a move is super effective → always prefer it
5. If no PP remaining → use Struggle (auto-selected)
6. If player fainted → switch to next alive Pokemon
7. If all fainted → navigate to Pokemon Center after whiteout

### Overworld Navigation

When not in battle (`0xD057 == 0`):

1. Read current map ID and position
2. Follow a predefined route plan (stored in `references/routes.json`)
3. Move toward objective using cardinal directions
4. If grass tile → expect random encounter, ensure party is healthy
5. If at Pokemon Center → heal if any party member below 50%
6. If at objective → execute next story beat

### Input Mapping

Send inputs via PyBoy's button API:

```python
# Button press: hold for N frames then release
def press_button(pyboy, button, frames=10):
    pyboy.button(button)        # press
    for _ in range(frames):
        pyboy.tick()
    pyboy.button_release(button) # release
    pyboy.tick()

# Available buttons: "a", "b", "start", "select", "up", "down", "left", "right"
```

### Menu Navigation

Menus require sequenced button presses with frame delays:

- **Select FIGHT in battle**: Press `"a"` → wait 30 frames → cursor is on FIGHT
- **Move cursor down**: Press `"down"` → wait 10 frames
- **Confirm selection**: Press `"a"` → wait 30 frames
- **Cancel / go back**: Press `"b"` → wait 20 frames
- **Open start menu**: Press `"start"` → wait 30 frames

### Screenshot Capture

To capture the current frame for LLM vision analysis:

```python
from PIL import Image

screen = pyboy.screen.ndarray  # numpy array of current frame
img = Image.fromarray(screen)
img.save("current_frame.png")
```

## Running on stereOS

This skill is designed to run inside a stereOS VM via Master Blaster. See `references/jcard.toml` for the VM configuration.

```bash
mb init pokemon-agent
# Copy skill files into the project
mb up
mb attach  # watch the agent play
```

### Shared Mount Permissions

The `[[shared]]` mount maps the host repo to `/workspace` inside the VM. Host files retain their original ownership (UID 501 on macOS), but the VM runs as `admin` (UID 1000). Output directories (`frames/`, `pokedex/`, `.tapes/`) need world-writable permissions so the agent can write data that persists back to the host. The install script handles this automatically with `chmod a+rwx`.

### Tapes Telemetry

Tapes captures all LLM API calls made by the agent transparently — no instrumentation needed. Every battle decision, every route choice, every item use is logged with cryptographic audit trails.

The install script sets up Tapes automatically (`tapes init --preset anthropic`). The agent runs through `tapes start`, which proxies API calls and stores sessions in `.tapes/`.

After a run, inspect sessions:

```bash
tapes deck           # Terminal UI for session exploration
tapes search "battle" # Search session turns
tapes checkout <hash> # Restore a previous conversation state
```

### Observational Memory

Long agent runs hit context compaction — when the context window fills up, older messages are compressed and cache prefixes are destroyed. Tapes solves this by storing the full conversation in `.tapes/tapes.sqlite` regardless of what happens to the live context.

The observational memory system reads Tapes data and distills it into a lightweight observations file that the agent can load at session start. This gives the agent durable memory across compaction boundaries and between sessions.

**Session start:** Read `.tapes/memory/observations.md` to recall what happened in previous sessions — errors hit, files created, progress made. This is cheap to load and keeps the agent from repeating mistakes or rediscovering things it already learned.

**Session end:** Run the observer to extract observations from the current session into the memory file.

```bash
# Check observations from past sessions before starting
cat .tapes/memory/observations.md

# After a session, distill new observations
python3 scripts/observe_cli.py

# Preview what would be extracted without writing
python3 scripts/observe_cli.py --dry-run
```

Observations are tagged by priority:
- `[important]` — errors, crashes, bugs, security issues
- `[possible]` — tests added, refactors, dependency updates
- `[informational]` — session goals, token usage, general context

For long speed runs, the pattern is:
1. Load observations at session start for continuity
2. Play the game, making decisions informed by past sessions
3. Run the observer after the session to capture what happened
4. Next session picks up where this one left off, even if context was compacted

## File Structure

```
pokemon-agent/
├── SKILL.md              # This file
├── jcard.toml            # stereOS VM config
├── .tapes/               # Tapes telemetry DB + config (gitignored)
│   └── memory/           # Observational memory output
├── scripts/
│   ├── install.sh        # Setup script (installs PyBoy + Tapes)
│   ├── agent.py          # Main agent loop
│   ├── memory_reader.py  # Memory address utilities
│   ├── tape_reader.py    # Tapes SQLite reader
│   ├── observer.py       # Observation extraction heuristics
│   └── observe_cli.py    # Observer CLI
└── references/
    ├── routes.json        # Overworld route plans
    └── type_chart.json    # Pokemon type effectiveness
```

## Limitations

- ROM not included. You must supply your own legally obtained ROM.
- Memory addresses are specific to Pokemon Red/Blue (US). Other games or regions require adjusted offsets.
- Real-time games (action RPGs) are not supported — this is for turn-based only.
- PyBoy supports Game Boy and Game Boy Color. GBA requires a different emulator (mGBA with Python bindings).

## Extending

To support other turn-based RPGs:

1. Map the game's memory layout (use BGB debugger or similar)
2. Create a new memory reader module in `scripts/`
3. Adjust the battle strategy logic for the game's combat system
4. Update `routes.json` with the game's map structure
