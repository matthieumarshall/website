# Research & Clarifications: Import Legacy Results and Standings

**Date**: 2026-05-09 | **Status**: Complete
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Clarifications Resolved (Session 2026-05-09)

### Q1: Update or Skip When Results Already Exist?

**Decision**: Update existing records (replace on re-run with `--force` flag)

**Rationale**:
- Allows admins to correct/refresh imported data without manual cleanup
- Provides clean recovery path if import fails partway through
- Supports incremental import (e.g., re-run with new data files added)

**Implementation**: Upsert logic via primary key (race_id, athlete_name, time) or delete+reinsert with `--force`

---

### Q2: How to Handle Missing/Malformed Data?

**Decision**: Import with NULL values where possible; log all issues; continue processing

**Rationale**:
- Preserves historical record even with incomplete data
- Provides transparency via import logs for data quality issues
- Does not halt import on individual record errors (maximizes data recovery)

**Implementation**:
- Result fields like `time`, `category`, `gender` are required; warn if missing but proceed with best effort
- Optional fields (`race_number`, `club`, `category_position`) can be NULL
- Log entry structure: `{"level": "warning", "file": "...", "row": 5, "issue": "missing_time", "athlete": "..."}`

---

### Q3: Auto-Create Seasons if Missing?

**Decision**: YES, extract season name from folder structure

**Rationale**:
- Eliminates manual pre-population step
- Season name deterministically derived from folder (e.g., "1988-1989")
- Idempotent: re-running import doesn't duplicate seasons

**Implementation**:
- Scan decade folders → season folders (e.g., `2020-2030/2021-2022`)
- Call `create_season_if_missing(con, "2021-2022")`
- Existing seasons are looked up by name (case-insensitive); new ones auto-created

---

### Q4: Auto-Create Fixtures if Missing?

**Decision**: YES, extract date and venue from result filename

**Rationale**:
- Filename format is stable and machine-readable: `YYYYMMDD-RndN-VenueName-min.pdf`
- Round number + date uniquely identify a fixture
- Venue name becomes fixture title

**Implementation**:
- Parse filename: `20210101-Rnd1-BicesterHeritage-min.pdf`
- Extract: date=2021-01-01, round=1, venue="Bicester Heritage"
- Call `create_fixture_if_missing(con, season_id, date, venue)`
- Deduplication: check (season_id, date) exists; skip if `--force` not set

---

### Q5: Discover Existing Browsing Routes/UI?

**Decision**: YES — `/results` and `/standings` routes already fully built

**Finding**:
- `/results` endpoint displays seasons → fixtures → races → results with filtering
- `/standings` endpoint displays individual and team standings by season
- UI components fully functional: filtering by category/club/gender/name, CSV/PDF export
- No new routes or templates needed; import data populates existing infrastructure

**Existing Infrastructure**:
- `src/website/main.py`: `/results`, `/results/fixture-panel`, `/results/race-panel`, `/results/race-table`
- `templates/results.html`: season selector, fixture list, race selector, results table
- `templates/_results_race_panel.html`: filters + export buttons
- `static/results-filter.js`: client-side filtering island
- `src/website/standings.py`: standings calculation logic (exists but not yet populated with historical data)

**Implication**: Import task is pure data population; UI wiring already complete.

---

## Key Technical Findings

### Existing Migration Scripts

**migrate_results.py**: Already handles PDF extraction
- Uses `pdfplumber` to open PDFs
- Extracts tables from pages
- Normalizes column headers
- Parses rows into Result objects
- Current: manually creates seasons + fixtures; new: auto-create

**migrate_standings.py**: Already handles standings PDFs
- Similar PDF extraction pattern
- Parses individual + team standings tables
- Current: requires season to pre-exist; new: auto-create

**_migration_helpers.py**: Provides shared utilities
- `open_db()`: DuckDB connection + auto-runs migrations
- `find_season_id()`: lookup by name (fails if not found)
- `find_fixture_by_date()`: lookup by date + season
- New helpers needed: `create_season_if_missing()`, `create_fixture_if_missing()`

### Database Schema (Already in Place)

**Seasons table** (`migrations/0003_create_seasons.sql`)
```sql
CREATE TABLE seasons (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE
);
```

**Fixtures table** (`migrations/0004_create_fixtures.sql`)
```sql
CREATE TABLE fixtures (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES seasons(id),
    date DATE NOT NULL,
    title VARCHAR NOT NULL,
    location VARCHAR
);
```

**Races table** (`migrations/0007_create_races_and_results.sql`)
```sql
CREATE TABLE races (
    id INTEGER PRIMARY KEY,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    name VARCHAR NOT NULL,
    display_order INTEGER DEFAULT 0
);
```

