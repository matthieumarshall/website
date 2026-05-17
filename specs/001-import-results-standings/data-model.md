# Data Model: Import Legacy Results and Standings

**Date**: 2026-05-09 | **Plan**: [plan.md](plan.md)

## Entity Definitions

### Season

**Purpose**: Represent a league year (e.g., 2021-2022)

**Fields**:
| Field | Type | Constraints | Notes |
|-------|------|-----------|-------|
| id | INTEGER | PRIMARY KEY | Auto-increment via sequence |
| name | VARCHAR | NOT NULL, UNIQUE | e.g., "1988-1989", "2021-2022" |

**Source**: Extracted from folder structure
- Example: `data/original_website/files/results/2020-2030/2021-2022/` → season name = "2021-2022"

**Auto-Creation Logic**:
```python
def create_season_if_missing(con, season_name: str) -> int:
    # Lookup existing
    row = con.execute(
        "SELECT id FROM seasons WHERE lower(name) = lower(?)",
        [season_name]
    ).fetchone()
    if row:
        return int(row[0])

    # Create new
    con.execute("INSERT INTO seasons (name) VALUES (?)", [season_name])
    row = con.execute(
        "SELECT id FROM seasons WHERE lower(name) = lower(?)",
        [season_name]
    ).fetchone()
    return int(row[0])
```

**Validation**:
- Season name must be non-empty
- Season name should match pattern `YYYY-YYYY` (e.g., "2021-2022")
- Case-insensitive uniqueness check

---

### Fixture

**Purpose**: Represent a single race event (date, location, season)

**Fields**:
| Field | Type | Constraints | Notes |
|-------|------|-----------|-------|
| id | INTEGER | PRIMARY KEY | Auto-increment |
| season_id | INTEGER | NOT NULL, FK(seasons) | Links to Season |
| date | DATE | NOT NULL | Race date from filename |
| title | VARCHAR | NOT NULL | Venue name from filename |
| location | VARCHAR | NULL | Additional location info (optional) |

**Source**: Extracted from result PDF filename + season
- Filename: `20210101-Rnd1-BicesterHeritage-min.pdf`
- Parse: date=2021-01-01, round=1, venue="Bicester Heritage"

**Auto-Creation Logic**:
```python
def create_fixture_if_missing(
    con,
    season_id: int,
    fixture_date: date,
    venue_name: str
) -> int:
    # Lookup existing by (season_id, date)
    row = con.execute(
        "SELECT id FROM fixtures WHERE season_id = ? AND date = ?",
        [season_id, fixture_date]
    ).fetchone()
    if row:
        return int(row[0])

    # Create new
    con.execute(
        "INSERT INTO fixtures (season_id, date, title) VALUES (?, ?, ?)",
        [season_id, fixture_date, venue_name]
    )
    row = con.execute(
        "SELECT id FROM fixtures WHERE season_id = ? AND date = ?",
        [season_id, fixture_date]
    ).fetchone()
    return int(row[0])
```

**Deduplication**:
- Primary key: (season_id, date) — if already exists, reuse the fixture_id
- On `--force`: Delete existing fixture's races + results, then recreate

**Validation**:
- date must be parseable as YYYY-MM-DD
- venue_name must be non-empty
- season_id must exist

---

### Race

**Purpose**: Represent a category of race within a fixture (e.g., U13 Boys, Senior Men)

**Fields**:
| Field | Type | Constraints | Notes |
|-------|------|-----------|-------|
| id | INTEGER | PRIMARY KEY | Auto-increment |
| fixture_id | INTEGER | NOT NULL, FK(fixtures) | Links to Fixture |
| name | VARCHAR | NOT NULL | e.g., "Men", "U13 Boys", "Senior Women" |
| display_order | INTEGER | NOT NULL DEFAULT 0 | Sort order (junior to senior) |

**Source**: Extracted from PDF section headings (e.g., "Men" appears before race table)

**Display Order Logic**:
```python
RACE_DISPLAY_ORDER = ["U9", "U11", "U13", "U15", "U17", "Men", "Women", "Seniors", "Veterans"]

def infer_display_order(race_name: str) -> int:
    for i, keyword in enumerate(RACE_DISPLAY_ORDER):
        if keyword.lower() in race_name.lower():
            return i
    return len(RACE_DISPLAY_ORDER)  # fallback
```

**Validation**:
- name must be non-empty
- fixture_id must exist
- display_order must be ≥ 0

---

### Result

**Purpose**: Individual race result (one row in a race results table)

**Fields**:
| Field | Type | Constraints | Notes |
|-------|------|-----------|-------|
| id | INTEGER | PRIMARY KEY | Auto-increment |
| race_id | INTEGER | NOT NULL, FK(races) | Links to Race |
| position | INTEGER | NOT NULL | Finishing position (1, 2, 3, …) |
| race_number | INTEGER | NULL | Optional bib/race number |
| athlete_name | VARCHAR | NOT NULL | Full name as in PDF |
| time | VARCHAR | NOT NULL | Finish time (formatted as in PDF, e.g., "25:30") |
| category | VARCHAR | NOT NULL | Normalized category (e.g., "SM40", "U13G") |
| category_position | INTEGER | NULL | Position within category (e.g., 1st in age group) |
| gender | VARCHAR | NOT NULL | M, F, or other |
| gender_position | INTEGER | NULL | Position within gender (e.g., 1st woman) |
| club | VARCHAR | NULL | Runner's club/team |

