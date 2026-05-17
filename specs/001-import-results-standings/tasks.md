# Tasks: Import Legacy Results and Standings

**Input**: Design documents from `/specs/001-import-results-standings/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓
**Feature Branch**: `fix_standings`

## Overview

This feature imports ~40 years of historical results and standings from legacy PDFs into DuckDB, making them browseable through existing UI without any transformation or recomputation. Tasks are organized by user story to enable independent implementation and testing.

**MVP Scope (Recommended)**: Complete **Phase 3** (US1 - Results Import) first. This alone delivers 80% of value and allows users to browse results. Phase 4 and beyond add standings and browsing enhancements.

---

## Phase 1: Setup - Import Infrastructure

**Purpose**: Establish logging and testing foundations

- [X] T001 Create ImportLogger class in `scripts/_import_logger.py` with info/warning/error methods, JSON output, and summary reporting
- [X] T002 [P] Create conftest.py fixtures in `tests/unit/` for DuckDB test database (`:memory:`), sample seasons, fixtures, races
- [X] T003 [P] Create pytest markers in `tests/unit/conftest.py` for unit vs. integration tests
- [X] T004 Create sample test data generator in `tests/unit/test_data.py` (helper functions for creating test seasons/fixtures/races)

**Checkpoint**: Logging infrastructure ready; test harness operational ✅

---

## Phase 2: Foundational - Migration Helpers & Existing Code Review

**Purpose**: Extend existing helpers; prepare for user story implementation

- [X] T005 Review and document existing `scripts/migrate_results.py` PDF parsing logic (20 min analysis, update code comments)
- [X] T006 Review and document existing `scripts/_migration_helpers.py` utilities; identify reusable patterns
- [X] T007 Add `create_season_if_missing(con, season_name: str) -> int` to `scripts/_migration_helpers.py` with idempotency + logging
- [X] T008 Add `create_fixture_if_missing(con, season_id: int, fixture_date: date, venue_name: str) -> int` to `scripts/_migration_helpers.py` with deduplication check
- [X] T009 [P] Add `fixture_exists(con, season_id: int, fixture_date: date) -> bool` helper to `scripts/_migration_helpers.py`
- [X] T010 [P] Add `result_exists(con, race_id: int, athlete_name: str, time: str) -> bool` helper to `scripts/_migration_helpers.py`
- [X] T011 Add type hints and docstrings to all new helpers in `scripts/_migration_helpers.py` (constitution: 100% coverage for new code)
- [X] T012 Write unit tests for migration helpers in `tests/unit/test_migration_helpers.py` (100% coverage: idempotency, deduplication, error cases)

**Checkpoint**: Migration helpers complete; all tests passing; foundation ready for user story work ✅

---

## Phase 3: User Story 1 - Import Historical Results Data (P1) 🎯

**Goal**: Admin can import all historical results from legacy PDFs into the database without transformation; data is preserved exactly; import logs capture all issues.

**Independent Test**: After import, verify all results appear in database; run `/results` page and browse historical seasons.

### Tests for User Story 1

- [X] T013 [P] [US1] Unit test: PDF parsing with valid result table in `tests/unit/test_migrate_results.py`
- [X] T014 [P] [US1] Unit test: PDF parsing with missing column headers (should warn + skip) in `tests/unit/test_migrate_results.py`
- [X] T015 [P] [US1] Unit test: PDF parsing with malformed position values (should log + skip row) in `tests/unit/test_migrate_results.py`
- [X] T016 [P] [US1] Unit test: Result insertion with NULL values for missing fields in `tests/unit/test_migrate_results.py`
- [X] T017 [P] [US1] Unit test: Season auto-creation during results import in `tests/unit/test_migrate_results.py`
- [X] T018 [P] [US1] Unit test: Fixture auto-creation from filename (date + venue) in `tests/unit/test_migrate_results.py`
- [X] T019 [P] [US1] Unit test: Deduplication check (skip existing result unless `--force`) in `tests/unit/test_migrate_results.py`
- [X] T020 [P] [US1] Unit test: `--force` flag replaces existing results in `tests/unit/test_migrate_results.py`
- [X] T021 [P] [US1] Unit test: `--dry-run` mode parses without DB writes in `tests/unit/test_migrate_results.py`
- [X] T022 [P] [US1] Unit test: Import log creation (JSON format, summary report) in `tests/unit/test_migrate_results.py`
- [X] T023 [US1] Integration test: Full import workflow (parse directory, create seasons/fixtures, insert results, verify counts) in `tests/unit/test_migrate_results.py`
- [X] T024 [US1] UI test: After import, `/results` page displays historical season in season dropdown in `tests/ui/test_historical_results_browsing.py`
- [X] T025 [US1] UI test: `/results?season_id=X` displays fixtures for historical season in `tests/ui/test_historical_results_browsing.py`
- [X] T026 [US1] UI test: Historical results are filterable by category/club/gender/name in `tests/ui/test_historical_results_browsing.py`

### Implementation for User Story 1

- [X] T027 [P] [US1] Enhance `scripts/migrate_results.py`: Add `--force` flag argument parsing
- [X] T028 [P] [US1] Enhance `scripts/migrate_results.py`: Add `--dry-run` flag argument parsing
- [X] T029 [P] [US1] Enhance `scripts/migrate_results.py`: Add `--season` filter argument parsing
- [X] T030 [US1] Enhance `scripts/migrate_results.py`: Integrate ImportLogger for structured logging (replace print statements)
- [X] T031 [US1] Enhance `scripts/migrate_results.py`: Call `create_season_if_missing()` for each season folder encountered
- [X] T032 [US1] Enhance `scripts/migrate_results.py`: Call `create_fixture_if_missing()` for each PDF filename (parse date + venue)
- [X] T033 [US1] Enhance `scripts/migrate_results.py`: Check `result_exists()` before insert; skip if exists + not `--force`
- [X] T034 [US1] Enhance `scripts/migrate_results.py`: On `--force`, delete existing results for this race before re-inserting
- [X] T035 [US1] Enhance `scripts/migrate_results.py`: Handle missing/malformed result fields (NULL values, log warnings)
- [X] T036 [US1] Enhance `scripts/migrate_results.py`: Implement `--dry-run` mode (parse PDFs, log, skip DB writes)
- [X] T037 [US1] Enhance `scripts/migrate_results.py`: Add type hints to all functions in migrate_results.py (constitution requirement)
- [X] T038 [US1] Enhance `scripts/migrate_results.py`: Add docstrings to public functions in migrate_results.py
- [X] T039 [P] [US1] Update usage docstring in `scripts/migrate_results.py` with new CLI options

**Checkpoint**: User Story 1 fully functional; admin can run import; all tests passing

---

## Phase 4: User Story 2 - Import Historical Standings Data (P1)

**Goal**: Admin can import historical end-of-season standings from legacy PDFs without transformation; standings marked `is_imported=true` to prevent recalculation.

**Independent Test**: After import, verify standings visible in `/standings` page for historical seasons.

### Tests for User Story 2

- [X] T040 [P] [US2] Unit test: PDF parsing with individual standings table in `tests/unit/test_migrate_standings.py`
- [X] T041 [P] [US2] Unit test: PDF parsing with team standings table (extract team_label A/B/C) in `tests/unit/test_migrate_standings.py`
- [X] T042 [P] [US2] Unit test: Standings insertion with NULL optional fields in `tests/unit/test_migrate_standings.py`
- [X] T043 [P] [US2] Unit test: Category heading parsing from PDF text (infer from section title) in `tests/unit/test_migrate_standings.py`
- [X] T044 [P] [US2] Unit test: `--force` flag deletes + re-imports all standings for season in `tests/unit/test_migrate_standings.py`
- [X] T045 [P] [US2] Unit test: `--dry-run` mode parses standings without DB writes in `tests/unit/test_migrate_standings.py`
- [X] T046 [P] [US2] Unit test: is_imported flag correctly set to true on import in `tests/unit/test_migrate_standings.py`
- [X] T047 [US2] Integration test: Full standings import workflow (parse directory, auto-create season, insert standings) in `tests/unit/test_migrate_standings.py`
- [X] T048 [US2] UI test: After import, `/standings` page displays historical season in season dropdown in `tests/ui/test_historical_results_browsing.py`
- [X] T049 [US2] UI test: `/standings?season_id=X` displays individual standings for historical season in `tests/ui/test_historical_results_browsing.py`
- [X] T050 [US2] UI test: Team standings visible when available (2024-25, 2025-26 seasons) in `tests/ui/test_historical_results_browsing.py`

### Implementation for User Story 2

- [X] T051 [P] [US2] Enhance `scripts/migrate_standings.py`: Add `--force` flag argument parsing
- [X] T052 [P] [US2] Enhance `scripts/migrate_standings.py`: Add `--dry-run` flag argument parsing
- [X] T053 [US2] Enhance `scripts/migrate_standings.py`: Integrate ImportLogger for structured logging
- [X] T054 [US2] Enhance `scripts/migrate_standings.py`: Auto-create season if missing (call `create_season_if_missing()`)
- [X] T055 [US2] Enhance `scripts/migrate_standings.py`: On `--force`, delete all standings for (season_id, category) before re-importing
- [X] T056 [US2] Enhance `scripts/migrate_standings.py`: Parse team standings and extract team_label (A/B/C) from team name in `scripts/migrate_standings.py`
- [X] T057 [US2] Enhance `scripts/migrate_standings.py`: Set `is_imported=true` flag on all inserted standings rows
- [X] T058 [US2] Enhance `scripts/migrate_standings.py`: Handle missing/malformed fields (NULL values, log warnings)
- [X] T059 [US2] Enhance `scripts/migrate_standings.py`: Implement `--dry-run` mode (parse PDFs, log, skip DB writes)
- [X] T060 [US2] Enhance `scripts/migrate_standings.py`: Add type hints to all functions
- [X] T061 [US2] Enhance `scripts/migrate_standings.py`: Add docstrings to public functions
- [X] T062 [P] [US2] Update usage docstring in `scripts/migrate_standings.py` with new CLI options

**Checkpoint**: User Story 2 fully functional; standings import working; all tests passing

---

## Phase 5: User Story 3 - Browse Historical Seasons and Results (P2)

**Goal**: Site visitors can browse and view results/standings for all historical seasons through existing UI.

**Independent Test**: Without any new UI code, existing `/results` and `/standings` pages display and filter historical data correctly.

### Tests for User Story 3

- [X] T063 [US3] UI test: `/results` page loads with historical seasons in dropdown (no errors) in `tests/ui/test_historical_results_browsing.py`
- [X] T064 [US3] UI test: Selecting historical season from dropdown loads fixtures via HTMX in `tests/ui/test_historical_results_browsing.py`
- [X] T065 [US3] UI test: Clicking fixture loads races for that fixture in `tests/ui/test_historical_results_browsing.py`
- [X] T066 [US3] UI test: Selecting race displays historical results table with all columns in `tests/ui/test_historical_results_browsing.py`
- [X] T067 [US3] UI test: Results filtering (category/club/gender/name) works on historical data in `tests/ui/test_historical_results_browsing.py`
- [X] T068 [US3] UI test: CSV export includes all filtered historical results in `tests/ui/test_historical_results_browsing.py`
- [X] T069 [US3] UI test: PDF export generates valid PDF with historical results in `tests/ui/test_historical_results_browsing.py`
- [X] T070 [US3] UI test: Seasons displayed in reverse chronological order (newest first) in `tests/ui/test_historical_results_browsing.py`
- [X] T071 [US3] UI test: `/standings` page loads with historical seasons in dropdown in `tests/ui/test_historical_results_browsing.py` — see T048/T049
- [X] T072 [US3] UI test: Selecting historical season on standings page displays standings table in `tests/ui/test_historical_results_browsing.py` — see T049

### Implementation for User Story 3

- [X] T073 Verify existing `/results` route (`src/website/main.py`) correctly queries historical data (no code changes expected)
- [X] T074 Verify existing `/standings` route (`src/website/main.py`) correctly queries historical data (no code changes expected)
- [X] T075 [P] Verify Jinja2 templates (`templates/results.html`, `templates/standings.html`) render historical seasons correctly (no changes expected)
- [X] T076 Verify results filtering JavaScript (`static/results-filter.js`) works with historical data (no changes expected)

**Checkpoint**: Users can browse all historical data through existing UI; no new code required

---

## Phase 6: User Story 4 - Validate Import Data Integrity (P2)

**Goal**: Admin receives clear validation reports during/after import; issues are logged with actionable details.

**Independent Test**: Run import on sample data with known quality issues; verify warnings are captured and reported correctly.

### Tests for User Story 4

- [X] T077 [P] [US4] Unit test: Warning logged for missing athlete_name in `tests/unit/test_validation_phase6.py`
- [X] T078 [P] [US4] Unit test: Warning logged for missing time value in `tests/unit/test_validation_phase6.py`
- [X] T079 [P] [US4] Unit test: Warning logged for non-numeric position in `tests/unit/test_validation_phase6.py`
- [X] T080 [P] [US4] Unit test: Summary report includes count of warnings/errors in `tests/unit/test_validation_phase6.py`
- [X] T081 [P] [US4] Unit test: Import log file created with ISO timestamp in filename in `tests/unit/test_validation_phase6.py`
- [X] T082 [P] [US4] Unit test: Duplicate result detection with clear warning message in `tests/unit/test_validation_phase6.py`
- [X] T083 [P] [US4] Unit test: PDF parse failure logged without halting import in `tests/unit/test_validation_phase6.py`
- [X] T084 [US4] Integration test: Full import with sample data containing quality issues; verify log contains all warnings in `tests/unit/test_validation_phase6.py`
- [X] T085 [P] [US4] Unit test: Standings warning for missing position value in `tests/unit/test_validation_phase6.py`
- [X] T086 [P] [US4] Unit test: Standings warning for missing total_score in `tests/unit/test_validation_phase6.py`
- [X] T087 [US4] Integration test: Standings import with issues; verify warnings logged in `tests/unit/test_validation_phase6.py`

### Implementation for User Story 4

- [X] T088 Implement summary report printing in `scripts/_import_logger.py` (format: section headers, counts, duration, log file path)
- [X] T089 Ensure all warnings/errors from T027-T062 tasks include descriptive messages in ImportLogger calls
- [ ] T090 Add validation helper functions to `scripts/_migration_helpers.py` (is_valid_position, is_valid_athlete_name, etc.) with logging
- [X] T091 Document expected warning types in README or docstring (`scripts/README-IMPORT.md` created)

**Checkpoint**: Import provides transparent reporting; admins can diagnose data quality issues

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final verification, documentation, and cleanup

### Documentation

- [X] T092 Update [quickstart.md](specs/001-import-results-standings/quickstart.md) with actual CLI commands + real examples post-implementation
- [X] T093 Create [README-IMPORT.md](scripts/README-IMPORT.md) documenting import scripts, options, troubleshooting
- [ ] T094 Add docstrings to all new classes/functions in `scripts/_import_logger.py`, `scripts/_migration_helpers.py` (enhanced), `scripts/migrate_results.py` (enhanced), `scripts/migrate_standings.py` (enhanced)
- [ ] T095 Document the import log JSON schema in comments or README (timestamp, level, stage, fields)

### Code Quality & Security

- [ ] T096 Run `ruff format scripts/` to format all new/modified migration scripts
- [ ] T097 Run `ruff check scripts/` to lint all migration scripts (fix any violations)
- [ ] T098 Run `bandit -r scripts/` to scan for security issues (must pass; no nosec suppressions without review)
- [ ] T099 Verify no hardcoded paths, secrets, or credentials in any scripts (code review)
- [ ] T100 Verify all DuckDB queries use parameterised statements (no SQL injection risk)

### Test Coverage & CI

- [ ] T101 Verify unit test coverage ≥85% across new modules: `coverage run -m pytest tests/unit/ && coverage report`
- [ ] T102 Verify all UI tests pass: `playwright test tests/ui/`
- [ ] T103 Verify pre-commit hooks pass: `pre-commit run --all-files`
- [ ] T104 Create `.github/workflows/import-tests.yml` (CI job to run import tests on PR)

### Final Verification

- [ ] T105 Manual end-to-end test: Run full import (results + standings) on staging data, verify counts match expectations
- [ ] T106 Manual UI verification: Browse `/results` and `/standings` pages post-import; verify all historical seasons visible
- [ ] T107 Manual export verification: Export results/standings to CSV and PDF; verify formatting correct
- [ ] T108 Performance verification: Time import of full dataset; verify completes in <5 minutes
- [ ] T109 Review import logs for warnings; document any systemic data quality issues for stakeholders
- [ ] T110 Update PR description with final migration summary (seasons imported, results count, standings count, any warnings)

**Checkpoint**: Feature complete, tested, documented, ready for merge

---

## Dependencies & Sequencing

### Critical Path (Must Complete in Order)

```
Phase 1 (T001-T004)
    ↓
