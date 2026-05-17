# Implementation Plan: Import Legacy Results and Standings

**Branch**: `fix_standings` | **Date**: 2026-05-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-import-results-standings/spec.md`

## Summary

Import historical results and standings from legacy PDF data (`data/original_website/files/results`) into DuckDB without transformation. The feature extends existing `migrate_results.py` and `migrate_standings.py` scripts to auto-create missing seasons/fixtures, handle malformed data gracefully (with logging), and support replace-on-rerun via `--force` flag. Historical data will be immediately browseable via the existing `/results` and `/standings` UI, which already supports season/fixture/race filtering and CSV/PDF export.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: pdfplumber (PDF parsing), pandas (data manipulation), DuckDB (persistent storage), FastAPI (CLI framework)
**Storage**: DuckDB with persistent file at `data/app.duckdb`
**Testing**: pytest with `:memory:` DuckDB for isolation
**Target Platform**: CLI admin tools + web browsing interface
**Project Type**: FastAPI web service + Python CLI scripts
**Performance Goals**: Import 10+ years of data in <5 minutes
**Constraints**: No computation on imported data; preserve values exactly as-is; log all data quality issues
**Scale/Scope**: ~40 seasons × ~5 fixtures/season × ~2-3 races/fixture × ~100-300 results/race = ~400k+ result records

## Constitution Check

✅ **Test-Driven Quality**: 85% coverage target. New import logic requires unit tests covering PDF parsing, DB inserts, auto-creation, and error handling. UI tests verify historical data displays.

✅ **Code Style & Type Safety**: Type hints on all function signatures. Snake_case naming. Docstrings for public functions. Comments explain non-obvious logic (e.g., season auto-creation strategy).

✅ **Security First**: Parameterised DuckDB queries (no SQL injection risk). No hardcoded secrets. Bandit scan passes. CSRF validation on any future admin UI for import triggers.

✅ **Modular Design & Dependency Injection**: Separate modules for PDF parsing logic, DB operations, import coordination. All DB operations pass `duckdb.DuckDBPyConnection` via `Depends(get_db)` or function parameters.

✅ **Collaborative Development**: Commits follow "verb + what was done" format. PR description documents migration strategy + any data quality findings. Pre-commit hooks enforced.

**No violations.**

## Project Structure

### Documentation (this feature)

```text
specs/001-import-results-standings/
├── plan.md                  # This file
├── research.md              # Phase 0 (resolved clarifications)
├── data-model.md            # Phase 1 output
├── quickstart.md            # Phase 1 output
├── contracts/               # Phase 1 output (N/A for CLI scripts)
└── tasks.md                 # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
scripts/
├── migrate_results.py       # Enhanced: auto-create seasons/fixtures, replace mode
├── migrate_standings.py     # Enhanced: replace mode, logging
├── _migration_helpers.py    # Enhanced: new helpers for auto-creation, logging
└── _import_logger.py        # NEW: structured import logging

src/website/
├── models.py                # Existing Pydantic models (Season, Fixture, Race, Result)
├── repository.py            # Existing: add helper queries for duplicate detection
└── database.py              # Existing: DB connection + migrations (no changes needed)

tests/unit/
├── test_migrate_results.py  # NEW: PDF parsing, season/fixture auto-creation
├── test_migrate_standings.py # NEW: standings parsing, replace logic
└── test_migration_helpers.py # NEW: helper functions for import

tests/ui/
└── test_historical_results_browsing.py  # NEW: verify historical data displays in UI
```

**Structure Decision**: Single Python project (existing FastAPI + scripts layout). Extensions to `scripts/` folder for enhanced import logic. Tests in `tests/unit/` and `tests/ui/` following existing convention.

## Complexity Tracking

No violations of constitution. Design follows existing patterns:
- Reuse existing PDF parsing logic from `migrate_results.py`
- Reuse existing DB connection / migration pattern from `database.py`
- Reuse existing UI components (`/results` page) for browsing
- No new external dependencies required (pdfplumber already installed)

---

## Phase 0: Research & Clarification

**Status**: ✅ Complete (clarifications documented in spec.md)

### Resolved Questions

1. **Update existing records on re-run?** → YES, with `--force` flag to replace
2. **Handle malformed/missing fields?** → Import with NULL; log warnings
3. **Auto-create seasons?** → YES, from folder names
4. **Auto-create fixtures?** → YES, from filename metadata (date + venue)
5. **Discover existing UI routes?** → YES, `/results` and `/standings` routes exist and ready for data

### Key Findings

- **Existing infrastructure**: `/results`, `/standings` pages already built; just need data
- **PDF structure**: All result files follow `YYYYMMDD-RndN-VenueName-min.pdf` pattern; table structure is stable
- **Standings data**: Only 2023-24, 2024-25, 2025-26 seasons have standings PDFs
- **Database ready**: DuckDB schema supports all needed fields; migrations in place

**Output**: [research.md](research.md)

---

## Phase 1: Design & Data Model

### 1. Entity Data Model

**Result (imported from PDF)**
- Fields: position (int), athlete_name (str), time (str), category (str), gender (str)
- Optional: race_number (int), category_position (int), gender_position (int), club (str)
- Source: PDF table rows; import as-is without computation
- Validation: position must be numeric; athlete_name must be non-empty (warn if empty)
- Deduplication: Skip if (race_id, athlete_name, time) tuple already exists and not `--force`

**Standing (imported from PDF)**
- Fields: position (int), athlete_name/team_name (str), club (str), total_score (int)
- Optional: rounds_competed, fixture_scores (JSON)
- Flag: is_imported = true (prevents recalculation)
- Validation: position must be numeric; name must be non-empty (warn if missing)
- Deduplication: Delete all standings for (season_id, category) if `--force`; then insert fresh

**Season (auto-created)**
- Identified by: folder name (e.g., "1988-1989")
- Created if missing: auto-create with name = folder name
- No computation needed; just ensure exists before inserting fixtures

**Fixture (auto-created)**
- Identified by: date + season_id (from filename date + folder name)
- Created if missing: parse `YYYYMMDD` from filename, create fixture with title = venue name from filename
- Deduplication: Check by (season_id, date); skip if exists and not `--force`

**Race**
- Identified by: (fixture_id, name) — extracted from PDF section headings
- Display order: assigned based on category keywords (U9, U11, …, Seniors, Veterans)
- Deduplication: Skip if race already exists for this fixture

### 2. Import Process Flow

```
For each decade folder (1987-1990, …, 2020-2030):
  For each season subfolder (1988-1989, …, 2025-2026):
    → Auto-create Season if missing

    For each PDF file (20210101-Rnd1-Venue-min.pdf, …):
      → Extract date, round, venue from filename
      → Auto-create Fixture if missing (date + season)
      → Parse PDF tables for races/results

      For each race (Men, U13, …):
        → Create Race record
        → For each result row:
            → Import with all fields (NULL where missing)
            → Log warnings for data quality issues