**Source**: Extracted from PDF table rows

**Data Preservation**:
- All values are imported **as-is** from PDF without transformation
- No computation on times, positions, or scores
- NULL values used where data missing in PDF

**Validation Rules**:
- position must be positive integer; warn if missing/invalid, skip row if unable to parse
- athlete_name must be non-empty; warn if empty, attempt to continue
- time must be non-empty (accept any string format from PDF); warn if missing
- category must be non-empty; warn if missing, attempt to infer from context
- gender must be non-empty; warn if missing
- race_id must exist
- race_number, category_position, gender_position: accept NULL if missing
- club: accept NULL if missing

**Deduplication**:
- Key: (race_id, athlete_name, time)
- If result already exists with this key:
  - Without `--force`: skip (log as duplicate)
  - With `--force`: delete old + insert new

**Example**:
```sql
INSERT INTO results (
    race_id, position, race_number, athlete_name, time, category,
    category_position, gender, gender_position, club
) VALUES (
    42,           -- race_id
    1,            -- position
    101,          -- race_number
    "John Smith", -- athlete_name
    "25:30",      -- time (preserved exactly from PDF)
    "SM40",       -- category
    1,            -- category_position
    "M",          -- gender
    1,            -- gender_position
    "Oxford AC"   -- club
);
```

---

### Standing (Individual)

**Purpose**: End-of-season athlete ranking

**Fields**:
| Field | Type | Constraints | Notes |
|-------|------|-----------|-------|
| id | INTEGER | PRIMARY KEY | Auto-increment |
| season_id | INTEGER | NOT NULL, FK(seasons) | Links to Season |
| category | VARCHAR | NOT NULL | e.g., "SM40", "U13G" |
| position | INTEGER | NOT NULL | Final league position (1, 2, 3, …) |
| athlete_name | VARCHAR | NOT NULL | Full name as in standings PDF |
| club | VARCHAR | NULL | Club/team |
| total_score | INTEGER | NOT NULL | Total points/score (imported as-is) |
| rounds_competed | INTEGER | NOT NULL DEFAULT 0 | Number of rounds entered (optional) |
| fixture_scores | VARCHAR | NOT NULL DEFAULT '{}' | JSON mapping fixture_id → position score |
| is_imported | BOOLEAN | NOT NULL DEFAULT false | Flag: true = historical import, don't recalculate |

**Source**: Extracted from standings PDF table rows (individual league)

**Data Preservation**:
- position, total_score, rounds_competed: imported exactly as shown in PDF
- No recalculation of scores or positions
- is_imported = true ensures the recalculation pipeline never overwrites historical data

**Deduplication** (with `--force`):
- Delete all standings for (season_id, category) before re-importing
- Ensures clean replacement; avoids orphaned records

**Validation**:
- position must be positive integer; warn if missing
- athlete_name must be non-empty; warn if missing, skip row
- total_score must be integer; warn if invalid
- season_id must exist
- category must be non-empty; attempt infer from PDF heading if missing

**Example**:
```sql
INSERT INTO individual_standings (
    season_id, category, position, athlete_name, club, total_score,
    rounds_competed, fixture_scores, is_imported
) VALUES (
    15,                                     -- season_id
    "SM40",                                 -- category
    1,                                      -- position
    "Jane Doe",                             -- athlete_name
    "Harriers",                             -- club
    450,                                    -- total_score
    5,                                      -- rounds_competed
    '{"1": 10, "2": 9, "3": 8, "4": 7, "5": 6}', -- fixture_scores
    true                                    -- is_imported
);
```

---

### Standing (Team)

**Purpose**: End-of-season team ranking

**Fields**:
| Field | Type | Constraints | Notes |
|-------|------|-----------|-------|
| id | INTEGER | PRIMARY KEY | Auto-increment |
| season_id | INTEGER | NOT NULL, FK(seasons) | Links to Season |
| category | VARCHAR | NOT NULL | e.g., "Women", "U13 Boys" |
| position | INTEGER | NOT NULL | Final league position |
| team_name | VARCHAR | NOT NULL | Full team name (e.g., "Oxford City AC A") |
| club | VARCHAR | NOT NULL | Club name without label (e.g., "Oxford City AC") |
| team_label | VARCHAR | NULL | A, B, C, etc. |
| total_score | INTEGER | NOT NULL | Total team points |
| rounds_competed | INTEGER | NOT NULL DEFAULT 0 | Rounds entered |
| fixture_scores | VARCHAR | NOT NULL DEFAULT '{}' | JSON mapping fixture_id → team score |
| is_imported | BOOLEAN | NOT NULL DEFAULT false | Flag: true = historical import, don't recalculate |

**Source**: Extracted from standings PDF table rows (team league)

**Data Preservation**: Same as Individual — imported exactly as-is, marked is_imported=true

