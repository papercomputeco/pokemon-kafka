Model: Opus 4.6

# Log 2: Getting Past the Intro

**Model:** GPT-5 Codex

## How Host-Guest File Sharing Works

When the sandbox starts, `jcard.toml` defines a shared directory:

```toml
[[shared]]
host = "./"
guest = "/workspace"
readonly = false
```

This mounts the host directory (`/Users/bdougie/code/pokemon/`) into the VM at `/workspace` using a shared filesystem (virtio-fs or 9p). It's bidirectional — files written by the guest at `/workspace/frames/turn10.png` appear instantly on the host at `./frames/turn10.png`. Same filesystem, two views.

That's why:
- We SSH into the VM and run `python3 scripts/agent.py` — it reads the ROM from `/workspace/rom/` (host files)
- The agent writes screenshots to `/workspace/frames/` — they appear on the host at `./frames/`
- We can `Read` the PNG files from the host path without copying anything

The permission errors we hit earlier (install.sh, ROM .ram save file) happened because the host files were owned by macOS UID 501 with `600` permissions, but the VM runs as `admin` (different UID). We fixed script/source files with `chmod a+r` on the host, but the ROM directory still blocks writes — which is why PyBoy's `.ram` save fails at shutdown.

## What We Tried to Get Past the Intro

### Attempt 1: 20 A-presses, 30-frame delay
- Result: Stuck on Oak's opening speech ("My name is OAK!")
- Problem: Way too few A-presses for the full intro

### Attempt 2: 300 A-presses, 10-frame delay + periodic down
- Result: Got to Oak's lab (map 40), saw dialogue "...Okay! It's"
- Problem: Not enough frames between presses — game text scrolls slowly, inputs were lost

### Attempt 3: 300 A-presses, 10-frame delay (with overworld A-press fix)
- Result: Same lab scene, dialogue cycling but agent not interacting with Pokeball table
- Problem: Navigator waypoints for Oak's lab had wrong coordinates

### Attempt 4: 600 A-presses, 30-frame delay
- Result: Landed in bedroom (map 38, pos 3,6) — intro completed
- Problem: Agent pressed directions but player never moved

### Attempt 5: Added cycling direction pattern, removed indoor waypoints
- Result: Still stuck at (3,6) for 2000 turns
- Problem: Not a navigation logic issue — button inputs weren't registering

### Attempt 6: Diagnostic script
- Key finding: Raw PyBoy calls with 20-frame hold DO move the player (3,6 → 3,7)
- The agent's `GameController.press()` used only 8-frame hold + 4-frame release — too fast for the game to register directional input

### Attempt 7: Increased hold_frames from 8→20, release from 4→10
- Result: Still stuck at (3,6)
- Problem: The `run_overworld()` method has an `if turn_count % 3 == 0: press A and return` gate that fires on every 3rd turn, and the other turns may still have timing issues with the added `wait(16)` after movement

## Current Status

The agent successfully:
- Boots the ROM headlessly in stereOS
- Completes Oak's intro sequence (lands in bedroom)
- Takes screenshots every 10 turns to `frames/`
- Reads memory addresses correctly (map ID, position, badges, party)

The agent fails to:
- Move the player character reliably (frame timing issue)
- Navigate the early game scripted sequences (bedroom → leave town → Oak's lab → pick starter)

## Root Causes Identified

1. **Frame timing**: GameController.press() needs longer hold times. The diagnostic proved 20-frame hold works with raw PyBoy calls, but the agent's controller flow (press + wait + next action) may have cumulative timing issues.

2. **The every-3rd-turn A-press gate**: On turn % 3 == 0, the agent presses A and returns immediately, skipping movement entirely. This means only 2 out of every 3 turns attempt movement, and those movement turns may also conflict with the A-press timing.

3. **No position-change detection**: The agent doesn't notice it's stuck. It should detect when position hasn't changed over N turns and try different approaches.

## Next Steps

- Simplify `run_overworld()` to just alternate: move, then A, move, then A
- Increase frame waits after directional input to 30+ frames
- Add stuck detection (if position unchanged for 20 turns, try random directions)
- Consider scripting the exact intro sequence rather than mashing
