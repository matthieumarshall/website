# Entries & Results Plan

## 1. Overview

The system must handle three distinct data scenarios:

| Scenario | Results source | Standings source | Entries? |
|---|---|---|---|
| **Historic seasons** | CSV import (bulk) | CSV import (pre-calculated) | No |
| **Current / recent seasons** | CSV upload per fixture OR fetch from Tempo Events | Calculated from results | Yes |
| **Future seasons** | Not yet available | N/A | Yes (entry management before results exist) |

All three scenarios must coexist — a user browsing the site should be able to navigate seamlessly from a 2018 historic season through to the current live season.

---

## 2. Data Flow

### 2a. Historic Data (one-time backfill)

```
CSV (results)    →  parse & validate  →  seasons / fixtures / races / results tables
CSV (standings)  →  parse & validate  →  standings table (is_imported = true)
```

Admin uploads a results CSV and/or a standings CSV for a past season. The importer creates the season, fixtures, races, and results rows if they don't already exist, and stores standings as-is (no recalculation — the imported numbers are authoritative).

### 2b. Current Season — CSV Upload

```
Admin uploads results CSV for a fixture
  → parse & validate
  → insert into races / results
  → trigger standings recalculation for that season
```

### 2c. Current Season — External Fetch (Tempo Events)

```
Admin clicks "Fetch from Tempo Events" for a fixture
  → backend calls Tempo Events API
  → maps response to internal results format
  → insert into races / results
  → trigger standings recalculation for that season
```

### 2d. Entries

```
Team manager creates entries for a season
  → athletes + entries rows created
  → race numbers assigned (manually or auto)
  → payment tracked
  → once results exist, entries link to results via race_number + fixture
```

---

## 3. Database Schema

### 3.1 Existing Tables (no changes needed)

These tables remain as-is:

- **seasons** — `id`, `name`, `created_at`
- **fixtures** — `id`, `season_id`, `title`, `date`, `location_name`, `address`, …
- **races** — `id`, `fixture_id`, `name`, `display_order`, `created_at`
- **results** — `id`, `race_id`, `position`, `race_number`, `athlete_name`, `time`, `category`, `category_position`, `gender`, `gender_position`, `club`

The results table stores denormalised athlete info (name, club, gender). This is correct — results are a historical record and must not change if an athlete later updates their profile.

### 3.2 New: `season_config`

Metadata per season that controls how standings are calculated and whether the season accepts entries.

```sql
CREATE TABLE season_config (
    season_id           INTEGER PRIMARY KEY REFERENCES seasons(id),
    scoring_scheme      VARCHAR NOT NULL DEFAULT 'position',
    -- 'position' = points by finish position (1st→N pts, 2nd→N-1, …)
    -- 'fixed'    = explicit points array (for historic leagues with custom rules)
    -- 'none'     = no standings for this season
    points_json         VARCHAR NOT NULL DEFAULT '[]',
    -- Only used when scoring_scheme = 'fixed'.
    -- JSON array: [10, 8, 6, 5, 4, 3, 2, 1] — index 0 = 1st place, etc.
    counting_fixtures   INTEGER,
    -- NULL = all fixtures count. Otherwise best N fixtures.
    entries_enabled     BOOLEAN NOT NULL DEFAULT false,
    -- true for current/future seasons where team managers can enter athletes.
    entry_fee_pence     INTEGER,
    -- cost per athlete entry (NULL = free / not applicable)
    created_at          TIMESTAMP DEFAULT current_timestamp
);
```

### 3.3 New: `athletes`

A normalised athlete identity used by the entries system. Results remain denormalised — the link from entries to results goes through `race_number` + `fixture_id`, NOT through a foreign key.

```sql
CREATE TABLE athletes (
    id              INTEGER PRIMARY KEY,
    first_name      VARCHAR NOT NULL,
    last_name       VARCHAR NOT NULL,
    gender          VARCHAR NOT NULL,
    date_of_birth   DATE,
    club            VARCHAR,
    created_at      TIMESTAMP DEFAULT current_timestamp
);
```