**Label Extraction**:
```python
def parse_team_name(full_name: str) -> tuple[str, str]:
    # "Oxford City AC A" → club="Oxford City AC", label="A"
    if full_name.endswith(" A") or full_name.endswith(" B") or full_name.endswith(" C"):
        parts = full_name.rsplit(" ", 1)
        return parts[0], parts[1]
    return full_name, None
```

---

## Relationships & Cascade Rules

```
Season (1) ──── (N) Fixture
                   ├─→ (1) Fixture ──── (N) Race
                   │              ├─→ (1) Race ──── (N) Result
                   │              └─→ (1) Race ──── (N) Result
                   │
                   └─→ Standings (Individual & Team)
```

**Cascade Behavior**:
- If Fixture deleted → delete associated Races → delete associated Results
- If Race deleted → delete associated Results
- If Season deleted (rare) → cascade to Fixtures → Races → Results + Standings

**FK Constraints** (Enforced by DuckDB):
- fixture.season_id → seasons.id (REFERENCES)
- race.fixture_id → fixtures.id (REFERENCES)
- result.race_id → races.id (REFERENCES)
- individual_standings.season_id → seasons.id (REFERENCES)
- team_standings.season_id → seasons.id (REFERENCES)

---

## Import State Machine

```
START
  ├─ [For each decade folder]
  │  └─ [For each season folder]
  │     ├─ create_season_if_missing() → season_id
  │     │
  │     └─ [For each result PDF file]
  │        ├─ parse_filename() → date, round, venue
  │        ├─ create_fixture_if_missing() → fixture_id
  │        │
  │        └─ [For each PDF page]
  │           └─ [For each extracted table]
  │              ├─ infer_race_name() → race_name
  │              ├─ create or reuse race record
  │              │
  │              └─ [For each table row]
  │                 ├─ parse_fields() → result dict
  │                 ├─ validate_and_normalize()
  │                 ├─ check_dedup(race_id, athlete_name, time)
  │                 ├─ if exists and not --force: SKIP + log "duplicate"
  │                 ├─ if exists and --force: DELETE old + INSERT new
  │                 ├─ if not exists: INSERT
  │                 └─ on error: log warning + continue
  │
  ├─ [For each standings PDF]
  │  ├─ parse_season_from_filename()
  │  ├─ lookup or create season
  │  │
  │  └─ [For each extracted standings table]
  │     ├─ classify as individual or team
  │     ├─ parse category from heading
  │     │
  │     └─ if --force: DELETE all standings for (season_id, category)
  │     └─ [For each table row]
  │        ├─ parse_fields() → standing dict
  │        ├─ validate()
  │        ├─ INSERT with is_imported=true
  │        └─ on error: log warning + continue
  │
  └─ DONE
     ├─ print summary: records imported, warnings, duration
     └─ write import log file
```

---

## Error Handling & Logging

**Log Levels**:
- **info**: Successful auto-creations, record insertions, summary
- **warning**: Data quality issues (missing fields, parse failures), duplicates skipped
- **error**: Critical failures (DB connection, constraint violations)

**Log Format** (JSON lines):
```json
{"timestamp": "2026-05-09T14:30:00Z", "level": "info", "stage": "season_create", "season": "1988-1989", "season_id": 1}
{"timestamp": "2026-05-09T14:30:01Z", "level": "info", "stage": "fixture_create", "fixture_date": "1988-01-22", "venue": "Stonesfield", "fixture_id": 42}
{"timestamp": "2026-05-09T14:30:02Z", "level": "info", "stage": "race_create", "fixture_id": 42, "race_name": "Men", "race_id": 101}
{"timestamp": "2026-05-09T14:30:03Z", "level": "info", "stage": "result_insert", "race_id": 101, "position": 1, "athlete": "John Smith"}
{"timestamp": "2026-05-09T14:30:04Z", "level": "warning", "stage": "result_parse", "file": "19880122-Rnd4-Stonesfield-min.pdf", "page": 1, "table": 0, "row": 5, "issue": "missing_time", "athlete": "Jane Doe"}
{"timestamp": "2026-05-09T14:30:05Z", "level": "error", "stage": "parse", "file": "19880205-Rnd5-Chilton-min.pdf", "reason": "pdf_extract_failed", "message": "No tables found in PDF"}
```

**Summary Report** (printed to stdout):
```
═══════════════════════════════════════════════════════════
Import Summary — 2026-05-09 14:35:00
═══════════════════════════════════════════════════════════
Results:     12,450 imported | 23 warnings
Standings:    1,230 imported |  5 warnings
─────────────────────────────────────────────────────────
Seasons created:  12
Fixtures created: 187
Races created:    412
─────────────────────────────────────────────────────────
Duration: 3 minutes 45 seconds
Log file: /path/to/import_20260509_143500.log
═══════════════════════════════════════════════════════════
```

---

## SQL Migration Scripts (Existing)

All tables required by this import already exist:

- `migrations/0003_create_seasons.sql` ✓
- `migrations/0004_create_fixtures.sql` ✓
- `migrations/0007_create_races_and_results.sql` ✓
- `migrations/0009_create_standings.sql` ✓

No new migrations required for import feature.
