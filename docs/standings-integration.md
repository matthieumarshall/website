# Standings Integration — pyresults + website

## Overview

The goal was to integrate the `pyresults` library into the website so that
league standings are automatically calculated from uploaded race results and
displayed in a dedicated Standings page.

The integration is purely in-memory: the website queries DuckDB for race
results, passes them to pyresults scoring services as domain objects, and then
writes the computed standings back to DuckDB. No intermediate CSV files are
used.

---

## Original Plan

### Design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Scoring rule | Position-based (lower = better) | Matches OXL scoring |
| Data flow | In-memory (no filesystem) | Website has no CSV store; avoids coupling |
| Entry point | Pre-calculate + store standings | Fast page loads; can re-run after edits |
| Coverage | Current season + historic import | Both live and past seasons need standings |
| Wheel hosting | GitHub Releases via Actions | Simple; no PyPI account needed |
| Fixture ordering | Sort by date ASC → r1, r2, r3… | Fixtures already sorted this way in the website |
| Category validation | Two-step normalise in seed_results.py + Pydantic validator | Catches bad data at import time |

### Scoring rules

- **Individual**: sum of best N−1 of N round scores (lowest total wins). Each score is the finishing position within the category.
- **Team**: sum of all rounds (no drop), top K athletes per club per round contribute. Lowest total wins.

### Round assignment

Fixtures within a season are sorted by `date ASC`. The first fixture becomes
`r1`, the second `r2`, etc. This mapping is computed fresh at each
recalculation and is never stored — the fixture table is the source of truth.

---

## Changes to pyresults

### Making heavy dependencies optional

`pandas`, `numpy`, `openpyxl`, and `fpdf` were moved from required dependencies
to an `[output]` optional extras group in `pyproject.toml`. The core library
(domain models, in-memory repos, scoring services) now runs with only
`python-dateutil`.

Modules that still need pandas (`RaceProcessorService`, `CsvRaceResultRepository`,
`CsvScoreRepository`, `CsvTeamResultRepository`) guard their imports with
`try/except ImportError` pointing to `pip install 'pyresults[output]'`.

`RaceProcessorService` is also excluded from `services/__init__.py` behind a
`try/except` so the services package itself is importable without pandas.

### New interface: ITeamResultRepository

Added to `repositories/interfaces.py`:

```python
class ITeamResultRepository:
    def load_team_results(self, category_code: str, round_number: str) -> list[dict]: ...
    def save_team_results(self, category_code: str, round_number: str, data: list[dict]): ...
    def team_results_exist(self, category_code: str, round_number: str) -> bool: ...
```

### New file: CsvTeamResultRepository

Extracted CSV team-result I/O from `TeamScoreService` into its own repository
class (`repositories/csv_team_result_repository.py`). Reads/writes
`{base_path}/{round_number}/teams/{category_code}.csv`.

### TeamScoreService refactored

Old constructor: `TeamScoreService(config, race_result_repo, team_scoring_service)`

New constructor: `TeamScoreService(config, race_result_repo, team_result_repo, team_score_repo, team_scoring_service)`

The service no longer does any pandas I/O directly — it reads via
`ITeamResultRepository` and writes via `IScoreRepository`.

### CsvScoreRepository: rounds_to_drop parameter

Added `rounds_to_drop: int = 1` (default keeps existing behaviour for
individual scores). Pass `rounds_to_drop=0` for team scores (all rounds count).

### New file: in_memory_repositories.py

Three classes for use by the website (no filesystem, no pandas):

- `InMemoryRaceResultRepository`
- `InMemoryScoreRepository` — also exposes `all_scores() -> dict[str, list[Score]]`
- `InMemoryTeamResultRepository` — normalises all dict keys to lowercase on save

### Public API (pyresults/\_\_init\_\_.py)

Exports all domain models, services, repository interfaces + in-memory
implementations, config helpers, plus a new utility function:

```python
def get_valid_category_codes() -> frozenset[str]:
    """Return all valid category codes for this competition."""
```

### GitHub Actions release workflow

`.github/workflows/release.yml` — triggers on `v*` tags, runs `uv build`,
uploads `dist/*` to GitHub Releases. The website can then depend on the wheel
via a direct URL.

---

## Changes to the website

### Migration 0009 — standings tables

Two new tables in `migrations/0009_create_standings.sql`:

