## Implementation Guide: Import Legacy Results and Standings - Phases 4-7

> **Status**: MVP (Phases 1-3) complete and committed. 290 tests passing, 78% code coverage.

### Current State

✅ **Operational** (Ready for production):
- Historical results import from legacy PDFs
- Season and fixture auto-creation
- Deduplication with `--force` override
- Dry-run preview mode
- Structured JSON logging
- API endpoints for results browsing
- Full test coverage (27 tests)

📁 **Files Implemented**:
- `scripts/_import_logger.py` — Structured logging (165 lines)
- `scripts/_migration_helpers.py` — Auto-creation + dedup helpers (150+ lines added)
- `scripts/migrate_results.py` — Enhanced CLI (420 lines)
- `tests/unit/test_migration_helpers.py` — 11 passing tests
- `tests/unit/test_migrate_results.py` — 12 passing tests
- `tests/unit/test_historical_results_browsing.py` — 4 passing tests

---

## Phase 4: User Story 2 - Import Historical Standings Data

**Effort**: 4-5 hours | **Pattern**: Mirror Phase 3 but for standings

### Architecture

```python
# scripts/migrate_standings.py — Similar structure to migrate_results.py
├── PDF parsing (pdfplumber)
│   ├── Extract individual standings tables
│   ├── Extract team standings (A/B/C labels)
│   └── Parse category headings from PDF text
├── Season auto-creation
├── Standings insertion
│   ├── Deduplication by (season_id, category, position)
│   └── Set is_imported=true flag
└── Logging (ImportLogger)
```

### Database Schema Notes

The `individual_standings` and `team_standings` tables already have:
- `is_imported` flag (NULL/true) — Set to TRUE on import
- All required fields for historical data
- No schema changes needed

### Implementation Steps (T040-T062)

1. **Tests First** (T040-T047):
   ```bash
   # Create tests/unit/test_migrate_standings.py
   # Mirror test structure from test_migrate_results.py but for standings
   ```

2. **CLI Script Enhancement** (T051-T062):
   - Copy `scripts/migrate_results.py` → `scripts/migrate_standings.py`
   - Replace PDF table detection logic for standings-specific format
   - Extract team_label (A/B/C) from team names (regex or parsing)
   - Add `is_imported=true` to all inserts
   - Add `--force` and `--dry-run` flags
   - Integrate ImportLogger

3. **UI Tests** (T048-T050):
   - Add to `tests/unit/test_historical_results_browsing.py`
   - Verify `/standings` page loads with historical seasons
   - Verify team standings visible when available

### Code Template

```python
# scripts/migrate_standings.py

def _extract_team_label(team_name: str) -> str | None:
    """Extract team label (A/B/C) from team name like 'Team A' or 'A'."""
    import re
    match = re.search(r'\b([A-C])\b', team_name, re.IGNORECASE)
    return match.group(1).upper() if match else None

def _parse_standings_pdf(pdf_path: Path) -> list[dict]:
    """Extract standings from PDF.

    Returns: List of category standings::
        {
            "category": str,  # e.g. "M" (Men)
            "standings": [
                {
                    "position": int,
                    "athlete_name": str,
                    "total_score": float,
                    "team_label": str | None,  # "A", "B", "C" for team standings
                    ...
                }
            ]
        }
    """
    # Similar to _parse_results_pdf but looks for standings table structure
    pass

def _insert_standings(con, season_id: int, standings: list[dict], *, force: bool = False, logger = None):
    """Insert standings with is_imported=true flag."""
    for category_standings in standings:
        for standing in category_standings["standings"]:
            # Insert to individual_standings or team_standings based on team_label
            # Set is_imported=true
            # Check standing_exists() for dedup if not --force
            pass
```

---

## Phase 5: User Story 3 - Browse Historical Seasons

**Effort**: 1-2 hours | **Pattern**: Verification only

### Verification Checklist (T063-T076)

All of these should **already work** — no code changes expected:

- [ ] `/results` page loads with historical seasons dropdown
- [ ] Can filter by season_id parameter
- [ ] Results filtering (category/club/gender/name) works
- [ ] CSV/PDF export includes historical results
- [ ] `/standings` page displays historical seasons
- [ ] Standing filtering works

### Test Script

```bash
# Run these to verify existing endpoints work:
uv run pytest tests/unit/test_historical_results_browsing.py -v

# Manual verification:
# 1. Start server: uv run uvicorn website.main:app --reload
# 2. Visit http://localhost:8000/results
# 3. Visit http://localhost:8000/standings
# 4. Check that historical seasons appear in dropdowns
```

---

## Phase 6: User Story 4 - Validation & Logging

**Effort**: 3-4 hours | **Pattern**: Enhance helpers + logging

### Features to Add (T077-T091)

1. **Validation Helpers** (add to `scripts/_migration_helpers.py`):
   ```python
   def is_valid_position(value: int | str) -> bool:
       """Position must be positive integer."""

   def is_valid_athlete_name(value: str) -> bool:
       """Athlete name must be non-empty, reasonable length."""

   def is_valid_time(value: str) -> bool:
       """Time must be time-like format (HH:MM:SS or variations)."""
   ```

