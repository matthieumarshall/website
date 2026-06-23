# Import Scripts Documentation

This directory contains Python scripts for importing historical results and standings from legacy PDFs into the DuckDB database.

## Overview

**Imported Data**:
- Historical race results (1988–2025, ~40 years)
- End-of-season standings (recent seasons: 2024–2025)

**Source Data**:
- PDFs: `data/original_website/files/results/` (organized by season: `YYYY-YYYY/`)
- PDF naming format: `YYYYMMDD-RndN-VenueName-min.pdf`
- Filename is parsed to extract race date and venue

**Output**:
- Records inserted into `results`, `individual_standings`, `team_standings` tables
- Log file: `data/import_YYYYMMDD_HHMMSS.jsonl` (JSON-lines format with structured logging)
- Summary printed to console after completion

---

## Scripts

### `migrate_results.py`

Imports historical race results from PDF files.

#### Usage

```bash
# Basic import (process all seasons)
uv run python scripts/migrate_results.py

# Options:
uv run python scripts/migrate_results.py --dry-run          # Preview only (no DB changes)
uv run python scripts/migrate_results.py --force            # Delete & re-import all results
uv run python scripts/migrate_results.py --season 2021-2022 # Import only 2021-2022
uv run python scripts/migrate_results.py --dry-run --force --season 2024-2025  # Combine options

# Batch CSV import
The `scripts/seed_results_batch.py` script can import all races from a folder tree of round CSVs.

Example:
```bash
uv run python scripts/seed_results_batch.py "2025-2026" \
    C:\Users\MatthieuMarshall\Documents\Admin\personal\course_a_pied\pyresults\input_data
```

Each round folder should be named like `r1`, `r2`, or `Round 1`, and each CSV file in that folder is imported as a separate race.

#### How It Works

1. **Discovers PDF files** in `data/original_website/files/results/YYYY-YYYY/` subdirectories
2. **Parses each PDF**:
   - Extracts tables from PDF pages
   - Maps columns to expected fields: position, athlete_name, club, category, gender, time
   - Skips rows with invalid position values (non-numeric)
   - Logs warnings for missing fields
3. **Auto-creates infrastructure**:
   - Season record (if not exists): `create_season_if_missing(con, season_name)`
   - Fixture record (if not exists): `create_fixture_if_missing(con, season_id, date, venue)`
   - Race record (if not exists): extracted from PDF filename
4. **Deduplicates results**: Checks `result_exists(con, race_id, athlete_name, time)` before insert
5. **Inserts results** with all available fields (NULL for missing values)
6. **Logs everything**:
   - Info: import stages, counts
   - Warning: missing fields, malformed values, duplicates
   - Error: PDF parse failures, DB errors

#### Options

| Option | Description | Example |
|---|---|---|
| `--dry-run` | Parse PDFs but skip all DB writes | `--dry-run` |
| `--force` | Delete existing results before re-import | `--force` |
| `--season YYYY-YYYY` | Import only specified season | `--season 2021-2022` |

#### Output

**Success**:
```
════════════════════════════════════════════════════════════
Import Summary — 2026-05-09 14:35:00
════════════════════════════════════════════════════════════
Stages completed: 2 (import_start, import_complete)
By level:
  info:      102
  warning:    45
  error:      2
Duration: 3m 42s
Log file: data/import_20260509_143500.jsonl
════════════════════════════════════════════════════════════
```

**Dry-run** (no DB writes):
```
[DRY-RUN] Would import 150 results from data/original_website/files/results/2021-2022/
Log created: data/import_20260509_143500.jsonl
```

---

### `migrate_standings.py`

Imports historical end-of-season standings from PDF files.

#### Usage

```bash
# Basic import (process all seasons with standings)
uv run python scripts/migrate_standings.py

# Options:
uv run python scripts/migrate_standings.py --dry-run          # Preview only
uv run python scripts/migrate_standings.py --force            # Delete & re-import
uv run python scripts/migrate_standings.py --season 2024-2025 # Import only 2024-2025
```

#### How It Works

1. **Discovers PDF files** in `data/original_website/files/standings/YYYY-YYYY/` (or similar)
2. **Parses standings tables**:
   - Extracts individual standings (position, athlete_name, total_score, etc.)
   - Extracts team standings (team_label A/B/C, total_score, etc.)
   - Handles category headers in PDF text (e.g., "Senior Men", "U13 Boys")
3. **Auto-creates season** if missing: `create_season_if_missing(con, season_name)`
4. **Marks imported standings** with `is_imported=true` to prevent recalculation
5. **Inserts records** into `individual_standings` and `team_standings` tables
6. **Logs warnings/errors** for data quality issues

#### Options

Same as `migrate_results.py`:
- `--dry-run`: Preview only
- `--force`: Delete and re-import
- `--season YYYY-YYYY`: Specific season only

---

## Support Modules

### `_import_logger.py`

Centralized JSON-lines logging for imports.

**Key Methods**:
- `info(stage, **fields)`: Log info-level entry
- `warning(stage, **fields)`: Log warning entry
- `error(stage, **fields)`: Log error entry
- `summary()`: Print human-readable summary to console
- `write_summary(path)`: Write summary to text file
- `get_log_file_path()`: Get path to JSON-lines log

**Example**:
```python
from _import_logger import ImportLogger