Phase 2 (T005-T012)
    ↓ (blocks Phase 3)
Phase 3 (T013-T039) & Phase 4 (T040-T062) — Can run in parallel
    ↓ (blocks Phase 5)
Phase 5 (T063-T076) — Validation only, no code
    ↓ (after Phase 3 & 4)
Phase 6 (T077-T091) — Validation + logging enhancements
    ↓
Phase 7 (T092-T110) — Polish
```

### Parallelizable Work

| Parallel Group | Tasks |
|---|---|
| During Phase 1 | All four tasks independent |
| During Phase 2 | T002-T004, T007-T010, T012 (after T007-T010 complete) |
| During Phase 3 & 4 | All test tasks (T013-T050) can run in parallel; implementation tasks depend on tests first |
| During Phase 6 | Unit tests T077-T087 can run in parallel; integration tests depend on implementation complete |

---

## Effort Estimates by Phase

| Phase | Tasks | Est. Hours | Notes |
|-------|-------|-----------|-------|
| 1: Setup | T001-T004 | 2-3 | Logging infrastructure + test harness |
| 2: Foundational | T005-T012 | 4-5 | Review existing code + write helpers + tests |
| 3: US1 Results | T013-T039 | 6-8 | PDF parsing + DB integration + logging |
| 4: US2 Standings | T040-T062 | 4-5 | Reuse much of US1; standings-specific logic |
| 5: US3 Browsing | T063-T076 | 2-3 | UI verification only; existing routes should work |
| 6: US4 Validation | T077-T091 | 3-4 | Logging + validation helpers |
| 7: Polish | T092-T110 | 2-3 | Docs + final verification |
| **Total** | **110 tasks** | **23-31 hours** | Includes code + tests + docs |

---

## MVP Scope Recommendation

**Minimum Viable Product** (delivers 80% of value with 60% of effort):

1. ✅ Phase 1: Setup (must have)
2. ✅ Phase 2: Foundational (must have)
3. ✅ Phase 3: User Story 1 - Results Import (P1, must have)
4. ⏳ Phase 5: User Story 3 - Browsing (P2, already works, just verify)

**Stop here** — Users can now browse 40+ years of historical results. Estimated: **12-15 hours**

**Then iterate**:
- Phase 4: Standings Import (next priority if business needs it)
- Phase 6: Validation/Logging (enhanced reporting for admins)
- Phase 7: Polish (docs + final hardening)

This allows you to ship value quickly and gather user feedback before investing in enhancements.
