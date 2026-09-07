# The Saffron gate, measured — 2026-09-07

Lane 33 walked into the Route 6 gate house's guard eight times from a 2-badge save and the Forger had no
class for the sentence. `scripts/probe_saffron_gate.py` boots a list of banked saves, walks each toward
Saffron (map 10) with no model seated, and records the refusal, the bag before and after, and what the guard
says when spoken to. Rows: `data/replay_arcs/logs/probe_saffron_gate{,2,3}.jsonl`.

## What the saves said

| save | badges | FRESH WATER in bag | gate | the guard, spoken to |
|---|---|---|---|---|
| captain_done | 2 | no | refused at 73 (3,2) | "I'm on guard duty. Gee, I'm thirsty, though! Oh wait there, the road's closed." |
| leg_5 | 3 | no | refused at 73 (3,2) | same |
| celadon | 3 | no | refused at 73 (3,2) | same |
| b5_celadon | 4 | yes | passed | "Hi, thanks for the cool drinks!" (70 (1,3)) |
| b5_lavender | 4 | yes | passed | same |
| BADGE5 | 5 | yes | passed | |
| fly_won-27 | 6 | no (tossed earlier: 6 `supervisor.tossed` rows in the sink) | passed | |

The refused step prints the window's first clause, `I on guard duty. Gee, I thi` (the decoder drops
apostrophes and the box cuts at the row). A guard in another gate house (map 126) was heard earlier saying
"I'm thirsty! I want something to drink!" (body_engaged rows in the sink). Passing consumes nothing on the
saves that pass; the clear happened on their lineage before the earliest of them was banked, and the guard
names it himself: drinks.

## What is and is not established

- **Established:** the gate class, both of its sentences, and the sentence of a cleared guard. The lineage
  that passes is the lineage that acquired FRESH WATER; the guard on that lineage thanks the player for
  drinks. `badge4` (4 badges, no FRESH WATER, different lineage) never reached a gate in this probe, so the
  badge count is not shown to matter either way.
- **Not established:** the act itself (handing the drink over) was never performed by a run of ours — no
  measured shop sells FRESH WATER (`quartermaster.SHOPS` are marts) and the sink has no hand-over row for it.
  The deposit test (bank the water, re-walk) did not run: `pc_store_item` refused on b5_celadon's Center.
  `clears_with` therefore says what was measured and no more.

## Added

`thirsty_guard`, pattern `on guard duty|I thirsty`, in pokemon-kafka `GATE_CLASSES` and empirical-evidence
`GATES`. The corpus's gate-text rows for this sentence exist only after a rebuild; the next `convert_telemetry`
run turns the 15 `supervisor.gate_text` rows on maps 70/73 into training rows with this class.

## Next

1. A drink-handing leg: teach the rig the vending machine (measured, like the marts) or find the b5
   lineage's FRESH WATER source in its run logs; then hand it to a refused guard and record the bag and the
   sentence change. That completes the clear.
2. Rebuild the corpus and regate the Forger with the new class in it.
