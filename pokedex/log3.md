# Log 3: Overworld Loop Fix to Reach Professor Oak

**Model:** GPT-5 Codex

## Goal

The agent could finish the intro and land in Red's bedroom, but it was failing to move through the early game reliably enough to reach Professor Oak.

This pass focused on fixing the overworld loop in `scripts/agent.py` so movement is driven by game state instead of blind input mashing.

## Root Cause

The main problems in the old overworld loop were:

- Every 3rd turn, the agent pressed `A` and returned immediately
- Directional movement only waited 16 frames after input
- There was no stuck detection when position did not change
- The early game path to Oak relied on generic routes and exploration instead of known map targets

That meant the agent spent too many turns interacting when it should have been walking, and when walking failed, it had no recovery logic.

## Map Data Used

The early-game scripted targets were based on `pret/pokered` map object data:

- `RedsHouse2F`: warp at `(7, 1)` to go downstairs
- `RedsHouse1F`: front door warp at `(2, 7)` and `(3, 7)`
- `PalletTown`: Oak encounter triggers when the player reaches the north edge; Oak's lab entrance is at `(12, 11)`

For the agent, the practical movement targets added were:

- Map `38` (Red's bedroom) → move to `(7, 1)`
- Map `37` (Red's house 1F) → move to `(3, 7)`
- Map `0` (Pallet Town) → move toward `(8, 1)` to trigger Oak's interception

## Code Changes

### 1. Replaced blind overworld interaction

The old pattern:

- Press `A` every 3rd turn
- Otherwise try one movement input

The new pattern:

- Press `A` only when a text box is active
- Press `A` in Oak's lab while the scripted intro is still running and the player has no starter
- Otherwise prioritize movement

### 2. Added dedicated movement timing

`GameController` now has a `move()` helper that:

- Holds a direction longer than before
- Uses a longer release/settle window
- Waits for tile movement to finish before the next decision

This separates directional walking from general-purpose button presses.

### 3. Added stuck detection

The agent now tracks:

- Last overworld map and position
- Last overworld action
- Consecutive turns where movement was attempted but position did not change

If the player does not move after a directional input and there is no text box active, the stuck counter increases and the agent logs a `STUCK` event.

### 4. Added fallback direction rotation

When the agent is stuck, the navigator does not keep retrying the exact same move forever. It rotates through alternative directions while still preferring the target direction.

This is intended to help with doorway alignment, collision edges, and early-game map transitions.

### 5. Added early-game scripted targets

A small `EARLY_GAME_TARGETS` table was added so the agent does not depend on the generic route planner for:

- Red's bedroom
- Red's house 1F
- Pallet Town northbound movement to Oak

This gives the early game a deterministic path up to the Oak interception sequence.

## Logging Improvements

The overworld loop now emits higher-signal logs:

- `MAP CHANGE` when transitioning between maps
- `STUCK` when repeated movement attempts fail
- `OVERWORLD` logs now include chosen action and stuck count

These logs should make it much easier to tell whether failures are caused by:

- bad timing
- bad target coordinates
- text box handling
- scripted movement taking over

## Verification

Verification completed:

- `python3 -m py_compile scripts/agent.py scripts/memory_reader.py`

Verification not completed in the local shell:

- Live ROM execution
- Screenshot inspection after the new loop
- Confirming that the agent reaches Oak's lab end-to-end

The local shell did not have `pyboy`, `Pillow`, or `numpy` installed, so runtime testing was not possible there.

## Expected Next Outcome

With this change, the expected sequence is:

1. Intro finishes
2. Player walks from bedroom to downstairs
3. Player exits the house into Pallet Town
4. Player walks north
5. Oak stops the player and escorts them to the lab
6. Agent switches to interaction-heavy behavior inside Oak's lab until the scripted sequence advances

## Remaining Risk

The biggest remaining uncertainty is live timing inside the emulator. The logic is materially better now, but the final answer still depends on runtime behavior in stereOS with the actual ROM.
