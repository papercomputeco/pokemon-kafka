# Training an Archetype

**Supervised fine-tuning of a crew seat from measured play of Pokémon Red**

| | |
|---|---|
| Organisation | pcc-labs |
| Document | PK-WP-01, version 1.0 |
| Date | 7 September 2026 |
| Prepared by | bdougie, with Claude Code |
| Repositories | `pcc-labs/pokemon-kafka`, `pcc-labs/empirical-evidence` |
| Artefacts | HF dataset `bdougie/pokemon-red-sft`; HF adapters `bdougie/smollm3-pokemon-forger-lora`, `bdougie/smollm3-pokemon-red-lora` |

## Abstract

An expedition system plays Pokémon Red with a crew of local language models, each seated by a router for one kind of work: reconnaissance, navigation, puzzles, battle, and reading what the game says back. This paper describes how one of those seats, the Forger, was turned from a role description into a trained adapter. The Forger's job is to name what a body on the map is and what talking to it yields, to classify the game's refusal sentences as gates, and to take an operator's handoff. Its training data was the thinnest in the corpus because the crew had only ever spoken to bodies on maps it had a saved game for. We ran a forward-play sweep that walked from healthy saves into 78 previously unheard maps, fixing the road engine wherever a measured wall stopped it, and rebuilt the corpus from the telemetry the sweep left behind. The corpus grew to 27,836 rows across nine domains and the Forger's dialogue rows from 848 to 1,318. A LoRA adapter on SmolLM3-3B trained on the Forger's 1,481 rows raised held-out body accuracy from 0.21 to 0.82 and outcome accuracy from 0.33 to 0.66 against a 0.49 majority baseline, and read all held-out gate sentences correctly. A second adapter trained on every seat's rows carries the battle seats at 0.99 and 0.95 while remaining a weaker Forger than the dedicated one. Both adapters, the dataset, and a quantized GGUF for local serving are published. Every row in the corpus is measured from the cartridge; no recalled game fact is load-bearing anywhere in the pipeline.

## 1. Introduction

The pokemon-kafka project asks a narrow question: can a system of small, locally served models learn to play a Game Boy cartridge well enough that each run makes the next run better, without a human in the loop body? The answer depends on where the models get their facts. Pokémon Red exists in several versions, and language models recall them interchangeably. The project's own record of trusting recall is expensive: a hand-typed species table hid 6,515 wild Paras sightings as Metapod, a recalled type chart carried two swapped pairs and mis-scored every battle for months, and a recalled RAM address wasted a probe session. The project therefore treats the ROM and the running game as the only sources of truth. Structures are extracted from the cartridge by content signature; behaviour and story are measured live.

That rule shapes how a seat can be trained. There is no textbook to distil. The training set for a seat has to be assembled from what the game actually did when the crew acted, recorded as events, and converted into prompts whose answers were observed rather than believed. This paper is the record of doing that for one seat end to end: the data problem, the play that solved it, the corpus, the adapter, the gate it had to pass, and how it is served.

We use the word *archetype* for a seat in the sense the crew uses it: a role with a system prompt, a bounded menu of actions, and a benchmark that decides who sits in it. Training an archetype means producing a model that fills the seat better than the base model does, measured on held-out rows of the seat's own work.

## 2. Background: the expedition system

### 2.1 Seats earned by benchmark

The crew was cast from a per-skill matrix run on 22 August 2026 (`benchmarks/2026-08-22-skill-matrix.md`): six models on three skill-isolated legs of the game. Battle was solved by all six and became an execution baseline. Navigation was solved by all six with three distinct solution families; one model's line dominated on both turns and hit points. Nobody solved the puzzle leg, but depth into the puzzle ordered exactly as a thirty-second screening question had predicted. The result was a casting table: the Investigator observes before anyone reasons, the Point Man navigates, the Extractor takes puzzles, the Wheelman fights. Anthropic models are not a seat; when the ladder is exhausted the failure is written down and handed to the operator.