logger = ImportLogger(log_file=Path("data/import.jsonl"))
logger.info("import_start", season="2021-2022")
logger.warning("result_missing_field", field="athlete_name", race_id=5)
logger.error("pdf_parse_error", pdf_file="bad.pdf", error="No tables found")
logger.info("import_complete", total_results=100)
print(logger.summary())
```

### `_migration_helpers.py`

Reusable utilities for database operations during import.

**Key Functions**:

```python
# Season management
season_id = create_season_if_missing(con, "2021-2022") -> int

# Fixture management
fixture_id = create_fixture_if_missing(con, season_id, date(2021, 1, 1), "Bicester") -> int
exists = fixture_exists(con, season_id, date(2021, 1, 1)) -> bool

# Result deduplication
exists = result_exists(con, race_id=5, athlete_name="John Smith", time="25:30") -> bool

# Standing deduplication
exists = standing_exists(con, season_id=5, category="SM40", position=1) -> bool
```

All functions use parameterized SQL queries (no SQL injection risk).

---

## Data Quality & Logging

### Warning Categories

**Result Import**:
- `result_missing_field`: Missing athlete_name, time, position, or other required field
- `result_malformed_position`: Position value is not numeric (e.g., "DNF")
- `result_duplicate_skipped`: Result already in DB (skipped unless `--force`)

**Standings Import**:
- `standings_missing_field`: Missing position or total_score
- `standings_duplicate_skipped`: Standing already imported

**PDF Parsing**:
- `pdf_parse_error`: Could not extract table from PDF (import continues)
- `pdf_missing_file`: File referenced in config not found

### Error Categories

- `database_insert_failed`: DuckDB rejected the INSERT
- `season_creation_failed`: Could not create season record
- `fixture_creation_failed`: Could not create fixture record

### Handling Issues

| Issue | Action |
|---|---|
| Many missing fields in a season | Review PDF; may indicate OCR error or formatting change |
| Duplicate warnings with `--force` | Expected behavior; `--force` deletes all, then re-imports from scratch |
| PDF parse failures for some files | Check PDF is valid; may be corrupt or unsupported format |
| Database insert failures | Check schema; verify DuckDB is writable |

---

## Performance

Typical import times on modern hardware:

| Task | Time |
|---|---|
| Results only (all seasons) | 3–5 minutes |
| Standings only (recent seasons) | 30–60 seconds |
| Full import (both) | 5–6 minutes |

Import is I/O-bound (PDF parsing time dominates). Parallelization possible but not implemented in v1.

---

## Architecture

### Database Schema (Relevant Tables)

```sql
-- Seasons
CREATE TABLE seasons (
  id INTEGER PRIMARY KEY,
  season_name TEXT UNIQUE NOT NULL
);

-- Fixtures (dates with races)
CREATE TABLE fixtures (
  id INTEGER PRIMARY KEY,
  season_id INTEGER NOT NULL,
  fixture_date DATE NOT NULL,
  location TEXT,
  UNIQUE(season_id, fixture_date),
  FOREIGN KEY (season_id) REFERENCES seasons(id)
);

-- Races (individual races at a fixture, e.g., "Men", "Women")
CREATE TABLE races (
  id INTEGER PRIMARY KEY,
  fixture_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  display_order INTEGER,
  UNIQUE(fixture_id, name),
  FOREIGN KEY (fixture_id) REFERENCES fixtures(id)
);

-- Historical results
CREATE TABLE results (
  id INTEGER PRIMARY KEY,
  race_id INTEGER NOT NULL,
  position INTEGER,
  athlete_name TEXT,
  club TEXT,
  category TEXT,
  gender TEXT,
  time TEXT,
  FOREIGN KEY (race_id) REFERENCES races(id)
);

-- Individual standings
CREATE TABLE individual_standings (
  id INTEGER PRIMARY KEY,
  season_id INTEGER NOT NULL,
  position INTEGER NOT NULL,
  athlete_name TEXT NOT NULL,
  club TEXT,
  category TEXT,
  total_score NUMERIC,
  is_imported BOOLEAN DEFAULT FALSE,
  UNIQUE(season_id, position, category),
  FOREIGN KEY (season_id) REFERENCES seasons(id)
);