**Why not link `results.athlete_id → athletes.id`?**

- Historic results will never have a corresponding athlete record.
- External results (Tempo Events) use athlete names, not our internal IDs.
- Results are immutable snapshots — they should not change when an athlete's profile is updated.
- Matching is done opportunistically (by race number within a fixture) when displaying entry↔result links in the UI.

### 3.4 New: `entries`

An entry represents one athlete registered for one season. Race numbers are assigned at entry time and are unique within a season.

```sql
CREATE TABLE entries (
    id              INTEGER PRIMARY KEY,
    season_id       INTEGER NOT NULL REFERENCES seasons(id),
    athlete_id      INTEGER NOT NULL REFERENCES athletes(id),
    category        VARCHAR NOT NULL,
    -- Age-group category, e.g. 'U9', 'U11', 'U13', 'Senior'
    race_number     INTEGER,
    -- Unique within a season. Assigned manually or via auto-increment.
    entered_by      INTEGER REFERENCES users(id),
    -- The team manager who submitted this entry.
    entered_at      TIMESTAMP DEFAULT current_timestamp,
    payment_status  VARCHAR NOT NULL DEFAULT 'unpaid',
    -- One of: 'unpaid', 'paid', 'refunded', 'waived'
    payment_amount  INTEGER,
    -- Amount in pence (NULL until paid)
    payment_ref     VARCHAR,
    -- Stripe PaymentIntent ID or manual reference
    notes           TEXT,
    UNIQUE(season_id, athlete_id),
    UNIQUE(season_id, race_number)
);
```

### 3.5 New: `standings`

Stores both imported historic standings and calculated current standings. When a season's results change, the calculated rows are deleted and regenerated.

```sql
CREATE TABLE standings (
    id                  INTEGER PRIMARY KEY,
    season_id           INTEGER NOT NULL REFERENCES seasons(id),
    category            VARCHAR NOT NULL,
    -- Same category values as results.category / entries.category
    position            INTEGER NOT NULL,
    athlete_name        VARCHAR NOT NULL,
    club                VARCHAR,
    gender              VARCHAR,
    total_points        INTEGER NOT NULL,
    fixture_points_json VARCHAR NOT NULL DEFAULT '[]',
    -- JSON array of objects: [{"fixture_id": 1, "points": 10}, …]
    -- Preserves per-fixture breakdown for display.
    counting_points     INTEGER,
    -- Total of best-N fixtures (= total_points if all count).
    is_imported         BOOLEAN NOT NULL DEFAULT false,
    -- true = historic CSV import (never recalculated)
    -- false = calculated from results (regenerated on demand)
    updated_at          TIMESTAMP DEFAULT current_timestamp
);
```

### 3.6 Entity Relationship Summary

```
seasons ──┬── fixtures ──── races ──── results
           │
           ├── season_config
           │
           ├── entries ──── athletes
           │       ↑
           │       └── users (entered_by = team manager)
           │
           └── standings
```

The dotted link from **entries → results** is logical, not a FK:
- Match on `entries.race_number = results.race_number` within the same season's fixtures.
- This allows the UI to show "View result" next to an entry once results are uploaded.

---

## 4. CSV Import Formats

### 4a. Results CSV (existing — already supported for current season)

Current upload format per fixture:

```csv
Position,RaceNumber,Name,Time,Category,CatPos,Gender,GenderPos,Club
1,142,Jane Smith,00:12:34,U13,1,F,1,Springfield AC
2,87,John Doe,00:12:45,U13,2,M,1,River Harriers
```

Each CSV maps to one race within a fixture. The admin selects the fixture and race (or creates a new race name) at upload time.

### 4b. Historic Results CSV (bulk import for an entire season)

For historic data where we need to create seasons, fixtures, and races in one go:

```csv
Season,FixtureTitle,FixtureDate,RaceName,Position,RaceNumber,Name,Time,Category,CatPos,Gender,GenderPos,Club
2018-19,Fixture 1,2018-10-06,U13 Boys,1,,John Doe,12:34,U13,1,M,1,Springfield AC
2018-19,Fixture 1,2018-10-06,U13 Boys,2,,Jane Smith,12:45,U13,2,F,1,River Harriers
2018-19,Fixture 2,2018-11-03,U13 Boys,1,,Jane Smith,11:58,U13,1,F,1,River Harriers
```

The importer:
1. Creates the season if `name` doesn't exist.
2. Creates fixtures (deduped by season + title).
3. Creates races (deduped by fixture + race name).
4. Inserts result rows.

Race numbers may be blank for historic data (not all old records have them).

### 4c. Historic Standings CSV

```csv
Season,Category,Position,Name,Club,Gender,TotalPoints,F1,F2,F3,F4,F5
2018-19,U13,1,Jane Smith,River Harriers,F,45,10,10,,15,10
2018-19,U13,2,John Doe,Springfield AC,M,38,8,8,12,10,
```

`F1`–`F5` columns are per-fixture points (empty = DNS/no score). These are stored in `fixture_points_json` as an ordered array. These standings are imported with `is_imported = true` and never recalculated.

---

## 5. Standings Calculation

### 5.1 When to Calculate

Standings are recalculated for a season when:
- Results are uploaded or fetched for any fixture in that season.
- Results are edited or deleted.
- An admin explicitly triggers recalculation.

Historic imported standings (`is_imported = true`) are **never** recalculated.

### 5.2 Algorithm

For a given season with `scoring_scheme = 'position'`:

```
For each category:
    For each fixture/race in the season:
        Award points based on category position:
            1st → max_points, 2nd → max_points - 1, … (min 1 point)
        Where max_points = number of finishers in that category for that race

    For each athlete (grouped by name + club):
        Collect their points across all fixtures
        If counting_fixtures is set:
            Sort fixture points descending
            Take best N (counting_fixtures)
        Sum → total_points / counting_points

    Rank athletes by counting_points descending
    Write standings rows
```

For `scoring_scheme = 'fixed'`, use the explicit `points_json` array instead of position-based points.

### 5.3 Tie-Breaking

When athletes share the same `counting_points`:
1. Most fixture appearances.
2. Best single-fixture result.
3. Alphabetical by name (stable fallback).

---

## 6. Entries System Design

### 6.1 Roles

| Role | Can do |
|---|---|
| **Admin** | Everything: manage seasons, configure entries, assign numbers, view all entries, override payments |
| **Team manager** | Enter athletes for their club, view their own entries, see payment status |
| **Public** | View published entry lists (names, clubs, numbers — no payment info) |

The `team_manager` role (referenced in high-level-plan.md Phase 1.3) needs to be created. A team manager is associated with a club name.

### 6.2 Entry Workflow

```
1. Admin enables entries for a season (season_config.entries_enabled = true)
2. Team manager navigates to Entries page → sees open seasons
3. Team manager adds athletes:
   - First name, last name, gender, date of birth, club (auto-filled from their profile)
   - Category is derived from DOB + season start date, or manually overridden
4. Admin (or system) assigns race numbers
5. Team manager pays (Stripe or manual)
6. Entry confirmed — visible on public entry list
```

### 6.3 Entry ↔ Result Linking

Once results are uploaded for a fixture:

```python
# Pseudocode for linking
def get_entry_for_result(result: Result, season_id: int) -> Entry | None:
    """Find the entry matching a result via race number."""
    if result.race_number is None:
        return None
    return db.execute(
        "SELECT * FROM entries WHERE season_id = ? AND race_number = ?",
        [season_id, result.race_number]
    )
```

This allows:
- On the **results page**: show "Entered by [team]" next to each result.
- On the **entries page**: show "Results: 1st at Fixture 1, 3rd at Fixture 2" next to each entry.
- Athletes without entries still appear in results (e.g. guest runners, historic data).

### 6.4 Entries Data Not Relevant to Results

The entries table deliberately contains fields that results don't need:

| Field | Purpose | Visible on results? |
|---|---|---|
| `entered_by` | Which team manager submitted | No |
| `entered_at` | When the entry was made | No |
| `payment_status` | Payment tracking | No (admin only) |
| `payment_amount` | Fee paid | No (admin only) |
| `payment_ref` | Stripe/manual reference | No (admin only) |
| `notes` | Admin notes | No |

---

## 7. External Results Integration (Tempo Events)

### 7.1 Fetch Flow

```
Admin navigates to fixture → clicks "Fetch from Tempo Events"
  → Admin enters Tempo Events race/event ID
  → Backend calls Tempo Events API
  → Response mapped to internal Result format
  → Preview shown to admin for confirmation
  → On confirm: inserted into races/results, standings recalculated
```

### 7.2 Data Mapping

The Tempo Events API response needs to be mapped to our results schema. The mapping layer should be isolated (e.g. `tempo_events.py`) so it can adapt if their API changes. Key fields to map:

```
Tempo Events field  →  Our field
---
position            →  results.position
bib_number          →  results.race_number
name                →  results.athlete_name
finish_time         →  results.time
age_category        →  results.category
category_position   →  results.category_position
gender              →  results.gender
gender_position     →  results.gender_position
club                →  results.club
```

### 7.3 Caching & Idempotency

- Store the Tempo Events event ID on the fixture or race so we can detect duplicate fetches.
- If results already exist for that race, warn the admin before overwriting.

---

## 8. Migration Strategy

New tables should be added as numbered migration scripts:

| Migration | Tables |
|---|---|
| `0008_create_season_config.sql` | `season_config` |
| `0009_create_athletes.sql` | `athletes` |
| `0010_create_entries.sql` | `entries` |
| `0011_create_standings.sql` | `standings` |

Each migration is idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE SEQUENCE IF NOT EXISTS`).

### Backfill for Existing Seasons

After migration, existing seasons will have no `season_config` row. The application should treat a missing config as:
- `scoring_scheme = 'none'`
- `entries_enabled = false`

An admin can retroactively add config to compute standings for existing seasons with results.

---

## 9. Implementation Phases

Suggested order based on dependencies and value:

### Phase A: Standings for Current Seasons
1. Add `season_config` and `standings` tables.
2. Build standings calculation logic.
3. Add standings display on results page (new tab or section per season).
4. Add admin UI to configure scoring rules per season.
5. Add "Recalculate standings" button for admins.

### Phase B: Historic Data Import
1. Build bulk CSV importer for historic results (creates seasons/fixtures/races/results).
2. Build CSV importer for historic standings (`is_imported = true`).
3. Ensure browse/display works seamlessly across historic and current seasons.

### Phase C: Entries System
1. Add `athletes` and `entries` tables.
2. Add `team_manager` role.
3. Build entry management UI for team managers.
4. Build race number assignment (admin).
5. Build public entry list view.
6. Link entries ↔ results in the UI.

### Phase D: Payments (Stripe)
1. Stripe integration for entry payments.
2. Payment confirmation and webhook handling.

### Phase E: External Results Fetch
1. Tempo Events API integration module.
2. Admin "Fetch results" UI per fixture.
3. Preview and confirmation before import.

---

## 10. Open Questions

1. **Scoring rules**: What is the exact points scheme used by the league? Is it consistent across all seasons, or has it changed?
2. **Counting fixtures**: Do all fixtures count, or best N of M? Has this changed across seasons?
3. **Category derivation**: Is category purely by age (DOB + season date), or can it be manually assigned? Are there mixed/open categories?
4. **Race numbers**: Are numbers unique per season, or per fixture? Do they carry across seasons?
5. **Tempo Events**: What is the API endpoint/format? Is authentication required? Is there a sandbox?
6. **Guest runners**: Can athletes without entries appear in results? How should they be handled in standings (excluded, or counted)?
7. **Team scoring**: Is there a team competition alongside individual standings? (Sum of top N athletes per club)
8. **Historic data availability**: How many seasons of historic results/standings CSVs exist? Are they all in the same format?
