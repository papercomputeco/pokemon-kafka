# The BICYCLE, and the counter nobody could reach (2026-09-02/03)

**Result: `BICYCLE` (item 6) is in the bag**, banked `bicycle.state` at map 66 (4,2). The chain the
cartridge described came true exactly as written, and the one thing that blocked it for a whole
recon leg was an engine gap, not the game.

## The chain, extracted before anyone walked anywhere

`BICYCLE` is item 6 and `BIKE VOUCHER` is item 45, and **neither appears as an item ball on any
map** — so both come from a person, which made this a talking problem from the start. The shop's
own script ruled money out before we had a single coin's worth of doubt:

    "Hi! Welcome to our BIKE SHOP"  /  "It's a cool BIKE! Do you want it?"
    "Sorry! You can't afford it!"
    "Oh, that's...  A BIKE VOUCHER!  OK! Here you go!"
    " exchanged the BIKE VOUCHER for a BICYCLE."
    "You better make room for this!"

A sign block grouped *"MON FAN CLUB — All MON fans welcome!"* with **VERMILION CITY**. That gave two
hypotheses, and both were handed to the leg as hypotheses rather than answers.

## Both hypotheses were testable; one was right and one was wrong

- **Voucher — CORRECT.** Vermilion is map 5 (confirmed by our own history: its (7,3) warp is the
  FISHING GURU who gave us the OLD ROD). Building **map 90**, an 8x8 room with six sprites — the
  densest small room in the city — is the Fan Club. The chairman says
  **"I chair the POKéMON Fan Club! I have collected over 100 POKéMON!"** and the sink records
  **`THE BAG GAINED [('BIKE VOUCHER', 1)]`**.
- **Shop — WRONG.** I guessed map 230 (two entrances, one clerk). Map 230 is the **badge
  explainer**: *"POKéMON BADGEs are owned only by skilled trainers… Which of the 8 BADGEs should I
  describe?"* The BIKE SHOP is **map 66**, whose customer says *"These BIKEs are cool, but they're
  way expensive!"* A ruled-out door is a real result; this one cost one building visit.

## What actually blocked it: a counter is not an adjacent tile

The recon leg reached the shop, held the voucher, freed a slot, stood at the counter — and failed,
recording `body (6,2) unreachable/no response`. It was right that (6,2) is unreachable. It was
wrong to conclude the clerk is.

    map 66 sprites: [{'kind':'npc','x':6,'y':2}, {'kind':'npc','x':5,'y':6}, {'kind':'npc','x':1,'y':3}]
    clerk (6,2): reachable adjacent cells -> []          <- correct, and a dead end
    clerk (5,2): reachable adjacent cells -> [(4,2,'right')]  <- talk fires here

**You talk to a shop clerk across the counter**, from two tiles away, exactly as `center_counter`
already models for a Pokémon Center nurse (npc at (3,1), stand (3,3), face up). That special case
was written for Centers and never generalized, so every other counter in the game — shops
included — is invisible to `_go_and_talk`, which only ever tries the four cells adjacent to the
sprite.

From (4,2) facing right, first press:

    "Oh, that's..."  "A BIKE VOUCHER!"  "OK! Here you go!"
    "AAAAAAA exchanged the BIKE VOUCHER for a BICYCLE."
    "How do you like your new BICYCLE?  You can take it on CYCLING ROAD and in caves!"

`Rig.talk_across` now tries the across-the-counter cell whenever no adjacent cell is reachable, so
this is a capability rather than a story.

## Still open

- **The gate is untested.** `29 -> 28` was the whole reason for the bike, and the route the engine
  plans from Cerulean is `3 -> 16 -> 10 -> 18 -> 6 -> 27 -> 28 -> 29` — i.e. it enters Cycling Road
  from the **north (27)**, so `29 -> 28` may never need to be walked at all. Driving it failed at
  the **first** hop: `3 -> 16` is `no-path` from (3,9,12). That is the same intra-map pathing
  failure that killed two badge-8 legs on map 3, and it is now the top blocker in this arc.
- **The bag stays full.** It sat at 20/20 with the voucher; `make_room` tossed 1x TM11 to free the
  slot the bicycle needed. Any future gift needs the same courtesy first.
- **The sink was flooded.** The recon leg emitted **221,504 `discovery` events** in one session and
  the day's telemetry file is **42 MB**. Recording every sentence is right; recording every frame's
  worth of them is not. Worth a de-dup before the next long recon.