2. **Enhanced Logging** (update `scripts/_import_logger.py`):
   - Add warning categories: `malformed_position`, `missing_athlete`, `missing_time`
   - Track counts per warning type
   - Include in summary report
   - Export to CSV for analysis

3. **Test Data with Issues**:
   ```python
   # tests/unit/test_migrate_results.py
   def test_warnings_for_malformed_data():
       """Import with known quality issues; verify warnings logged."""
       logger = ImportLogger()

       # Parse results with:
       # - Missing athlete_name (should warn)
       # - Non-numeric position (should skip)
       # - Missing time value (should warn)

       assert logger.records["warning"]["malformed_position"] > 0
   ```

---

## Phase 7: Polish & Cross-Cutting Concerns

**Effort**: 2-3 hours

### Documentation (T092-T095)

Create `scripts/README-IMPORT.md`:

```markdown
# Legacy Data Import Guide

## Quick Start

```bash
# Preview what will be imported (no database changes)
uv run python scripts/migrate_results.py --dry-run --season 2021-2022

# Import a specific season
uv run python scripts/migrate_results.py --season 2021-2022

# Force re-import (replace existing)
uv run python scripts/migrate_results.py --season 2021-2022 --force

# Import standings
uv run python scripts/migrate_standings.py --dry-run
uv run python scripts/migrate_standings.py
```

## Log Output

Import scripts generate JSON-lines logs at `logs/import-TIMESTAMP.jsonl`:

```json
{"level": "info", "stage": "season_created", "season": "2021-2022", "season_id": 1}
{"level": "warning", "stage": "result_parse", "reason": "malformed_position", "value": "DNF"}
{"level": "info", "stage": "result_insert", "athlete": "John Doe", "time": "23:45"}
```

Summary printed to stdout includes:
- Seasons created
- Fixtures auto-created
- Results inserted
- Deduplicates skipped
- Warnings/errors encountered
- Duration
- Log file location
```

### Code Quality (T096-T100)

```bash
# Format all scripts
uv run ruff format scripts/ tests/

# Lint
uv run ruff check scripts/ --fix

# Security scan
uv run bandit -r scripts/

# Type check (optional, helps catch bugs)
uv run py   # already passing
```

### Testing & CI (T101-T104)

```bash
# Coverage check
uv run pytest tests/unit/ --cov=scripts --cov=src/website --cov-report=html

# Run all tests
uv run pytest tests/unit/ -v

# Pre-commit (should pass)
pre-commit run --all-files
```

---

## Quick Reference: Common Tasks

### Add a new helper function to `_migration_helpers.py`:

```python
def new_helper(con: duckdb.DuckDBPyConnection, param: str) -> int:
    """Short description.

    Args:
        con: DuckDB connection.
        param: Parameter description.

    Returns:
        Integer ID or count.
    """
    result = con.execute(
        "SELECT id FROM table WHERE name = ?", [param]
    ).fetchone()
    return int(result[0]) if result else None
```

1. Add type hints and docstring
2. Add unit test in `tests/unit/test_migration_helpers.py`
3. Run: `uv run pytest tests/unit/test_migration_helpers.py -v`
4. Ensure test passes before using in production code

### Run tests for a specific module:

```bash
# Results import
uv run pytest tests/unit/test_migrate_results.py -v

# Migration helpers
uv run pytest tests/unit/test_migration_helpers.py -v

# All tests
uv run pytest tests/unit/ -q
```

### Check test coverage:

```bash
uv run pytest tests/unit/ --cov=scripts --cov-report=html
# Opens htmlcov/index.html in browser
```

---

## Deployment Checklist

Before merging to `main`:

- [ ] All 290+ tests passing locally
- [ ] Pre-commit hooks pass: `pre-commit run --all-files`
- [ ] Code coverage ≥ 80%
- [ ] Manual dry-run test: `scripts/migrate_results.py --dry-run --season 2021-2022`
- [ ] Verify log file generated with expected format
- [ ] Documentation updated (README-IMPORT.md)
- [ ] PR description includes import summary

---

## Success Metrics

✅ **MVP Complete** (Phases 1-3):
- 290 tests passing
- 78% code coverage
- Historical results importable
- Browseable via existing UI
- Structured logging

✅ **Phases 4-5** (Recommended next):
- Standings import working
- Historical seasons visible in both results and standings

✅ **Phases 6-7** (Polish):
- Enhanced validation reporting
- Full documentation
- CI/CD integration

---

## Troubleshooting

**Q: Tests fail with "fixture not found"**
A: Make sure you're running from the repo root: `cd /path/to/website && uv run pytest`

**Q: ImportLogger not found**
A: Ensure `sys.path.insert(0, str(_SCRIPTS_DIR))` is called before imports in migrate_results.py

**Q: Pre-commit hooks fail**
A: Run `pre-commit run --all-files` and fix issues, then commit again

**Q: Type checking errors (mypy)**
A: Add type hints or suppress with `# type: ignore` comment with explanation

---

**Ready to implement Phases 4-7?** Follow the patterns above — they reuse the same structure, helpers, and testing approach. Ask if you need clarification on any section!
