# The Forger regated on v6u, by random split and by map — 2026-09-07 late

The question behind this regate: does the adapter read sentences, or remember Red's coordinates? And when
it meets a sentence no row covered, does it say so or name the nearest story? Both were asked with data.

## What changed in the corpus (v5u → v6u, `bdougie/pokemon-red-sft`)

- 27,836 → 28,003 rows. npc-dialogue 1,318 → 1,357 (the Forger's three seated arcs). gate-text 82 → 101.
- `thirsty_guard`: the Saffron gate house guard, measured across seven saves (10 rows).
- `unclassified`: refused steps whose sentence no class knows, labelled as such with a clears text that sends
  the crew to measure (8 rows, capped at three per distinct sentence, prose only, refused-step events only).
  Before this every gate-text row had a known class, so "not one I know" was never an answer the model had
  seen — which is why lane 33's adapter named `script_guard` for the guard and ran away.

## Two gates

Same recipe (SmolLM3-3B, bf16 LoRA r32, 3 epochs), two adapters:

| split | rows | body base → tuned | outcome base → tuned (majority) | gate base → tuned |
|---|---:|---|---|---|
| random: 10 % of Forger rows, same maps and runs | 154 | 0.25 → **0.89** | 0.39 → **0.63** (0.54) | 0.00 → **0.80** (8/10) |
| by map: 29 of 192 maps held out entirely; the adapter trained without them | 370 | 0.22 → **0.90** | 0.39 → **0.64** (0.55) | 0.00 → **0.89** (16/18) |

Both passed the gate rule (tuned ≥ base on every metric, tuned > every majority). Training: 261 steps,
about 9 minutes each on the 5090.

## What the by-map number means

On maps the adapter had never seen, body accuracy is the same as on familiar ones (0.90 vs 0.89) and the gate
class is read at 16/18. If the body head were a lookup of Red's sprite table by coordinates it would have fallen
toward the base's 0.22 on those maps. It did not: it reads the sentence and the sprite picture. The outcome head
is the same nine points over the majority on both splits; its ceiling is the label's (stale-vs-talk timing,
fights the sentence does not show), not the maps'.

This is the answer to "will it just give up on a new NPC": it never gave up, and now on an unseen map it reads
as well as at home. Whether it says "unclassified" on an unseen *gate* the two gates only sample (the
unclassified rows are 8 of 101); the next walk-into-a-new-gate arc measures it live.

## Published

- Adapter: `bdougie/smollm3-pokemon-forger-lora` (random-split adapter; `eval.json` carries both gates and the
  held-out map list). The by-map adapter stays local at empirical-evidence `out/forger_bymap/sft`.
- Corpus: `bdougie/pokemon-red-sft` v6u. Doc: empirical-evidence `docs/forger-adapter.md`.
- The GGUF and the local Ollama model were first repackaged from a *stale* merge (the packaging script reused
  every existing file); fixed in empirical-evidence `scripts/package_lora.sh` and repackaged.

## Next

1. A walk-into-a-new-gate arc with the v6 adapter seated: does it say `unclassified` on a sentence it has not seen?
2. The first vote: a `stale` reading keeps a body out of the heard catalog.
3. A Yellow lane, when a Yellow ROM is in `rom/`: rows named by game, gated `--by-game`.
