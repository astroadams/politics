# Presidential Election Data Visualization

Interactive visualizations of U.S. presidential election results (1976–2024) at the
state, county, and precinct level, built with Dash / Plotly, Panel / GeoViews, and a
Mapbox GL + vector-tile web app.

- `presidential_map.py` – primary Dash dashboard (state margins, partisan lean, EV distribution, trend lines).
- `precinct_level_visualization.py` / `precinct_visualization_panel.py` – hierarchical precinct maps. See [README_PANEL.md](README_PANEL.md).
- `election_app.py` + `tile_server.py` + `generate_vector_tiles.py` – high-performance vector-tile web app. See [README_TILES.md](README_TILES.md).
- Contributor conventions are in [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md).

---

## Data sources and preparation

Everything the apps read lives in `data/`. Files fall into two groups: **downloaded**
(third-party source data, retrieved as-is) and **derived** (produced from the downloaded
files by scripts in this repo). Large downloads and generated geometry are excluded from
git (see [`.gitignore`](.gitignore)); the tables below are the record of where to get
them again and how they were built.

### Downloaded / third-party source data

| File(s) in `data/` | Source | Where it was downloaded from | Retrieved | Preparation on download |
|---|---|---|---|---|
| `1976-2020-president.csv` | MIT Election Data and Science Lab (MEDSL), *U.S. President 1976–2020* | Harvard Dataverse, dataset `10.7910/DVN/42MVDX` (`electionlab.mit.edu/data`) | 2025 (file dated Jul 2025) | Used unchanged. State-level returns; columns `year, state, state_po, state_fips, …, candidatevotes, totalvotes, party_detailed, party_simplified, …`. |
| `1976-2016-president.csv` | MEDSL, *U.S. President 1976–2016*, codebook version `20171101` | Harvard Dataverse `10.7910/DVN/42MVDX` (earlier release) | 2019 | Used unchanged. Superseded by the 1976–2020 file; kept for reference. Field-by-field description in [codebook-us-president-1976-2016.md](codebook-us-president-1976-2016.md). |
| `countypres_2000-2016.csv` | MEDSL, *County Presidential Election Returns 2000–2016* | Harvard Dataverse, dataset `10.7910/DVN/VOQCHQ` | 2019 | Used unchanged. Also the lookup source for human-readable county names (`add_names_to_data.py`). |
| `2020-<st>-precinct-general.tab` (AK, AL, AR, AZ, CO, CT, DC, DE, FL) and `2020-ca-precinct-general.csv` | MEDSL, *2020 U.S. Elections Official Precinct-Level Returns* | `github.com/MEDSL/2020-elections-official` (mirrored on Harvard Dataverse) | Nov 2024 | Used unchanged. `.tab` is the tab-delimited form of the per-state `.csv`; California is kept as `.csv` because of its size (~300 MB). Only a partial set of states was downloaded. |
| `precincts-with-results.geojson` (~900 MB) | The New York Times / The Upshot, *presidential-precinct-map-2020* | `https://int.nyt.com/newsgraphics/elections/map-data/2020/national/precincts-with-results.geojson.gz` (project: `github.com/TheUpshot/presidential-precinct-map-2020`) | Nov 2024 | Downloaded gzipped, then `gunzip`-ed. National precinct polygons with per-precinct `GEOID, votes_dem, votes_rep, votes_total, votes_per_sqkm, pct_dem_lead`. This is the base layer for all derived precinct/county/state geometry below. |
| `ACSST1Y2017.S1501_*`, `ACSST1Y2018.S1501_*`, `ACSST5Y2017.S1501_*`, `ACSST5Y2018.S1501_*` (`_data_with_overlays_*.csv`, `_metadata_*.csv`, `_table_title_*.txt`) | U.S. Census Bureau, American Community Survey table **S1501 – Educational Attainment** (1-year and 5-year estimates, 2017 and 2018) | `data.census.gov` (filename timestamps are the export time) | 2020-04-25 | Used unchanged — raw data.census.gov download bundle (data + column metadata + table-title note). |
| `tl_2019_us_state.shp` / `.dbf` / `.shx` / `.prj` / `.cpg` / `.iso.xml` | U.S. Census Bureau, TIGER/Line 2019 – States (and equivalent) | `www2.census.gov/geo/tiger/TIGER2019/STATE/` | 2019-11-09 | Used unchanged. Fallback state geometry for `generate_state_boundaries_from_csv.py`. |
| `electoral_vote_apportionment.csv` | Congressional apportionment counts by decade (U.S. Census / Clerk of the House "Statistics of the Congressional Election") | Compiled by hand into a small CSV | 2019 | Hand-entered: one row per state, one column per apportionment/census year 1789–2013. `presidential_map.py` adds `+2` to convert House seats to electoral votes. |
| `2024_state_results.csv` | Published 2024 presidential results (national press tabulation – Harris vs. Trump, votes / % / EV by state) | Copied from a published results table; exact outlet not recorded in the repo | 2024 (post-election) | Pasted in as a wide table with header rows; light manual cleanup only. |
| `2024_margin.csv` | Derived from `2024_state_results.csv` | — | 2024 | Hand-computed to match the `margins.csv` schema (no header row): `year, state_po, electoral_votes, margin, margin_text, partisan_lean, partisan_lean_text`. Lets the dashboard show 2024 alongside 1976–2020. |
| `Education.xls` (repo root, not in `data/`) | U.S. Census Bureau, *USA Counties 2011* compendium | `census.gov/library/publications/2011/compendia/usa-counties-2011.html` (see [NOTES.txt](NOTES.txt)) | 2020 | Used unchanged; exploratory only. |

