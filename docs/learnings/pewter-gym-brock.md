obstacle:      pewter-gym-brock (Badge 1 — Boulder Badge)
category:      battle
symptom:       Four previous runs (r7, r8, haiku, laguna-xs) reached Pewter City and never took the
               badge. Reproduced here from the staged arrival baton on unmodified `main`
               (`data/probe/b`, 2026-08-17): the lane walks map 2 -> Gym (map 54) in ~10 turns,
               beats the Gym's Jr. Trainer down to **3/48 HP**, steps onto Brock's face tile at
               (5,1) — and whites out. `MAP CHANGE | 54 -> 0` (respawn in Pallet), after which the
               lane wanders back down Route 1 into Viridian Forest and burns its remaining budget
               there. Final fitness: `badges: 0`, `final_map_id: 51`. The wall is not one obstacle
               but three stacked ones, each of which hides the next: party health, Gym interior
               navigation, and an engagement (facing) bug on Brock's own tile.
failed:        -
  variant: all six BATTLE_SPREAD lanes of `pewter_to_badge`, unmodified repo
  failure: Byte-identical, exactly as r8 reported. The spread varies `hp_run_threshold` /
           `hp_heal_threshold` only, and the lane carries no healing item, so no lane ever takes a
           different branch. Confirmed again AFTER the fix: all six lanes finish in 168 turns with
           identical fitness (`data/relay-brock-1/report.json`). Six lanes here buy repetition, not
           search — a real spread for this segment would have to vary navigation or the heal path.
  variant: seed `pre_brock_r8.state` / `pre_brock_r7.state` ("iterate on the battle in seconds")
  failure: Both files are the SAME file (md5 `2f36ff8b08edc2e9adbff0bff503e3f6`), and neither is
           parked on Brock: `--save-state-on-trainer 54:` fires on the FIRST trainer battle on map
           54, which is the Gym's Jr. Trainer (Diglett L11 + Sandshrew L11). Loaded at 8 HP
           (`data/probe/a`), the lead loses that fight in three turns, whites out, and the run
           restarts from Pallet Town — 400 turns later it is back in Viridian Forest. Unusable for
           battle iteration; the MANIFEST's provenance for them is wrong on both counts.
  variant: heal-only fix (Pokemon Center round trip, no Gym waypoints) — `data/probe/c`
  failure: Healing works (32/48 -> 48/48 in ~25 turns) and the Jr. Trainer now costs only 12 HP,
           but the lane then spends 1400 of its 1500 turns two-cycling (4,2)<->(4,6) inside the
           Gym. Exposed obstacle 2 (see pewter-gym-interior-navigation).
winner:        `pewter_to_badge`, seed `pewter_arrival_lagunaxs_hp32.state`, all six lanes:
               `badges: 1`, `brock_won: true`, `brock_turns: 11`, `turns: 168`,
               `brock_lead_species: Charmeleon`, `brock_lead_level: 16`, ending on (5,1) map 54.
               Three code changes, no genome change (`BATTLE_SPREAD` untouched):
               1. `scripts/agent.py::_pewter_heal_action` — a Pewter Pokemon Center round trip
                  gated on the lead's HP ratio (`PEWTER_HEAL_GATE = 0.85` outside the Gym,
                  `PEWTER_GYM_RETREAT_GATE = 0.9` inside it, `PEWTER_MAX_HEAL_TRIPS = 6`).
               2. `references/routes.json` "54" — six emulator-derived interior waypoints that take
                  the east detour around the Jr. Trainer and end ON Brock's face tile (5,1), plus
                  removing PEWTER_GYM from `parcel_quest.GO_NORTH_PILOT_MAPS` so they can run.
               3. `scripts/agent.py::_brock_engage_action` — a face-cycle (up/left/right/down, A
                  between each) on Brock's row, and `_quest_nav_active = True` inside the Gym so a
                  backtrack restore cannot yank the lane off the tile it just climbed to.
               Plus a measurement fix: `brock_won` was null on runs that DID win (below).
why it worked: The battle itself was never unwinnable — it was never fought at survivable HP, and
               on the two occasions it was reached, it was reached by accident. A L16 Charmeleon
               beats Brock comfortably: Ember is resisted by rock (0.5x) but Onix's Gen-1 Special
               stat is ~15, so Ember still lands 9-16 per turn against Onix's 36 HP, while Onix's
               L14 moveset (Tackle/Screech — Rock Throw is a level-19 move it does not have) chips
               back single digits. Measured: `MOVE | L16 Ember(fire) vs #22(rock) dmg=9,9,16,1 KO`,
               11 battle turns for both of Brock's Pokemon. What it cannot survive is entering at
               3/48. The Center is on the map the lane is already standing on and no lane had ever
               walked into it — `healer.py` is a genome race, not an in-game heal, so "heal" in
               this repo never meant HP. Walking in is ~25 turns and converts a guaranteed loss
               into a fight with ~40 HP of headroom. The other two changes are about REACHING the
               fight (see the two sub-obstacle files); the badge falls out of all three together.
               Note the margin is still thin (`lead_hp: 6` at the end of the winning relay lanes,
               37 in the equivalent standalone probe — the difference is Onix's damage rolls): two
               of the 11 battle turns are spent on the move-category probe firing Scratch (1-2
               damage) at each new Pokemon, which is roughly 20 HP of the margin.
generalizes:   1. When a battle wall reproduces identically across a decision spread, the spread is
               not the variable — measure the STATE the lane arrives in before tuning the policy
               that runs once it is there. Two of the three fixes here are in navigation, and the
               third is a resource (HP) the fitness file was already reporting.
               2. Prefer an in-game resource loop (Center, Mart, item) over parameter tuning: the
               game ships the fix, and it is worth 40 HP that no genome can produce.
               3. Trust a staged seed only after re-measuring it. Two of the five seeds are the
               same file, and the two "pre-Brock" ones are pre-Jr.-Trainer at 8 HP.
artifacts:     data/relay-brock-1/report.json (all six lanes, `brock_won: true`)
               data/relay-brock-1/batons/pewter_to_badge.state (verified: badges=1, map 54 (5,1) —
                 re-read with `agent.py --max-turns 0`, see data/probe/baton/fitness.json)
               data/relay-brock-1/pewter_to_badge/*/fitness.json, .../base/agent.log
               data/probe/{a,b,c,d,e,f,g,h}/{agent.log,fitness.json,world.map} (the diagnosis)
