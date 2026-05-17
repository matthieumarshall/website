# Feature Specification: Import Legacy Results and Standings

**Feature Branch**: `001-import-results-standings`
**Created**: 2026-05-09
**Status**: Draft
**Input**: User description: "Improve the migration scripts (in scripts folder) to import existing results and standings data from the old website. These should do no computation on the results or standings but allow the user to browse them for all historic seasons where there is data. Data is currently found in data\original_website\files\results"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Import Historical Results Data (Priority: P1)

An admin user needs to import all historical results from the legacy website into the new application without any data transformation or computation. The import should preserve all original data as-is so that the historical record remains intact and can be browsed.

**Why this priority**: This is the core functionality—without it, historical results are not available in the new system and the site cannot display past race results.

**Independent Test**: Can be fully tested by running the import script on the legacy data directory and verifying that all results appear in the database with original values unchanged.

**Acceptance Scenarios**:

1. **Given** legacy results data exists in `data/original_website/files/results`, **When** admin runs the import script, **Then** all results are loaded into the database with original data preserved unchanged
2. **Given** the import script is run, **When** import completes successfully, **Then** a summary report is displayed showing count of imported results and any warnings
3. **Given** multiple result files exist, **When** import runs, **Then** all files are processed in order and consolidated into a single dataset
4. **Given** results already exist in the database, **When** import runs with `--force` flag, **Then** existing results are replaced with fresh import data

### User Story 2 - Import Historical Standings Data (Priority: P1)

An admin user needs to import historical standings (league tables, rankings) from the legacy website for all seasons. Standings should be imported as-is without recalculation, preserving the historical state as it appeared on the old site.

**Why this priority**: Standings data is essential context for historical results. Users need to see how seasons ended and what the final league positions were.

**Independent Test**: Can be fully tested by running the import script on standings data and verifying that standings for all seasons are available and match the source data exactly.

**Acceptance Scenarios**:

1. **Given** legacy standings data exists, **When** admin runs the import script, **Then** all standings records are loaded with original values preserved
2. **Given** standings for multiple seasons exist, **When** import completes, **Then** standings are organized by season and accessible for browsing
3. **Given** standings data contains position, team info, and stats, **When** imported, **Then** all fields are preserved without modification or recalculation

### User Story 3 - Browse Historical Seasons and Results (Priority: P2)

A site visitor wants to browse results and standings from past seasons. The application should display a list of all seasons with available historical data and allow browsing results and standings for each season.

**Why this priority**: Once data is imported, users need a way to discover and view it. This completes the user journey from import to viewing.

**Independent Test**: Can be fully tested by verifying that a browseable interface displays all seasons with imported data and users can view results/standings for any historical season.

**Acceptance Scenarios**:

1. **Given** results and standings have been imported, **When** user visits the results page, **Then** a list of all available seasons is displayed
2. **Given** user selects a season, **When** they view it, **Then** results and standings for that season are displayed
3. **Given** historical data exists for seasons, **When** user browses, **Then** seasons are presented in reverse chronological order (newest first)

### User Story 4 - Validate Import Data Integrity (Priority: P2)

An admin user wants to verify that imported data is valid and complete before the import process completes. The system should detect and report any issues with the data to ensure integrity.

**Why this priority**: Data validation prevents corrupted or incomplete data from being imported, protecting data integrity.

**Independent Test**: Can be fully tested by running import on data with known issues (missing fields, malformed records) and verifying that warnings/errors are reported clearly.

**Acceptance Scenarios**:

1. **Given** import script encounters invalid data, **When** processing, **Then** warnings are logged and reported to the user
2. **Given** required fields are missing from a record, **When** import runs, **Then** the specific record is flagged with details about missing data
3. **Given** import completes, **When** summary is displayed, **Then** it includes count of records processed, warnings encountered, and errors that prevented import

### Edge Cases

- What happens if the legacy data directory doesn't exist or is empty?
- How does the system handle duplicate results (same race, same participants)?
- What if standings data contains teams no longer in the system?
- How does the system behave if the import is interrupted mid-process?
- What happens if some result records have missing or malformed data?

## Clarifications

### Session 2026-05-09