The Forger was added later, for a counted reason. Across four legs of a water arc the crew engaged zero bodies on five maps while one map's own stuck record listed ten live bodies and used them only as obstacles to route around. A seat that is handed failure codes and nothing the game said is reasoning about a world nobody looked at.

### 2.2 The supervisor loop

A leg is run by a deterministic supervisor (`scripts/supervisor.py`). It boots a banked save, settles it, looks up the route in the extracted map graph, and walks it hop by hop through a road engine (`scripts/road.py`) that knows collision, ledges, warps, water, currents, and slopes. When a hop fails, the supervisor assembles measured facts and a bounded menu of actions, hands them to the seated model through a recording proxy, and executes the model's choice. Models pick actions; they never drive the emulator. Every run emits events to a dated telemetry sink with a stable run identifier. The sink is what the corpus is built from.

### 2.3 Ground truth

Map, warp, collision, tile-pair, ledge, species, type, and encounter tables come from `rom/pokemon_red.gb` through `scripts/rom_truth.py`, which locates them by content signature and never by remembered address. Everything the tables cannot say, such as which tile identifiers are water, whether a tree is cuttable, or where a current carries the player, is measured with a probe against the running game and stored in `references/` as a measured file. Recalled lore may propose a hypothesis; only a measurement may ship.

## 3. The Forger archetype

The Forger answers three kinds of question, each as a JSON object the supervisor can act on.

- **npc-dialogue.** Given the map, the cell a body stands on, its sprite picture when known, and the sentence read from the screen after talking to it: what is the body (trainer, npc, item, unknown) and what did the talk yield (talk, handed, fought-won, fought-lost, fled, gate, blocker, stale), with any items received and any gate named.
- **gate-text.** Given a refused step and the sentence the game printed: what gate class this is and what clears it.
- **handoff.** Given the supervisor's exhaustion record: the diagnosis and the actions the operator then measured and took.

On 5 September 2026 the corpus held 848 npc-dialogue rows and 65 gate-text rows. The body catalogue (`scripts/npc_catalog.py`), which cross-references every sprite the cartridge lists against every conversation the sink records, showed sentences for 600 of 922 bodies on 119 of 213 maps. Ninety-three maps had never been heard from at all, and none of them had a banked save. A first Forger adapter trained on that corpus reached body accuracy 0.73 and an outcome head one row above the majority label. The data, not the recipe, was the constraint.

## 4. Method

### 4.1 Forward play for data

We wrote a lane runner (`data/replay_arcs/forward_lane.sh`) that runs one single-goal leg per unheard map, banking the save on arrival so that the next leg boots the last arrived bank. A leg is launched with the supervisor's engage and sweep-items flags, so that on arrival the crew talks to every body the cartridge lists for the map and picks up every item ball, never tossing an item. Lanes were seeded from healthy saves: a post-credits save with all badges and a healthy party, and, for the maps whose story state had closed, earlier saves such as a two-badge save with the S.S. Anne still docked and a save holding the Poké Flute with the Route 16 sleeper still present.

The lane rows record 166 legs, 96 of which arrived, on 78 distinct target maps out of the 87 the map graph could route to. Legs finish in two to ten seconds when the route is clean because the headless emulator is unthrottled; a wall costs the leg's whole budget. Every wall was treated as an engine defect until measured otherwise. Each fix was measured live with a probe, covered by a test, and merged behind the repository's full-coverage gate. The walls and their fixes, in the order they were met, were:

1. **North and south water edges.** Route 21 to Pallet Town is a water edge with no land cells; the engine knew only east and west water crossings and boarded the land plaza. The crossing now routes the edge row's columns, walks to the shore, and arms Surf before routing.
2. **Shore edges.** Cinnabar Island to Route 20 has land rows that face a cliff and water rows that open. Any land on the near edge had read as a wall; a land-plus-water edge is now sent to the surf crossing. About fifty legs routed through this hop.
3. **Water tiles by measurement.** Tile 0x32 surfs; tile 0x11 is a fenced pond that refused 103 times. The water set became {0x14, 0x32}.
4. **Battles under the arm.** A wild encounter or swimmer that opens while Surf is being armed is fought and the arm retried.
5. **Routing by reachable region.** Once a wall on a map chain is measured, the router plans by the walk's flood fill, one-way ledges and door tiles included, rather than by map. Region keys carry the map, the region's minimum cell and its size after a one-way superset was found to share a minimum cell with a strip. 214 region routings fired during the sweep.
6. **Connection alignment.** Map connections carry a signed alignment offset in the map header. Without it the engine entered Route 15's neighbour at the nearest cell and landed in a thirteen-cell pocket. Extracting the offsets put the entry where the game puts it.
7. **Multi-entry edges.** One edge may lead to several disconnected regions of the far map; the router now emits one hop per far region the aligned open cells reach.
8. **Cut.** Bushes with tile 0x3D are cut and become floor in the loaded model; trees with tile 0x50 print "There isn't anything to CUT!" and are not.
9. **Currents and slopes.** The Seafoam Islands' currents were measured and stored as hops; Cycling Road's slope forbids moving against it and its safe cells are pruned from the walk.
10. **The sleeper and the bicycle.** The bag scrolls to the top before an item is used; a body the sprite table still lists after removal is tested with one press before the engine waits for it; the Cycling Road gate's "No pedestrians" sentence is answered by riding the bicycle.
11. **Story state.** A door held by a Rocket grunt on a five-badge save is clear on a seven-badge save. Story-state bodies are heard from a later save, never forced with a probe.

