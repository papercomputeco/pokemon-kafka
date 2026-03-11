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
