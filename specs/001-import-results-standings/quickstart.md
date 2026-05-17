# Quickstart: Import & Browse Historical Results

**Date**: 2026-05-09 | **Data Model**: [data-model.md](data-model.md)

## For Admins: Running the Import

### Prerequisites

- Python 3.11+ environment activated (`.venv` virtual environment)
- `uv` package manager installed
- Access to `data/original_website/files/results/` directory (must be in repo root)

### Basic Import (Results + Standings)

```bash
# Step 1: Dry-run first to preview what will be imported (no database changes)
uv run python scripts/migrate_results.py --dry-run
uv run python scripts/migrate_standings.py --dry-run

# Step 2: Run the actual import
uv run python scripts/migrate_results.py
uv run python scripts/migrate_standings.py

# Step 3: Verify import success
uv run python scripts/verify_import.py  # (optional: check counts match expectations)
```

**Expected behavior**:
- Each script parses PDFs and inserts into DuckDB
- Progress logged to stdout with JSON-formatted log file
- Log file created in `data/` directory with timestamp: `import_YYYYMMDD_HHMMSS.jsonl`
- Example log file: `data/import_20260509_143500.jsonl`
- Final summary printed to console:

```
════════════════════════════════════════════════════════════
Import Summary — 2026-05-09 14:35:00
════════════════════════════════════════════════════════════
Stages completed: 2 (import_start, import_complete)
By level:
  info:     98
  warning:  23
  error:     0
─────────────────────────────────────────────────────────
Duration: 3m 45s
Log file: data/import_20260509_143500.jsonl
════════════════════════════════════════════════════════════
```

### Import Options

#### Option 1: Dry-Run Mode (`--dry-run`)

Preview the import without making any database changes:

```bash
# Results import dry-run
uv run python scripts/migrate_results.py --dry-run

# Standings import dry-run
uv run python scripts/migrate_standings.py --dry-run
```

**What it does**:
- Parses all PDF files
- Logs each record and validation issue
- Skips all database writes (INSERT/DELETE)
- Useful for checking for PDF parsing errors before committing to import

**Example output**:
```
Parsing: data/original_website/files/results/1988-1989/19880115-Rnd1-Venue-min.pdf
  Found race: "Men"
  Found 42 results in table
  Inserted race into database: race_id=1 (DRY-RUN: skipped DB write)
```

#### Option 2: Force Mode (`--force`)

Delete all existing results/standings for a season and re-import fresh:

```bash
# Force replace all existing results
uv run python scripts/migrate_results.py --force

# Force replace all existing standings
uv run python scripts/migrate_standings.py --force
```

**What it does**:
- Deletes ALL existing results/standings for affected seasons
- Re-imports everything fresh from PDFs
- Useful if import partially failed or data was corrupted

**⚠️ WARNING**: `--force` is destructive. Ensure you have backups or plan to re-import.

#### Option 3: Season Filter (`--season YYYY-YYYY`)

Import only results from a specific season:

```bash
# Import only 2021-2022 season
uv run python scripts/migrate_results.py --season 2021-2022

# Import only 2024-2025 standings
uv run python scripts/migrate_standings.py --season 2024-2025
```

**What it does**:
- Only processes PDFs in `data/original_website/files/results/YYYY-YYYY/` folder
- Skips all other seasons
- Useful for incremental imports or testing

#### Option 4: Combine Options

You can combine flags:

```bash
# Force re-import 2021-2022 season (dry-run first!)
uv run python scripts/migrate_results.py --dry-run --force --season 2021-2022
uv run python scripts/migrate_results.py --force --season 2021-2022

# Dry-run standing for specific season
uv run python scripts/migrate_standings.py --dry-run --season 2024-2025
```

### Interpreting the Import Log

The import script creates a **JSON-lines log file** (one JSON object per line) with detailed records.

**Log file location**: `data/import_YYYYMMDD_HHMMSS.jsonl` (example: `data/import_20260509_143500.jsonl`)

#### Reading the Log

View the full log:
```bash
cat data/import_20260509_143500.jsonl | python -m json.tool
```

Find warnings only:
```bash
grep '"level": "warning"' data/import_20260509_143500.jsonl
```

Count issues by type:
```bash
# Count warnings by stage
grep '"level": "warning"' data/import_20260509_143500.jsonl | \
  grep -o '"stage": "[^"]*"' | sort | uniq -c
```

#### Log Entry Structure

Each line is JSON with fields:

```json
{
  "timestamp": "2026-05-09T14:35:00.123456",
  "level": "info|warning|error",
  "stage": "import_start|pdf_parse|result_insert|standings_validation|import_complete",
  "message": "Human-readable message",
  "pdf_file": "path/to/file.pdf (optional)",
  "athlete_name": "Name (optional)",
  "race_id": 123 (optional),
  "position": 1 (optional),
  "...": "...other context fields"
}
```

**Example log entries**:

```json
{"timestamp": "2026-05-09T14:35:00.123456", "level": "info", "stage": "import_start", "message": "Starting results import", "directory": "data/original_website/files/results"}
{"timestamp": "2026-05-09T14:35:01.123456", "level": "warning", "stage": "result_missing_field", "message": "Missing athlete_name", "pdf_file": "1988-1989/19880115-min.pdf", "race_id": 1, "position": 5}
{"timestamp": "2026-05-09T14:35:02.123456", "level": "error", "stage": "pdf_parse_error", "message": "Could not extract table", "pdf_file": "1999-2000/invalid.pdf", "error": "No tables found"}
{"timestamp": "2026-05-09T14:37:45.123456", "level": "info", "stage": "import_complete", "message": "Import finished", "total_records": 12450, "warnings": 23, "errors": 1, "duration_seconds": 165}
```

#### Common Warnings

| Warning Type | Meaning | Action |
|---|---|---|
| `result_missing_field` | Missing athlete name, time, or position | Check PDF for OCR errors; recheck manually if needed |
| `result_malformed_position` | Position is non-numeric (e.g., "DNF", "DNS") | These rows are skipped; usually acceptable |
| `result_duplicate_skipped` | Result already in database | Re-run with `--force` if re-import needed |
| `standings_missing_field` | Position or score missing from standings table | Check source PDF; import continues |
| `pdf_parse_error` | Couldn't extract table from PDF | Review PDF in viewer; may be corrupt or mis-formatted |

#### Common Errors

| Error Type | Meaning | Action |
|---|---|---|
| `pdf_open_failed` | PDF file couldn't be opened | Check file exists and isn't corrupted |
| `database_insert_failed` | DuckDB rejected the insert | Check schema matches; review constraints |
| `season_creation_failed` | Couldn't create season record | Check if season name is valid; check DB permissions |

### Validation

After import completes successfully:

```bash
# Check database has data
uv run python -c "
import duckdb
con = duckdb.connect('data/app.duckdb')

# Count records
print('Seasons:', con.execute('SELECT COUNT(*) FROM seasons').fetchone()[0])
print('Fixtures:', con.execute('SELECT COUNT(*) FROM fixtures').fetchone()[0])
print('Races:', con.execute('SELECT COUNT(*) FROM races').fetchone()[0])
print('Results:', con.execute('SELECT COUNT(*) FROM results').fetchone()[0])
print('Standings (individual):', con.execute('SELECT COUNT(*) FROM individual_standings').fetchone()[0])
print('Standings (team):', con.execute('SELECT COUNT(*) FROM team_standings').fetchone()[0])
"
```

---

## For Users: Browsing Historical Data

### Accessing Results

1. **Navigate to Results page**: `/results`
2. **Select a historical season**: Choose from dropdown (e.g., "1988-1989")
3. **Browse fixtures**: List of all races for that season appears
4. **Select a fixture**: Click to expand and see all races for that date
5. **Select a race**: View results table with filtering options

### Filtering Results

Once a race is displayed, you can filter by:
- **Category**: e.g., "Senior Men", "U13 Boys" (dropdown, auto-populated)
- **Club**: e.g., "Oxford AC", "Harriers" (dropdown)
- **Gender**: M, F, etc. (dropdown)
- **Name**: Free-text search for athlete name

Filters are **persistent** in the URL, so you can share filtered results:
```
/results?season_id=1&fixture_id=10&race_id=42&category=SM40&club=Harriers
```

### Exporting Results

For any race, export results to:
- **CSV**: Click "↓ CSV" button — includes all columns (with current filters applied)
- **PDF**: Click "↓ PDF" button — formatted table for printing/sharing

Both respect the current filter selections (category, club, gender, name).

### Viewing Standings

1. **Navigate to Standings page**: `/standings`
2. **Select a historical season**: Choose from dropdown (seasons with standings data available)
3. **Browse standings**:
   - **Individual standings**: Ranked athletes by total score
   - **Team standings**: Ranked teams (A, B, C divisions) by total score
   - All standings shown in reverse chronological order of season

Standings are **read-only** (historical snapshots, not recalculated).

---

## Technical Notes for Admins

### Data Preservation

- All imported values are **exactly as they appear in legacy PDFs**
  - Times, positions, scores are NOT recomputed
  - Missing data is imported as NULL (not transformed)
