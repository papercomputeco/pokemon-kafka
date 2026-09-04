# Gold Teeth -> the Warden -> HM04 STRENGTH: won (2026-09-04)

run_id `04dabd83e329` · baton in `warden_no_hm04.state` (map 156, GOLD TEETH in the bag) · baton
out `strength_won.state` (155, 2, 4), then `strength_taught.state` (Gyarados knows STRENGTH) and
`strength_ready.state` (Charizard swapped to the lead for the sea).

## Where the Warden actually is

**Map 155, the Fuchsia house behind the door at map 7 (27,27).** Not map 156 (the Safari Zone
building — its two staff say the Safari intro lines, measured 2026-09-03) and not any of the four
Safari rooms 221/223/224/225 (measured the same night: SARA, silent sprite-32 bodies).

The catalog that found him: every one of Fuchsia's eight doors (152, 153, 154, 155, 156, 157, 158,
164) had zero engaged bodies in the event sink. 155 was tried first because the cartridge lists
an item ball in it (a RARE CANDY, behind a Strength boulder — the "npc" at (8,4), pic 63, says
*"This requires STRENGTH to move!"*). The body at (2,3) said *"AAAAAAA gave the GOLD TEETH to the
WARDEN!"* and the bag gained `HM04` on the same talk. Bag growth was the verdict, per the mission.

## What it cost, and why it was cheap this time

Ten hand-tapped `probe_warden2..11.py` scripts were written the night before, scanning map 219's
interior cell by cell for a way into room 223. The extracted collision grid already shows the
x=17 column solid from rows 6 to 13; rounds 10 and 11 both ended pressing left into it. None of
them could have found the Warden: he is not in the Safari Zone at all.

The win was one supervisor command, no new script:

    uv run python scripts/supervisor.py run --state .../warden_no_hm04.state \
        --goal 155,158,152,153,164,154 --hunt-item HM04 --sweep-items --bank strength_won

`--hunt-item` is new: the leg is judged on the bag holding a named item that a BODY hands over
(the third observed way a story item arrives, after balls and beaten trainers), and the goal
chain is the list of doors it might be behind — a door without it is ruled out, not a failure.

## Teaching it (`Rig.teach`, new, measured)

USE HM04 -> "Booted up an HM!" -> "It contained STRENGTH!" -> "Teach STRENGTH to a POKéMON?"
(YES/NO draws only once the typewriter finishes) -> a roster captioned ABLE / NOT ABLE, fainted
members included (Gyarados L20 at 0 HP: ABLE; Dugtrio, Pidgeot, Hypno: NOT ABLE; Primeape,
Charizard: ABLE) -> "GYARADOS learned STRENGTH!". The roster does not scroll, so the cursor is
the raw register, not `list_index` (whose scroll half still held the bag's offset). Proof is
move id 70 landing in Gyarados' struct, slot 4.

## Boulder sprites are pic 63

Every "npc" with `pic == 63` answers "This requires STRENGTH": map 155 (1), Seafoam 192 (2),
159 (2), 160 (2), 161 (6), 162 (2), plus 108, 194, 198. The earlier Seafoam legs logged these as
unreachable bodies; they are the boulders the next leg pushes.