```

### 3. Error & Logging Strategy

**Import Log**: JSON-lines format to `data/import_YYYYMMDD_HHMMSS.log`
```json
{"level": "info", "stage": "season_create", "season": "1988-1989", "season_id": 1}
{"level": "warning", "file": "20210101-Rnd1-Venue-min.pdf", "issue": "missing_athlete_name", "row_index": 5}
{"level": "error", "file": "20210101-Rnd1-Venue-min.pdf", "issue": "parse_failed", "reason": "no_tables_found"}
```

**Summary Report**: Print to stdout after import
```
Import Summary (2026-05-09 14:30:00)
─────────────────────────────────────
Results: 12,450 imported | 23 warnings
Standings: 1,230 imported | 5 warnings
Seasons created: 12
Fixtures created: 187
Duration: 3m 45s
```

### 4. Implementation Modules

**scripts/_import_logger.py** (NEW)
- Class: `ImportLogger(log_file: Path | None)`
- Methods: `info()`, `warning()`, `error()`, `summary()`
- Output: JSON lines + stdout summary

**scripts/_migration_helpers.py** (ENHANCED)
- New: `create_season_if_missing(con, season_name) → int`
- New: `create_fixture_if_missing(con, season_id, fixture_date, venue_name) → int`
- New: `fixture_exists(con, season_id, fixture_date) → bool`
- New: `result_exists(con, race_id, athlete_name, time) → bool`

**scripts/migrate_results.py** (ENHANCED)
- New: `--force` flag to replace existing results
- New: Auto-create seasons/fixtures
- New: Track & log data quality issues
- New: Support `--dry-run` mode (parse, no DB writes)
- Signature: `uv run python scripts/migrate_results.py [--season YYYY-YYYY] [--dry-run] [--force]`

**scripts/migrate_standings.py** (ENHANCED)
- New: `--force` flag to delete + re-import all standings for season
- New: Auto-create seasons if missing
- New: Track & log data quality issues
- New: Support `--dry-run` mode
- Signature: `uv run python scripts/migrate_standings.py [--dry-run] [--force]`

**tests/unit/test_migrate_results.py** (NEW)
- Test PDF parsing edge cases (empty tables, missing columns, malformed data)
- Test season auto-creation
- Test fixture auto-creation from filename
- Test result insertion with NULL values
- Test `--force` replace behavior
- Test dry-run mode (no DB changes)
- Coverage: ≥85% of new logic

**tests/unit/test_migration_helpers.py** (NEW)
- Test `create_season_if_missing()` idempotency
- Test `create_fixture_if_missing()` date parsing
- Test deduplication checks
- Coverage: 100% (critical path)

**tests/ui/test_historical_results_browsing.py** (NEW)
- After import, verify `/results` page displays all seasons
- Verify `/results?season_id=X` shows historical fixtures
- Verify historical results are filterable/exportable
- Verify `/standings` page displays historical season standings

### 5. Quickstart for Admin

After import completes, users can:
1. Navigate to `/results` → select historical season (e.g., "1988-1989")
2. Browse fixtures, races, and results just like current data
3. Export results to CSV/PDF
4. View `/standings` → select historical season to see end-of-season standings

No additional UI needed; existing components handle all interactions.

**Output**:
- [data-model.md](data-model.md) — detailed entity definitions
- [quickstart.md](quickstart.md) — admin usage guide
- [contracts/](contracts/) — N/A (internal import, no API contracts)

---

## Phase 2: Implementation Tasks

*(Generated by `/speckit.tasks` — not included in this plan)*

See [tasks.md](tasks.md) for breakdown of all actionable work items, dependencies, and sequencing.

---

## Timeline & Dependencies

**Phase 0** (Complete): Clarification
- Resolved all unknowns from spec

**Phase 1** (This document): Design
- Technical context + entity model defined
- Import flow documented
- Logging strategy specified
- Modules defined

**Phase 2** (Next step): Task generation via `/speckit.tasks`
- Creates actionable tasks with dependencies
- Sequences implementation (parsing → DB layer → integration → tests → UI verification)

**Estimated effort**:
- PDF parsing & helpers: 4-6 hours
- DB layer (auto-creation + logging): 3-4 hours
- Testing (unit + UI): 4-5 hours
- Integration & final validation: 2-3 hours
- **Total**: 13-18 hours
