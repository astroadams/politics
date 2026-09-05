# Repository Guidelines

## Project Structure & Module Organization
- Root: Python scripts for data processing and apps (e.g., `presidential_map.py`, `election_app.py`, `tile_server.py`, `generate_vector_tiles.py`).
- `data/`: CSV/GeoJSON inputs and derived files (e.g., `1976-2020-president.csv`, `margins.csv`, precinct/state geometries).
- `templates/`: Frontend templates (e.g., `mapbox_election_viewer.html`).
- `tiles/`: Vector tile artifacts (e.g., `tiles.mbtiles`).
- `assets/`: Static assets and CSS for Dash.

## Build, Test, and Development Commands
- Install dependencies: `pip install -r requirements.txt`.
- Run Dash dashboard: `python presidential_map.py` (development server at `http://localhost:8050`).
- Generate vector tiles: `python generate_vector_tiles.py [--data-dir data --output-dir tiles --max-zoom 14]`.
- Run tile server: `python tile_server.py --mbtiles tiles/tiles.mbtiles --port 5001`.
- Run web app (Mapbox GL UI): `python election_app.py --port 5000` → open `http://localhost:5000`.
- Health checks: `curl http://localhost:5001/health` (tiles) and `curl http://localhost:5000/health` (app).
- Heroku-style run (production Dash): `gunicorn presidential_map:server` (see `Procfile`).

## Coding Style & Naming Conventions
- Python, PEP 8, 4-space indentation; use `snake_case` for files, functions, and variables.
- Keep scripts single-purpose; prefer small helpers over large monoliths.
- Docstrings: module/function docstrings with concise descriptions and parameter notes.
- Data files go in `data/`; do not import from `assets/` or `templates/` in processing code.

## Testing Guidelines
- No formal test suite yet; add lightweight checks:
  - Validate endpoints locally (see health checks above).
  - Sanity-check derived files: `python -c "import pandas as pd; print(pd.read_csv('data/margins.csv').head())"`.
  - If adding functions, include minimal `if __name__ == '__main__':` demos or assertions.

## Commit & Pull Request Guidelines
- Commits: imperative, present-tense, scoped messages (e.g., "add EV histogram", "update labels").
- PRs must include: purpose and scope, how to run/reproduce, screenshots or GIFs of UI changes, data sources touched, and any follow-ups.
- Link related issues and note any breaking changes or data migrations.

## Security & Configuration Tips
- Large datasets and generated tiles (`tiles/tiles.mbtiles`) should not be committed; prefer instructions to regenerate.
- Mapbox token is only needed for external basemaps; local vector tiles work without it. Configure ports with `--port` flags to avoid conflicts.
- Pre-commit hook to block large files: enable with `git config core.hooksPath .githooks`. The hook rejects staged files > 50MB.