- Historical standings are marked `is_imported = true` to prevent recalculation pipeline from overwriting them

### Duplicate Handling

**Without `--force`**:
- If a result already exists (same race, athlete name, time), it's skipped
- Useful for incremental imports (add new files, re-run, only new results added)

**With `--force`**:
- All existing results are deleted before re-import
- Ensures clean slate; useful if import was corrupted or partially failed

### Seasons & Fixtures Auto-Creation

- **Seasons**: Automatically created from folder names (e.g., `2021-2022` → season id auto-assigned)
- **Fixtures**: Automatically created from PDF filename date + venue (e.g., `20210101-Rnd1-Bicester-min.pdf` → fixture for 2021-01-01)
- Both are idempotent: re-running import doesn't duplicate seasons or fixtures

### Performance

Typical import times:
- **Results only**: ~3–5 minutes for all seasons (40+ years, ~400k records)
- **Standings only**: ~30 seconds (recent seasons, ~2k records)
- **Both**: ~5–6 minutes total

Import is I/O-bound (PDF parsing); parallelization is possible but not implemented in v1.

---

## Troubleshooting

### Problem: Import Takes Too Long

**Symptoms**: Still running after 10 minutes

**Causes**:
1. Slow disk I/O on old/network drive
2. Large legacy PDF files taking time to extract

**Solutions**:
- Verify disk performance: `time ls -la data/original_website/files/results/` should complete in <1 sec
- Try importing one season at a time: `--season 2021-2022`
- Check system load: `top` or `wsl -e top`

### Problem: Missing Data in Results

**Symptoms**: Some rows have NULL values for time, athlete_name, etc.

**Expected**: This is normal for legacy data. Check the import log:
```bash
grep '"level": "warning"' data/import_YYYYMMDD_HHMMSS.log
```

**Workaround**:
1. Review the specific PDF file mentioned in the warning
2. Manually correct the PDF if possible
3. Re-run import with `--force` to reload corrected data

### Problem: Import Fails with DB Error

**Symptoms**: Error like "constraint violation" or "database locked"

**Causes**:
1. Database is locked (another process accessing it)
2. Data doesn't match schema (should never happen if code is correct)

**Solutions**:
1. Stop any other running FastAPI server: `pkill -f uvicorn`
2. Wait 5 seconds for DB lock to release
3. Retry import: `uv run python scripts/migrate_results.py`

### Problem: UI Doesn't Show Imported Data

**Symptoms**: `/results` page is empty or old seasons missing

**Checks**:
1. Verify import succeeded: `tail data/import_YYYYMMDD_HHMMSS.log` (should show summary)
2. Verify database has data: `uv run python -c "import duckdb; print(duckdb.connect('data/app.duckdb').execute('SELECT COUNT(*) FROM results').fetchone())"`
3. Restart FastAPI server: `uv run uvicorn src.website.main:app --reload`

If data exists in DB but not showing in UI, restart the FastAPI server (it may have cached empty results).

---

## Advanced: Manual SQL Queries

### View All Imported Seasons

```sql
SELECT id, name FROM seasons ORDER BY name DESC;
```

### View All Fixtures in a Season

```sql
SELECT f.id, f.date, f.title
FROM fixtures f
WHERE f.season_id = ?
ORDER BY f.date ASC;
```

### Count Results by Season

```sql
SELECT s.name, COUNT(*) as result_count
FROM results r
JOIN races rc ON r.race_id = rc.id
JOIN fixtures f ON rc.fixture_id = f.id
JOIN seasons s ON f.season_id = s.id
GROUP BY s.name
ORDER BY s.name DESC;
```

### Find Results with Missing Data

```sql
SELECT rc.name, COUNT(*)
FROM results r
JOIN races rc ON r.race_id = rc.id
WHERE r.time IS NULL OR r.time = ''
GROUP BY rc.name;
```

### View Import Logs (Structured)

```bash
# Count warnings by type
python -c "
import json
with open('data/import_20260509_143500.log') as f:
    warnings = [json.loads(line) for line in f if 'warning' in line]
    from collections import Counter
    issues = Counter(w.get('issue', 'unknown') for w in warnings)
    for issue, count in issues.most_common():
        print(f'{issue}: {count}')
"
```

---

## Support

For issues or questions:
1. Check the import log: `data/import_YYYYMMDD_HHMMSS.log`
2. Review this guide's "Troubleshooting" section
3. Contact the development team with:
   - Import log file (sanitized if needed)
   - Steps to reproduce the issue
   - Expected vs. actual behavior