Twelve pull requests (#128 to #139) carried these fixes. Five things remained unreachable after measurement and are listed in Appendix C.

### 4.2 Corpus construction

The corpus is built in the sibling repository empirical-evidence by `autotune.convert_telemetry`, a deterministic conversion of the telemetry sink (seed 42) into chat rows, one domain per kind of decision. Table 1 lists the domains, the seat each serves, and what a row teaches.

**Table 1. Domains of the sft_v5u corpus (27,836 rows; 25,053 train, 2,783 validation).**

| Seat | Domain | Rows | What the row teaches |
|---|---|---:|---|
| Wheelman | move-choice | 10,938 | damage bucket per move; best move per matchup |
| Narrator | narrator | 10,493 | one-sentence play-by-play for the overlay |
| Wheelman | battle-outcome | 3,571 | will this fight be won; fight or flee |
| Forger | npc-dialogue | 1,318 | where a body stands and what it said, to what it is and what the talk yields |
| Wheelman | battle-action | 725 | next action from a won battle's turns |
| Extractor | puzzle-consult | 587 | menu choice at a wall, labelled by what the engine returned |
| Forger | gate-text | 82 | the game's refusal sentence, to the gate class and what clears it |
| Operator | handoff | 81 | the supervisor's exhaustion facts, to what the human measured and did |
| Genome | genome | 41 | above-median rollout genomes per scenario |

The v5 conversion ran over the sink after the sweep. Because the sink alone no longer held the older battle sources, the shipped corpus is the union (`autotune.merge_corpus`) of the 5 September corpus and the post-sweep conversion, de-duplicated and re-split with a 10% validation share. Each row carries its domain and a `meta` block with the event's own timestamp, source file, run identifier and map coordinates; 27,045 of 27,836 rows are stamped, spanning 27 June to 7 September 2026. The conversion is guarded by a resident-memory budget after an earlier run over 21 GB of sink was killed by the kernel.

One defect is worth recording. The merge's first split files carried messages only. The held-out gate scores by domain, so it found zero scorable rows and reported a pass. The splits were re-cut from the corpus keeping every key, and the dataset was re-uploaded. A gate that can pass on nothing is not a gate; the fix was structural, not a threshold.

A Forger-only corpus, `sft_v5_forger`, is the npc-dialogue, gate-text and handoff rows of v5u: 1,481 rows, 1,333 train and 148 validation.

### 4.3 Training

Both adapters were trained with `autotune.train_sft`, a TRL SFTTrainer run with PEFT LoRA on `HuggingFaceTB/SmolLM3-3B` in bf16 on one RTX 5090. Table 2 gives the configuration.

**Table 2. Training configuration.**

| Parameter | Forger adapter | All-seats adapter |
|---|---|---|
| Base model | SmolLM3-3B, bf16 | SmolLM3-3B, bf16 |
| LoRA rank / alpha / dropout | 32 / 64 / 0.05 | 32 / 64 / 0.05 |
| Target modules | q, k, v, o, gate, up, down | q, k, v, o, gate, up, down |
| Training rows | 1,333 | 25,053 |
| Schedule | 3 epochs | 900 steps (0.57 epoch) |
| Wall time | 770 s | 1,842 s |
| Final training loss (mean) | 0.374 | 0.215 |
| Final mean token accuracy | 0.968 | 0.965 |

### 4.4 The gate

An adapter ships only if it passes `autotune.eval_heldout` on the validation split. The gate compares the tuned model with the untuned base on every scored metric and with a majority-label baseline on every metric that has one. The rule is strict: the tuned model must match or beat the base on every metric and beat every majority baseline. A model that improves one head by regressing another fails. Metrics are exact-match accuracies on the JSON fields of the answer: body and outcome for npc-dialogue, gate for gate-text, win and recommendation for battle-outcome, bucket for move-choice.

## 5. Results

### 5.1 Coverage

**Table 3. Body catalogue before and after the sweep.**

| | 5 September 2026 | 7 September 2026 |
|---|---:|---:|
| Bodies the cartridge lists that have a recorded sentence | 600 of 922 | 887 of 996 |
| Maps with at least one heard body | 119 of 213 | 184 of 213 |
| Unheard maps with no banked save | 93 | 10 |

The denominator grew because the rebuilt catalogue reads sprite tables from more banked saves. Of the ten maps left, six have no warp entrance in the extracted tables, three form a closed pocket on one map, and one is a facility floor behind a cell the walk wedges on.

### 5.2 Corpus growth

**Table 4. Forger domains, v4 to v5u.**

| Domain | v4 (5 Sep) | v5u (7 Sep) | Change |
|---|---:|---:|---:|
| npc-dialogue | 848 | 1,318 | +470 |
| gate-text | 65 | 82 | +17 |
| handoff | 77 | 81 | +4 |

### 5.3 The Forger adapter

**Table 5. Held-out gate, Forger adapter (148 validation rows).**

| Metric | Rows | Base | Tuned | Majority |
|---|---:|---:|---:|---:|
| npc-dialogue / body | 133 | 0.21 | **0.82** | |
| npc-dialogue / outcome | 133 | 0.33 | **0.66** | 0.49 (always "talk") |
| gate-text / gate | 4 | 0.00 | **1.00** | |

<!-- fig:forger -->

The gate passed. Against the 5 September adapter the body head moved from 0.73 to 0.82 and the outcome head from one row over the majority to seventeen points over it. The recipe was unchanged between the two runs; the 470 new dialogue rows are the difference.

### 5.4 The all-seats adapter

**Table 6. Held-out gate, all-seats adapter (2,783 validation rows; scored domains shown).**

| Metric | Rows | Base | Tuned | Majority |
|---|---:|---:|---:|---:|
| battle-outcome | 349 | 0.52 | **0.99** | |
| move-choice | 1,061 | 0.00 | **0.95** | |
| npc-dialogue / body | 132 | 0.21 | **0.77** | |
| npc-dialogue / outcome | 132 | 0.42 | **0.63** | 0.61 (always "talk") |
| gate-text / gate | 8 | 0.00 | **1.00** | |

<!-- fig:mixed -->

The gate passed. The base model's move-choice score of zero is a format failure rather than ignorance: it does not return the requested JSON. Scoring the validation split took 1,086 seconds for the base model and 251 seconds for the tuned one, because tuned answers are short and parse first time.

### 5.5 Serving

The Forger adapter is merged into the base, converted to GGUF, quantized to Q4_K_M (`scripts/package_lora.sh` in empirical-evidence), uploaded to the adapter's repository under `gguf/`, and registered with the local Ollama as `pokemon-forger:Q4_K_M`. The crew reaches it through the same recording proxy as every other seat. Any other machine downloads the GGUF with `hf download` and registers it with a two-line Modelfile. A smoke test through the proxy on a held-out prompt returned the right body and the right JSON shape.

## 6. Discussion

**Data moved the number; the recipe did not.** Two Forger adapters were trained with the same rank, schedule and base two days apart. The second is nine points better on body and seventeen points further above the majority on outcome. The only change was 470 rows of dialogue from 78 maps the crew had never stood on. For a seat whose work is to read a world, coverage of the world is the training signal.

**Play produced the data, and the engine had to be fixed to play.** None of the eleven walls in section 4.1 was a modelling problem. They were gaps between the extracted map graph and what the cartridge does at an edge, a shore, a slope, or a sleeping body. Fixing each in the engine rather than in a one-off script is what let the next lane run unattended, and is why the rows exist at all.

**The outcome head is the weak point.** Body classification is close to solved for the dialogue the corpus covers. Outcome is harder: "talk", "gate", "blocker" and "stale" partition the same sentence by what the supervisor did next, and the majority label alone scores 0.49 to 0.61 depending on the split. The dedicated adapter beats that by seventeen points; the all-seats adapter by two. More rows of the rarer outcomes, not more epochs, are the likely remedy.

**A dedicated adapter is the better Forger.** The all-seats adapter was trained on seventeen times as many rows for a fraction of an epoch and carries the battle seats convincingly. On the Forger's domains it trails the dedicated adapter on both heads. Seating is per role; the router can load the Forger's own adapter for the Forger's calls.

**Gates must be able to fail.** The split defect in section 4.2 would have shipped an untested adapter with a passing report. The fix was to make every row carry the key the gate scores by. A pipeline's checks deserve the same measurement discipline as its data.

## 7. Limitations

- The validation splits for the Forger's domains are small: 132 to 133 dialogue rows and 4 to 8 gate sentences. The gate-text result in particular is a floor, not an estimate.
- The gate scores exact matches on categorical fields. The free-text `clears_with` field of gate-text and the `diagnosis` of handoff are not scored.
- Labels are what the supervisor recorded, including its own misreads. A body labelled "unknown" with the gate `stale_window_text` is a real event the crew met, but it teaches the model the engine's failure mode as well as the game's behaviour.
- The gate numbers are the bf16 adapter's. The quantized GGUF returned a wrong outcome on one held-out prompt in a smoke test; it has not been gated separately.
- The dataset and both adapters are published privately. One-line `ollama pull` from the Hub requires a public repository.
- Ten maps remain unheard (Appendix C). The corpus cannot contain sentences the crew never read.

## 8. Future work

1. Gate the quantized GGUF with the same script as the bf16 adapter and publish that number beside it.
2. Seat the Forger adapter in the router for the Forger's calls and measure the crew's engage rate and wall clearance on a replay arc against the base model.
3. Grow the rarer outcome classes by replaying legs that end in gates and blockers.
4. Extend the gate to the free-text fields with a rubric the operator has agreed to.
5. Find live entries for the closed pocket on map 3 and the facility floor behind map 21, or record them as unreachable by design.

## 9. Conclusion

An archetype is a role with a benchmark. Training one from a game that models mis-remember meant refusing recall as a source and building the training set from measured play instead. That forced the play to happen, which forced the engine to be fixed wherever the map graph and the cartridge disagreed. The result is a corpus of 27,836 measured rows, a dedicated Forger adapter that quadruples the base model's body accuracy and beats the majority outcome label by seventeen points, an all-seats adapter that carries the battle seats, and a served quantized model any machine can pull. Each step is reproducible from the commands in Appendix B, and each number in this paper is the output of one of them.

## References

1. pcc-labs/pokemon-kafka, `AGENTS.md`: ground-truth rule and the measured cost of breaking it.
2. pcc-labs/pokemon-kafka, `.claude/skills/expedition/SKILL.md`: the crew, the rules of a leg, definition of done.
3. pcc-labs/pokemon-kafka, `benchmarks/2026-08-22-skill-matrix.md`: the per-skill model matrix that cast the crew.
4. pcc-labs/pokemon-kafka, `docs/learnings/forward-play-sweep-2026-09-05.md`: the sweep postmortem, walls measured and fixed, 5 to 7 September 2026.
5. pcc-labs/pokemon-kafka, pull requests #128 to #140.
6. pcc-labs/empirical-evidence, `docs/forger-adapter.md`: dataset, adapters and serving recipe; pull request #20.
7. Hugging Face: `bdougie/pokemon-red-sft` (dataset), `bdougie/smollm3-pokemon-forger-lora`, `bdougie/smollm3-pokemon-red-lora`.
8. HuggingFaceTB/SmolLM3-3B; TRL SFTTrainer; PEFT LoRA; llama.cpp GGUF conversion and quantization; Ollama.

## Appendix A. Row schemas

Each row is a three-message chat: a system prompt naming the seat, a user prompt of measured facts, and the assistant's JSON answer as observed. The Forger's dialogue prompt reads, for one validation row:

> On map 182, the crew talked to the body at (18, 22). It said: 'We hope to see you again!'.
> What is this body, and what comes of talking to it? Respond with JSON {"body": "trainer"|"npc"|"item"|"unknown", "outcome": "talk"|"handed"|"fought-won"|"fought-lost"|"fled"|"gate"|"blocker"|"stale", "items": [str], "gate": str|null}

with the answer `{"body": "unknown", "gate": "stale_window_text", "items": [], "outcome": "gate"}` and a `meta` block carrying the event name, map, coordinates, run identifier and timestamp. A gate-text prompt gives the map, cell and the refusal sentence, and asks for `{"gate": str, "clears_with": str}`; the answer for "No SURFing on GYARADOS here!" names `surf_launch_refused` and states that the clear is a shore cell facing edge-reaching water with Surf armed through the party menu.

## Appendix B. Reproduction

```
# pokemon-kafka: hear the unheard maps, then rebuild the catalogue
LANES="1 2 3" PLAN=data/replay_arcs/forward_sweep_3.json data/replay_arcs/forward_sweep.sh
uv run python scripts/npc_catalog.py build && uv run python scripts/npc_catalog.py report

# empirical-evidence: corpus, adapters, gate, packaging
uv run python -m autotune.convert_telemetry --pk-root ../pokemon-kafka \
    --pk-data ../pokemon-kafka/data/telemetry/game --max-rss-gb 40 --out data/sft_v5
uv run python -m autotune.merge_corpus data/sft_v4 data/sft_v5 --out data/sft_v5u
uv run python -m autotune.train_sft --data-dir data/sft_v5_forger --out out/forger/sft
uv run python -m autotune.eval_heldout --adapter out/forger/sft --data-dir data/sft_v5_forger
scripts/package_lora.sh out/forger/sft bdougie/smollm3-pokemon-forger-lora pokemon-forger

# any machine
hf download bdougie/smollm3-pokemon-forger-lora gguf/pokemon-forger.Q4_K_M.gguf
ollama create pokemon-forger:Q4_K_M -f Modelfile      # FROM ./pokemon-forger.Q4_K_M.gguf
```

## Appendix C. What stayed out of reach

| Maps | Measured reason |
|---|---|
| 173, 69, 78, 75, 239, 240 | no warp entrance in the extracted warp table; unreachable by design |
| 226, 227, 228 | a closed pocket on map 3: its 0x50 trees are not cuttable, its gap refuses silently, the south edge lands off map |
| 83 | a tileset-22 facility floor behind map 21's cell (6, 39); the walk wedges interior to interior |
| 28, 81, 102–104 | reached; partially heard |
