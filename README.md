# Pokemon Agent

Autonomous Pokemon Red player that reads game memory, makes strategic decisions, and plays headlessly inside a stereOS VM.

## Architecture

```
stereOS VM (/workspace)
┌──────────────────────────────────────────────────┐
│                                                  │
│  PyBoy (headless, window="null")                 │
│    ↓ memory addresses                            │
│  MemoryReader → BattleState / OverworldState      │
│    ↓                                             │
│  Strategy Engine (heuristic or LLM)              │
│    ↓ button inputs                               │
│  GameController → PyBoy                          │
│                                                  │
│  Tapes ← proxies LLM API calls, records sessions │
│                                                  │
└──────────────────────────────────────────────────┘
  ↕ shared mount (./ ↔ /workspace)
Host: frames/  .tapes/  pokedex/
```

The agent runs a tight loop: read game state from known memory addresses, pick an action, send button inputs, tick the emulator forward. No display server needed. Screenshots come from PyBoy's internal frame buffer (`screen.ndarray`), not from the OS.

**Shared mount permissions.** The `[[shared]]` mount in `jcard.toml` maps `./` on the host to `/workspace` in the VM. Files keep their host ownership (UID 501 on macOS), but the VM runs as `admin` (UID 1000). This means host-created directories are read-only inside the VM by default. The install script opens write permissions on output directories (`frames/`, `pokedex/`, `.tapes/`) so the agent can write session data that persists back to the host.

## Quickstart

### stereOS (recommended)

```bash
mb up          # boot the VM, install deps, start the agent through Tapes
mb attach      # watch it play
```

The VM configuration lives in `jcard.toml`. It mounts the repo at `/workspace`, installs Python + PyBoy + Tapes, and runs the agent.

### Local

```bash
bash scripts/install.sh
python3 scripts/agent.py rom/pokemon_red.gb --strategy heuristic --max-turns 1000
```

Add `--save-screenshots` to capture frames every 10 turns into `frames/`.

> You must supply your own legally obtained ROM file in `rom/`.

## How It Works

**Game loop.** Each turn the agent ticks PyBoy forward, reads memory, decides, and acts. Turns are cheap. The agent runs hundreds of thousands of them to progress through the game.

**Memory reading.** `MemoryReader` pulls structured data from fixed addresses in Pokemon Red's RAM: battle type, HP, moves, PP, map ID, coordinates, badges, party state. These addresses are specific to the US release.

**Battle strategy.** When a battle is detected (`0xD057 != 0`), the agent evaluates available moves using a type effectiveness chart, picks the highest-damage option, and manages healing and switching. The heuristic strategy requires no API calls.

**Overworld navigation.** Outside battle, the agent follows waypoints defined in `references/routes.json`. It handles early-game scripted sequences (Red's room to Oak's lab) and general map-to-map routing. A stuck counter triggers random movement to break out of loops.

## Tapes Telemetry

Tapes proxies all LLM API calls made by the agent and records them with content-addressable session storage. The install script sets up Tapes automatically inside the VM.

After a run, inspect what happened:

```bash
tapes deck              # terminal UI for session exploration
tapes search "battle"   # search session turns
tapes checkout <hash>   # restore a previous conversation state
```

Session data lives in `.tapes/` (gitignored).

## Project Structure

```
pokemon-agent/
├── README.md                # this file
├── SKILL.md                 # skill definition for stereOS agents
├── jcard.toml               # stereOS VM configuration
├── .tapes/                  # Tapes telemetry DB + config (gitignored)
├── frames/                  # screenshot output (gitignored)
├── rom/                     # user-provided ROM files (gitignored)
├── scripts/
│   ├── install.sh           # setup: Python, PyBoy, Tapes
│   ├── agent.py             # main agent loop + strategies
│   └── memory_reader.py     # memory address definitions
├── references/
│   ├── routes.json          # overworld waypoints
│   └── type_chart.json      # type effectiveness data
└── pokedex/
    └── log1.md              # session log: stereOS setup notes
```

## Pokedex

The `pokedex/` directory contains session logs and development notes. Each log documents what happened during a run: setup blockers, fixes, observations about agent behavior. These serve as a record of how the project evolved and what the agent encountered.
