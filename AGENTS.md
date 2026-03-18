# Repository Guidelines

## Project Structure & Module Organization
- fast_trade/: core library (backtesting engine, indicators, CLI)
  - run_backtest.py, build_data_frame.py, build_summary.py, finta.py
  - cli.py (entrypoint `ft`), archive/ (data download/update helpers)
- test/: pytest suite (`test_*.py`)
- saved_backtests/: optional output when using `ft backtest --save`
- example_backtest.yml, strategy.yml: reference strategies
- pyproject.toml: packaging, deps, and console script
- the virtual env is literally `venv/` use `source venv/bin/activate`

## Docker Container Management
- After completing a bug fix, feature, or any change in `fast_trade/`, you MUST restart the relevant containers to ensure the Python interpreter picks up the changes (especially as uvicorn workers and Celery do not always auto-reload).
- Command: `docker compose restart api-gateway backtest-worker data-ingestor`

## Build, Test, and Development Commands
- Setup (editable): `python -m venv .venv && source .venv/bin/activate && pip install -e .`
- Run tests: `pytest` (or `python -m pytest`)
- Coverage: `coverage run -m pytest && coverage report -m`
- Lint: `flake8` (configured via `.flake8`, max line length 122)
- CLI help: `ft -h`
- Quick run: `ft backtest ./strategy.yml [--save] [--plot]`
- Download data: `ft download BTCUSDT binanceus --start 2024-12-01 --end 2025-01-01`

## Agent Usage Notes
- Prefer YAML for strategies and configs (`.yml/.yaml`). JSON is deprecated in examples.
- Use `ft terminal` for interactive browsing of backtests and strategies.
  - Shortcuts: `TR`, `SUM`, `GP`, `POS`, `OPEN BT`, `OPEN STRAT`, `EDIT`, `RUN`, `SAVE`, `N/P`, `Q`.
  - `EDIT` writes `strategy.override.yml` in the backtest run folder.
- Use `ft backtests list` / `ft backtests show --index N` for non‑interactive environments.
- Use `ft evolve evolver_example.yml` for GA runs (config is YAML).

## Coding Style & Naming Conventions
- Python 3.8+; 4‑space indentation; prefer type hints where practical.
- Use snake_case for modules/functions/variables; CapWords for classes.
- Keep functions small and fast; avoid unnecessary allocations in hot paths.
- Lint with `flake8` (line length 122; excludes build/dist/test per `.flake8`).
- Public API lives under `fast_trade/`; avoid breaking changes without discussion.

## Testing Guidelines
- Framework: `pytest`; place unit tests in `test/` as `test_*.py`.
- Aim for focused, deterministic tests (no network calls). Use small CSV/fixtures.
- Cover new logic in `run_backtest.py`, `build_summary.py`, and helpers.
- Validate strategies with `validate_backtest` where relevant.
- Measure coverage with `coverage`; source is configured to `./fast_trade` in `.coveragerc`.

## Commit & Pull Request Guidelines
- Commits: short, imperative summaries (e.g., "fix archive update"); keep changes scoped.
- Reference issues (e.g., `#123`) when applicable; include rationale in the body.
- PRs must include: clear description, before/after behavior, test coverage, and docs/README updates when user‑facing.
- Ensure `pytest`, `flake8`, and coverage run clean locally before requesting review.

## API Contract & UI Synchronization
- **Source of Truth**: The API contract is defined in [`api-contract.ts`](file:///mnt/projects/News-Dashboard/src/app/types/api-contract.ts).
- **Requirement**: Whenever you modify the backend API (specifically in `fast_trade/services/api.py`), you **MUST** update the corresponding TypeScript interfaces in `api-contract.ts`.
- **Scope**: This applies to `BacktestRequest`, `BacktestResult`, `LeaderboardEntry`, `Preset`, and `OptimizeRequest`.
- **Validation**: Ensure that field names, types, and optionality match exactly between the Pydantic models in Python and the TypeScript interfaces.

## Security & Configuration Tips
- Do not commit real secrets; use a local `.env` only for development. No API keys are required for archive downloads.
- Archive path defaults to `./archive` when using the CLI; prefer this in examples.