-- Team standings
CREATE TABLE team_standings (
  id INTEGER PRIMARY KEY,
  season_id INTEGER NOT NULL,
  team_label TEXT,
  position INTEGER NOT NULL,
  team_name TEXT NOT NULL,
  total_score NUMERIC,
  is_imported BOOLEAN DEFAULT FALSE,
  UNIQUE(season_id, team_label, position),
  FOREIGN KEY (season_id) REFERENCES seasons(id)
);
```

### Import Workflow

```
├─ Read PDF files from data/original_website/files/results/YYYY-YYYY/
├─ For each PDF:
│  ├─ Parse filename to extract date and venue
│  ├─ Extract tables from PDF pages
│  ├─ For each row:
│  │  ├─ Validate data (position is numeric, etc.)
│  │  ├─ Log warning if invalid
│  │  └─ Skip row if critical field missing
│  ├─ Create season if missing
│  ├─ Create fixture if missing
│  ├─ Create race if missing
│  ├─ Check if result already exists
│  └─ Insert result (or skip if exists + not --force)
└─ Print summary + log file path
```

### Error Handling

- **Warnings don't halt import**: Missing fields, malformed values logged; import continues
- **Errors may halt import**: Database errors, file access issues — logged with stack trace
- **Dry-run mode**: All parsing done, no DB writes; useful for detecting issues before commit

---

## Troubleshooting

### Issue: "No PDF files found"

**Symptoms**:
```
ImportError: No PDF files found in data/original_website/files/results/
```

**Solutions**:
1. Verify `data/original_website/` directory exists (copied from archive)
2. Check PDFs are in expected structure: `data/original_website/files/results/YYYY-YYYY/`
3. Run from repository root (not from `scripts/` directory)
4. Check file permissions: PDFs must be readable

### Issue: "ModuleNotFoundError: No module named 'pdfplumber'"

**Solution**:
```bash
uv add pdfplumber
uv run python scripts/migrate_results.py
```

### Issue: "Database is locked" (Windows)

**Symptoms**:
```
Error: database is locked (or disk I/O error)
```

**Solutions**:
1. Ensure no other processes are using `data/app.duckdb`
2. Close Jupyter notebooks, database browsers, etc.
3. Wait 2-3 seconds; database lock is usually transient
4. Try again: `uv run python scripts/migrate_results.py`

### Issue: Partial import (import stopped mid-way)

**Solutions**:
1. Check import log for error: `grep '"level": "error"' data/import_*.jsonl`
2. Fix issue (e.g., download missing PDFs)
3. Re-run with `--force` to reset and re-import: `uv run python scripts/migrate_results.py --force`
4. Or `--dry-run` first to verify: `uv run python scripts/migrate_results.py --dry-run --force`

### Issue: "Column count mismatch" when inserting

**Symptoms**:
```
Prepare Error: Mismatch in the number of columns in the INSERT statement
```

**Solutions**:
1. Verify schema matches migrations in `migrations/` directory
2. Run migrations: `python scripts/_apply_migrations.py`
3. Check if schema was updated but import script wasn't

---

## Security Notes

### No SQL Injection

All database queries use **parameterized statements**:

```python
# ✅ SAFE: Parameter binding
con.execute("INSERT INTO results (race_id, athlete_name, time) VALUES (?, ?, ?)",
            [race_id, athlete_name, time])

# ❌ UNSAFE: String concatenation (not used in this project)
# con.execute(f"INSERT INTO results ... VALUES ({race_id}, '{athlete_name}', '{time}')")
```

### No Credential/Secret Exposure

- No API keys, passwords, or tokens in scripts
- Database path configurable via environment variable (see `src/website/database.py`)
- Import logs may contain athlete names (considered non-sensitive in context of public race results)

### File Access

- Scripts only read from `data/original_website/` (archive data)
- Scripts only write to `data/` directory (import logs, database)
- No access to system files outside repository

---

## Development & Testing

### Running Tests

```bash
# All import-related unit tests
uv run pytest tests/unit/test_migrate_results.py -v
uv run pytest tests/unit/test_migrate_standings.py -v
uv run pytest tests/unit/test_validation_phase6.py -v

# With coverage
uv run pytest tests/unit/ --cov=scripts --cov-report=html
```

### Test Database

Tests use in-memory DuckDB (`:memory:`) to avoid modifying production `data/app.duckdb`.

```python
# Fixture provides test DB connection
def test_result_import(test_db: duckdb.DuckDBPyConnection) -> None:
    # test_db is isolated, in-memory, and cleaned up after test
    pass
```

### Adding New Import Features

1. Add tests first (TDD approach)
2. Implement feature in script
3. Add type hints and docstrings
4. Run linting: `ruff format scripts/ && ruff check scripts/`
5. Run bandit for security scan: `bandit -r scripts/`
6. Run full test suite: `uv run pytest tests/unit/`
7. Commit with descriptive message

---

## References

- **Legacy Website Archive**: `data/original_website/` (read-only reference)
- **Schema Definitions**: `migrations/0007_create_races_and_results.sql` (results) and `migrations/0009_create_standings.sql` (standings)
- **Specification**: `specs/001-import-results-standings/` (full feature spec, data model, plan)
- **API Routes**: `src/website/main.py` (routes that expose imported data: `/results`, `/standings`)