- Q: When results already exist and import is re-run, should we update/replace or skip? → A: Update existing records (replace on re-run)
- Q: How should import handle missing/malformed fields? → A: Import with NULL values where possible and log warnings/issues
- Q: Should seasons be auto-created if they don't exist in the database? → A: Yes, auto-create seasons from folder names
- Q: Should fixtures be auto-created if missing? → A: Yes, auto-create fixtures from result filename (date + venue)
- Q: How should we discover existing browsing routes/UI for historical data? → A: Discover in codebase during planning phase

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST read results data from `data/original_website/files/results` without modification
- **FR-002**: System MUST read standings data from legacy data source without modification
- **FR-003**: System MUST import all results into the database with original values preserved exactly
- **FR-004**: System MUST import all standings into the database with original values preserved exactly
- **FR-005**: System MUST NOT perform any computation on results data (e.g., recalculate times, points, or positions)
- **FR-006**: System MUST NOT perform any computation on standings data (e.g., recalculate league positions or statistics)
- **FR-007**: Import script MUST support a dry-run mode to preview what will be imported without making changes
- **FR-008**: Import script MUST provide a detailed summary report after completion showing count of records imported and any warnings/errors
- **FR-009**: System MUST display all seasons with available imported data in the web interface
- **FR-010**: Users MUST be able to view results for a selected historical season
- **FR-011**: Users MUST be able to view standings for a selected historical season
- **FR-012**: System MUST validate imported data and report any integrity issues to the admin
- **FR-013**: Import script MUST support `--force` flag to re-import and replace existing data (overwrite on re-run)
- **FR-014**: System MUST auto-create seasons if they don't exist (identified by folder name, e.g., "1988-1989")
- **FR-015**: System MUST auto-create fixtures if missing (identified by result filename: date and venue)
- **FR-016**: System MUST import records with NULL/empty values for missing or malformed fields rather than skipping the record
- **FR-017**: System MUST log warnings for all missing/malformed fields encountered during import
- **FR-018**: System MUST discover and reuse existing browsing routes/UI components for displaying historical seasonal data

### Key Entities *(include if feature involves data)*

- **Result**: A single race result record containing participant, position, time, and other race-specific metrics as they appeared in the legacy system
- **Standing**: A league position record for a season, containing team/participant rank, points, and statistics as they appeared in the legacy system
- **Season**: A time period (e.g., calendar year or league year) grouping results and standings, auto-created from legacy folder structure
- **Fixture**: A race event (date, location) auto-created from result file metadata (filename date and venue)
- **Import Log**: Metadata about an import operation including timestamp, records processed, warnings, and errors

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of result records from legacy data are successfully imported into the database (or skipped with reason if malformed)
- **SC-002**: 100% of standings records from legacy data are successfully imported into the database (or skipped with reason if malformed)
- **SC-003**: All imported data values match source data exactly (no values modified, computed, or transformed)
- **SC-004**: Admin can run import script and complete it in under 5 minutes for typical legacy dataset
- **SC-005**: Import provides clear feedback with count of records processed, warnings logged, and issues encountered
- **SC-006**: Users can browse and view results/standings for all historical seasons with available data
- **SC-007**: 100% of imported results are browseable through the web interface without errors
- **SC-008**: Seasons are auto-created if missing; fixtures are auto-created if missing; process completes without manual intervention

## Assumptions

- Legacy data files are in PDF format following consistent naming convention (`YYYYMMDD-RndN-VenueName-min.pdf`)
- Results PDFs contain extractable tables with columns: position, athlete_name, time, category, gender (optional: race_number, category_position, gender_position, club)
- Standings PDFs contain extractable tables for individual and/or team standings with position, name, club, and score columns
- Season identifiers can be extracted from folder names (e.g., "1988-1989" → season_id auto-generated or matched to existing)
- Fixture information (date, venue) can be reliably extracted from result filename: `YYYYMMDD-RndN-VenueName-min.pdf`
- Existing database schema supports storing historical results and standings alongside current data
- Admin user has access to the scripts folder and can run command-line tools
- The web interface already has infrastructure for displaying seasonal data (routes, templates); import just populates the data