**`individual_standings`**

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| season_id | INTEGER FK | → seasons |
| category | VARCHAR | pyresults category code e.g. `SM`, `WV40` |
| position | INTEGER | rank within category |
| athlete_name | VARCHAR | |
| club | VARCHAR | |
| total_score | INTEGER | lower = better |
| rounds_competed | INTEGER | |
| fixture_scores | VARCHAR | JSON `{"fixture_id": position, …}` |
| is_imported | BOOLEAN | true = historic; never overwritten by recalc |
| updated_at | TIMESTAMP | |

**`team_standings`** — same plus `team_name`, `club`, `team_label` (A/B/C).

Indexes on `(season_id, category)` for both tables.

### src/website/standings.py — bridge module

Main entry point: `recalculate_standings(db, season_id)`.

Flow:

1. `list_fixtures_for_season()` → build `round_for_fixture` dict (`{fixture_id: "r1", …}`)
2. For each fixture, for each race, for each result → build `DomainRaceResult` with `Athlete` objects → `race_result_repo.save_race_result()`
3. Per-round team scoring: `TeamScoringService.calculate_teams_for_race()` → `team_result_repo.save_team_results()`
4. `IndividualScoreService.update_all_categories()` using the in-memory race result repo
5. `TeamScoreService.update_all_team_categories()` using the in-memory team result repo
6. Delete non-imported rows for the season, bulk-insert new standings

Helper `_build_season_config(round_numbers)` constructs a `CompetitionConfig`
from the OXL defaults but overrides `round_numbers` dynamically per season and
sets `data_base_path = Path("/dev/null")` (never accessed).

Helper `_parse_time(str)` handles timing system output formats:
`"0 days 00:29:27"`, `"00:29:27"`, `"29:27"`.

### src/website/repository.py — standings functions

- `load_individual_standings(db, season_id, category=None) -> list[dict]`
- `load_team_standings(db, season_id, category=None) -> list[dict]`
- `list_standing_categories(db, season_id) -> list[dict]` — returns `{category, type, count}` records
- `season_has_standings(db, season_id) -> bool`

### src/website/main.py — standings routes

| Method | Path | Description |
|---|---|---|
| GET | `/standings` | Main standings page (season selector) |
| GET | `/standings/category-panel` | HTMX partial — category tab buttons |
| GET | `/standings/table` | HTMX partial — standings table for one category |
| POST | `/standings/recalculate` | Admin-only; triggers `recalculate_standings()` |

Admin check uses `get_active_principals(request)` (consistent with other admin routes).

### Templates

- `standings.html` — main page, mirrors `results.html` structure with a season selector and HTMX target
- `_standings_category_panel.html` — Individual / Team heading groups with category buttons; admin "Calculate standings" / "Recalculate standings" form
- `_standings_table.html` — position, name/team, club, one column per fixture (R1…RN), total, rounds competed; explanatory note for drop-round rule

### Sidebar navigation

"Standings" added to `SIDEBAR_ITEMS` in `src/website/helpers.py`, between Results and Entries.

### Category normalisation — seed_results.py

`_normalise_category(raw_category, gender)` is called at CSV import time.
Priority:

1. Exact match against `get_valid_category_codes()` (case-insensitive)
2. Gender-dependent veteran map: `("male", "v40") → "MV40"`, `("female", "v40") → "WV40"`, etc.
3. Unambiguous display-name map: `"senior men" → "SM"`, `"u13 boys" → "U13B"`, etc.
4. Pass through unchanged with a `stderr` warning

This means existing CSVs from the timing system (which use display names like
"Senior Men", "V40", "U11 Boys") are automatically normalised to pyresults
codes on import.

### pyresults dependency

For local development: `pip install -e ../pyresults` (no pandas — core only).

For production: add to `pyproject.toml` dependencies as a direct wheel URL:
```
pyresults @ https://github.com/matthieumarshall/pyresults/releases/download/v0.1.1/pyresults-0.1.0-py3-none-any.whl
```

### Pre-commit fixes

The `djlint` hook was changed from `language: system` (using `uv run djlint`)
to `language: python` with `additional_dependencies: ["djlint>=1.36.4"]`.
The `uv run` approach fails on Windows due to script path canonicalization.

---

## Test coverage

All **170 pyresults tests** and **258 website unit tests** pass after the integration.

The one test that needed updating was `test_sidebar_items_has_six_entries` → `test_sidebar_items_has_seven_entries` and the set of expected page keys gained `"standings"`.
