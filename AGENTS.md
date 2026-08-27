# Project Guidelines

## Toolchain

- Always use `uv` instead of `python3`, `pip`, or `python`. Examples:
  - `uv run pytest` not `python3 -m pytest`
  - `uv run ruff check` not `ruff check`
  - `uv sync --group dev` to install dependencies
  - `uv run python script.py` not `python3 script.py`

## Linting

- Ruff is configured in `pyproject.toml` (rules: E, F, I, W; line-length: 120)
- Run `uv run ruff check .` and `uv run ruff format --check .` before committing
- Git hooks enforce this: `git config core.hooksPath .githooks`

## Testing

- Run tests: `uv run pytest --cov --cov-report=term-missing`
- All test files in `tests/`; scripts on pythonpath via `pyproject.toml`

## Ground truth — learn the game by playing the game

The game has multiple versions; recalled Pokémon knowledge hallucinates across them. No
recalled game fact (map ids, species/item/type ids, encounter pools, story mechanics, RAM
addresses) may be load-bearing in code, tests, missions, or navigation. The measured cost of
breaking this: a hand-typed species map hid 6,515 wild Paras sightings as "Metapod", the type
map had two pairs swapped and mis-scored every battle for months, and a recalled RAM address
wasted a probe session.

- **Structures** come from `rom/pokemon_red.gb` via `scripts/rom_truth.py` — tables located by
  content signature, never by remembered address (maps, warps, collision, tile pairs, ledges,
  species/types/catch rates, wild encounter pools).
- **Behavior and story** are measured live: probes, screenshots, RAM reads, and cutscene
  `discovery` events. What the game says on screen is the instruction stream.
- The encounter catalog (`scripts/encounters.py`) cross-checks extraction against telemetry;
  a disagreement is a decode bug, not a footnote.
- Recalled lore may generate hypotheses to test — never conclusions to ship.
