# Mission: stop Seafoam B4's current with STRENGTH, cross to the platform, catch the legendary

You are the Extractor (puzzle seat). `uv run ...` for all Python. Print `date` at start and before any
summary. Screenshot every refusal and look at it. Write measured facts to the journal
(`from memory_writer import append_observations`, `source_session:"extractor"`, content starting `map=...`).
Do not write `docs/learnings/`.

## The baton and the goal

- Main run: `data/local_runs/roster-bench/healed_cinnabar.state` — 7 badges, party healed, Gyarados L20
  (party **index 5**) knows SURF + STRENGTH (both confirmed live). Charizard L100 is the lead.
- A surfer already on Seafoam B3: `data/local_runs/roster-bench/seafoam_loop_stuck_3.state` (161 at (18,12));
  the clean-floor boulder baton for the oracle. Use this to solve the boulder half fast, then replay on the
  main baton for the real catch.
- Goal: reach the sprite at **map 162 (6,1)** (the legendary candidate — READ IT LIVE, do not assume) and
  engage/catch it.

## What is measured (journal: grep `map=162`, `map=161`)

- The conveyor is the way down: on B3 (161) surf from the 0x15 shore **(15,7) facing DOWN**; the current
  carries the surfer, no input needed, and lands it on **B4 (162) at (20,15)** in the EAST water (x16-27).
- The legendary platform (6,1) sits on land (x5-10, y0-2), reachable only from the **WEST water** (x2-13)
  via the 0x15 shore **(7,3)**: from the west water reach (7,4), step UP to (7,3), UP to (7,2), to (6,1).
- East and west water join only through the central land block. The **only** 0x15 launch from central land
  into the west water is **(7,11)** — and from (7,11) facing DOWN, SURF says **"The current is much too
  fast!"**. That current is the gate.
- Boulder mechanic (B3, tileset 17): STRENGTH pushes a boulder one tile per 16-frame hold; a boulder that
  reaches a **0x22 hole** falls through to B4. B3 holes **(4,15)/(4,16)/(4,17)** sit directly over B4's
  west channel (x2-5, rows 12-16) — the "too fast" current. B4 already shows boulder sprites at (4,15)/(5,15)
  from earlier drops. B3's first hole (3,16) has a measured 6-push solution:
  `(8,14) UP; (5,14) LEFT x4 (parks at (1,14), opening (3,14)); (3,15) DOWN into (3,16)`.

## The job

1. On B3, drop boulders into the holes over B4's west channel (start with the known (3,16) solution; then
   the (6,16)/(4,15..17) holes). The boulder oracle already catalogs pushes:
   `uv run python scripts/boulder_oracle.py show --map 161`. Extend it if a new push is needed.
2. After each drop, go down the conveyor to B4 and retest the launch off **(7,11) DOWN** (`scripts/probe_b4_launch_clean.py`
   reads the sentence). The verdict is the current no longer being "too fast" — surf succeeds and moves onto (7,12).
3. When it crosses: surf the west water to (7,4), step up to the platform, stand beside (6,1), and READ the
   sprite (`rig.talk`, screenshot). If it battles, catch it (bring Ultra Balls / status; Gyarados can bring
   it low without KO — do not one-shot with the L100s).
4. Bank `seafoam_legendary` with the catch, and re-run the whole sequence on `healed_cinnabar.state` so the
   catch lands on the 7-badge run.

## Discipline

- `rig.walk` is LAND-only; it cannot move a surfer on water. Drive water with directional presses (the probes
  carry a `navigate()` that BFSes over land+water and arms surf on entry).
- Drain text after every battle (B until `rig.textbox()` empty). Kill by PID, never `pkill -f` your own cmd.
- One-off drivers are `scripts/probe_<name>.py`. Commit as you go.

## Definition of done

`seafoam_legendary.state` banked with the legendary caught, or the journal holding, per boulder configuration,
what the (7,11) current said afterwards — with screenshots — and the smallest drop-set that clears it.