**Results table** (`migrations/0007_create_races_and_results.sql`)
```sql
CREATE TABLE results (
    id INTEGER PRIMARY KEY,
    race_id INTEGER NOT NULL REFERENCES races(id),
    position INTEGER NOT NULL,
    race_number INTEGER,
    athlete_name VARCHAR NOT NULL,
    time VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    category_position INTEGER,
    gender VARCHAR NOT NULL,
    gender_position INTEGER,
    club VARCHAR
);
```

**Standings tables** (`migrations/0009_create_standings.sql`)
- `individual_standings`: position, athlete_name, club, total_score, fixture_scores (JSON), is_imported flag
- `team_standings`: similar + team_name, team_label

→ All fields already support NULL values; schema ready for historical data import

### Data Format & Availability

**Results PDFs**: ALL decades available
- 1987-1990, 1990-2000, 2000-2010, 2010-2020, 2020-2030 directories
- Each contains season folders (e.g., 1988-1989, 2021-2022)
- Files follow naming: `YYYYMMDD-Rnd#-VenueName-min.pdf`
- Estimated: 40 seasons × 5-7 fixtures × 2-3 races = ~400-600 result PDFs total

**Standings PDFs**: Only recent seasons
- 2023-24: `OXL 23-24 Individual Standings R5.pdf`, `OXL 23-24 Team Standings R5.pdf`
- 2024-25: `2024-25 OXL Standings After R5.pdf`
- 2025-26: `2025-26_OXL_Standings_After_R5.pdf`
- Total: ~7 standings PDFs

**Scale**: ~400k result records + ~2k-3k standings records to import

### Constitution Compliance

✅ All existing patterns support the new implementation:
- Type hints already used throughout (`result: Result`, `db: duckdb.DuckDBPyConnection`)
- Dependency injection via `Depends(get_db)` established
- Pre-commit hooks (ruff, bandit) configured
- Test fixtures with `:memory:` DuckDB in place
- 85% coverage target applicable to new modules

---

## Design Decisions

### Decision 1: Auto-Creation via Helper Functions

**Alternative rejected**: Manual pre-population script
- New approach: Create seasons/fixtures on-demand during import
- Benefit: Single import run handles everything; no separate setup steps
- Risk mitigation: Helper functions are idempotent (check exists first)

### Decision 2: Logging via ImportLogger Class

**Alternative rejected**: Print statements + error returns
- New approach: Structured JSON logging to file + console summary
- Benefit: Machine-readable logs for debugging; admin-friendly summary
- Risk mitigation: Rotate logs by date to avoid disk bloat

### Decision 3: Dry-Run Mode in Both Scripts

**Alternative rejected**: Only in migrate_results.py
- New approach: Both `migrate_results.py` and `migrate_standings.py` support `--dry-run`
- Benefit: Admin can preview any import without risk
- Implementation: Parse all files, print summary, skip DB writes

### Decision 4: Reuse Existing `/results` & `/standings` UI

**Alternative rejected**: Build admin-only import UI
- New approach: Data import is admin CLI tool; browsing uses existing public pages
- Benefit: No new frontend code needed; seamless integration
- Implementation: After import, data automatically appears in `/results?season_id=X`

---

## Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-----------|
| PDF parsing fails on edge case | Medium | Lost data from that file | Detailed error logging; admin can retry with `--force` after fixing file |
| Duplicate results inserted | Low | Data corruption | Deduplication check (race_id, athlete_name, time) before insert |
| Import takes >5 min | Low | UX issue for admin | Optimize with batch inserts; PDF parsing is already fast (pdfplumber is efficient) |
| Missing season/fixture breaks cascade | Very Low | DB constraint error | Auto-create logic ensures deps exist before child records |
| Malformed data silent failures | Medium | Data loss | Structured logging of all issues; admin reviews logs post-import |

---

## Assumptions Validated

✅ Legacy data files are in PDF format — confirmed, all result PDFs exist
✅ PDF naming convention is stable — confirmed, `YYYYMMDD-RndN-VenueName-min.pdf` consistent
✅ Database schema ready — confirmed, all tables exist with NULL support
✅ Existing routes ready for data — confirmed, `/results` fully functional
✅ pdfplumber dependency available — confirmed, already in `uv.lock`
✅ Admin has CLI access — confirmed, `scripts/` pattern established

---

## Next Steps

1. ✅ **Clarification Phase**: All questions resolved (this document)
2. → **Design Phase**: [plan.md](plan.md) details technical approach + architecture
3. → **Task Generation**: `/speckit.tasks` creates actionable task list
4. → **Implementation**: Build modules, write tests, integrate with UI
5. → **Verification**: Run UI tests to confirm browsing works; review import logs