### Derived / generated files

These are produced from the downloaded files by scripts in this repo. Regenerate them
rather than expecting them in git.

| File(s) in `data/` | Produced by | From | Notes |
|---|---|---|---|
| `margins.csv` | `presidential_map.py` (the `prep = True` block, ~lines 162–200) | `1976-2020-president.csv` + `electoral_vote_apportionment.csv` | Per state-year: vote margin `(dem/total − rep/total)*100`, partisan lean `state_margin − national_margin`, electoral votes, and formatted `D+`/`R+` label strings. |
| `states/by_state/<stateFIPS>/precincts/<countyFIPS>_precincts.geojson` | `split_precinct_data.py` | `precincts-with-results.geojson` | Splits the single national file into a state→county hierarchy for lazy loading, using the `GEOID` prefix (`SSCCC…`) for FIPS codes. |
| `states/by_state/<stateFIPS>/counties_<stateFIPS>.geojson`, `states/state_boundaries.geojson` | `create_proper_state_boundaries.py` / `regenerate_state_summaries.py` (also an initial pass in `split_precinct_data.py`); `generate_state_boundaries_from_csv.py` is the shapefile-based fallback | the split precinct files | County and state polygons with vote totals aggregated up from precincts. `add_names_to_data.py` then adds `state_name` / `county_name` using `countypres_2000-2016.csv`. |
| `*.original.geojson` / `*_original.geojson` (e.g. `state_04.geojson` vs `04001_precincts.original.geojson`) | `simplify_geometries_topological.py` | the aggregated geometry above | `*.original` / `*_original` are pre-simplification backups; the un-suffixed files are topologically simplified (shared borders preserved) for faster rendering. |
| `sample.geojson`, `fips24.geojson` | repo geometry-processing scripts | `precincts-with-results.geojson` | Reduced extracts of the national precinct layer (same `GEOID, votes_dem, votes_rep, votes_total, votes_per_sqkm, pct_dem_lead` schema) used for quick tests and the Mapbox app. |
| `tiles/tiles.mbtiles` (in `tiles/`, not `data/`) | `generate_vector_tiles.py` | `states/state_boundaries.geojson` + the by-state county/precinct files | MVT vector tiles, zoom 0–14, state→county→precinct by zoom. See [README_TILES.md](README_TILES.md). |

### Reproducing the derived data

```bash
pip install -r requirements.txt

# 1. Get the base precinct layer (~900 MB uncompressed)
curl -L https://int.nyt.com/newsgraphics/elections/map-data/2020/national/precincts-with-results.geojson.gz \
  | gunzip > data/precincts-with-results.geojson

# 2. Build the state/county/precinct hierarchy
python split_precinct_data.py
python create_proper_state_boundaries.py     # or regenerate_state_summaries.py
python add_names_to_data.py
python simplify_geometries_topological.py

# 3. State-level margins for the Dash dashboard
#    set `prep = True` near the top of presidential_map.py, run once, then set it back
python presidential_map.py

# 4. (optional) Vector tiles for the Mapbox app
python generate_vector_tiles.py
```

State/precinct returns from MEDSL and the Census ACS/TIGER files are re-downloaded from
the URLs in the table above when needed.
