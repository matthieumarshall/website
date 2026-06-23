# Data Model: Team Entries

**Date**: 2026-06-07 | **Plan**: [plan.md](plan.md)

---

## Existing Tables (unchanged)

- **`seasons`** — `id`, `name`, `created_at`
- **`fixtures`** — `id`, `season_id`, `title`, `date`, `location_name`, `address`, …
- **`users`** — `id`, `username`, `password_hash`, `role`, `email`, `created_at`

The `users.role` field currently supports `admin`. A new role value `club_manager` is added (no schema change required — `role` is a `VARCHAR`).

---

## New Tables

### `clubs`

**Purpose**: Master list of OXL member clubs with their EA club ID. Admin-maintained.

**Migration**: `0013_create_clubs.sql`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | `INTEGER` | PK, `nextval('club_id_seq')` | |
| `name` | `VARCHAR` | NOT NULL | Full name e.g. "Oxford City AC" |
| `oxl_code` | `VARCHAR` | NOT NULL, UNIQUE | Short code e.g. "OxC" |
| `ea_club_id` | `VARCHAR` | NOT NULL | EA's numeric club ID (string to avoid leading-zero loss) |
| `is_active` | `BOOLEAN` | NOT NULL, DEFAULT true | Soft-delete; inactive clubs cannot enter |
| `created_at` | `TIMESTAMP` | DEFAULT `current_timestamp` | |

**Validation**:
- `ea_club_id` must be non-empty and match `\d+` (digits only).
- `oxl_code` must be unique and non-empty.
- Deleting a club is forbidden if it has associated `entry_batches`; use `is_active = false`.

---

### `club_managers`

**Purpose**: Associates a user account (with `role = 'club_manager'`) to exactly one club. Admin-created.

**Migration**: `0014_create_club_managers.sql`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | `INTEGER` | PK, `nextval('club_manager_id_seq')` | |
| `user_id` | `INTEGER` | NOT NULL, FK → `users(id)`, UNIQUE | One club per manager account |
| `club_id` | `INTEGER` | NOT NULL, FK → `clubs(id)` | |
| `is_active` | `BOOLEAN` | NOT NULL, DEFAULT true | |
| `created_at` | `TIMESTAMP` | DEFAULT `current_timestamp` | |

**Validation**:
- A user can only be a manager for one club at a time (enforced by UNIQUE on `user_id`).
- If `is_active = false`, the user can log in but cannot create or view entries.

---

### `season_entry_config`

**Purpose**: Per-season settings controlling whether entries are open and the EA reference date for age category calculation.

**Migration**: `0015_create_season_entry_config.sql`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `season_id` | `INTEGER` | PK, FK → `seasons(id)` | |
| `entries_open` | `BOOLEAN` | NOT NULL, DEFAULT false | Admin toggle; system also enforces deadline per fixture |
| `ea_reference_date` | `DATE` | NOT NULL | Usually 31 Aug of season start year (for age category) |
| `total_fixtures` | `INTEGER` | NOT NULL, DEFAULT 5 | Used to validate price tier completeness |
| `created_at` | `TIMESTAMP` | DEFAULT `current_timestamp` | |

**Validation**:
- `ea_reference_date` must be in the past by the time entries open.
- `total_fixtures` must match the number of fixtures attached to the season.

---

### `entry_price_tiers`

**Purpose**: Lookup table: for a given season and number of fixtures remaining, what is the price per junior and adult athlete?

**Migration**: `0016_create_entry_price_tiers.sql`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | `INTEGER` | PK, `nextval('entry_price_tier_id_seq')` | |
| `season_id` | `INTEGER` | NOT NULL, FK → `seasons(id)` | |
| `fixtures_remaining` | `INTEGER` | NOT NULL, CHECK ≥ 1 | e.g. 5 = full season |
| `junior_pence` | `INTEGER` | NOT NULL, CHECK ≥ 0 | Price in GBP pence |
| `adult_pence` | `INTEGER` | NOT NULL, CHECK ≥ 0 | Price in GBP pence |
| `updated_at` | `TIMESTAMP` | NOT NULL, DEFAULT `current_timestamp` | Updated when admin changes price |
| UNIQUE | | `(season_id, fixtures_remaining)` | One tier per remaining-count per season |

**Validation**:
- Prices must be non-negative.
- `fixtures_remaining` must be between 1 and `season_entry_config.total_fixtures`.
- Admin can only edit `junior_pence` / `adult_pence`. The `updated_at` is refreshed on each edit.
- Changing a price tier does **not** affect existing `athlete_entries` rows (prices are snapshotted there).

---

### `entry_batches`

**Purpose**: One submission event — a team manager selects a set of athletes and pays for them together. Multiple batches per club per season are allowed.

**Migration**: `0017_create_entry_batches.sql`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | `INTEGER` | PK, `nextval('entry_batch_id_seq')` | |
| `season_id` | `INTEGER` | NOT NULL, FK → `seasons(id)` | |
| `club_id` | `INTEGER` | NOT NULL, FK → `clubs(id)` | |
| `manager_user_id` | `INTEGER` | NOT NULL, FK → `users(id)` | User who created the batch |
| `status` | `VARCHAR` | NOT NULL, DEFAULT `'pending_payment'` | See states below |
| `fixtures_remaining_at_entry` | `INTEGER` | NOT NULL | Snapshot — fixtures open when batch was created |
| `total_pence` | `INTEGER` | NOT NULL, DEFAULT 0 | Sum of all athlete entry prices; snapshot |
| `stripe_checkout_session_id` | `VARCHAR` | NULLABLE | Set when Stripe session is created |
| `stripe_payment_intent_id` | `VARCHAR` | NULLABLE | Set from webhook |
| `stripe_payment_method` | `VARCHAR` | NULLABLE | `'card'` or `'bacs_debit'`; set from webhook |
| `paid_at` | `TIMESTAMP` | NULLABLE | Set when `status` transitions to `paid` |
| `created_at` | `TIMESTAMP` | DEFAULT `current_timestamp` | |

**Status State Machine**:
```
pending_payment
  → payment_initiated   (Stripe checkout.session.completed, payment_status='unpaid' = BACS mandate)
  → paid                (checkout.session.completed, payment_status='paid' = card)
                         OR charge.succeeded (BACS settlement)
  → payment_failed      (checkout.session.expired)
```

**Validation**:
- A batch in `pending_payment` or `payment_failed` can be retried (manager can create a new Stripe session).
- A batch is immutable once `paid`.
- `total_pence` is the sum of `athlete_entries.amount_pence` for this batch.

---

### `athlete_entries`

**Purpose**: One row per athlete per season per batch. Immutable once the batch is `paid`.

**Migration**: `0018_create_athlete_entries.sql`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | `INTEGER` | PK, `nextval('athlete_entry_id_seq')` | |
| `batch_id` | `INTEGER` | NOT NULL, FK → `entry_batches(id)` | |
| `season_id` | `INTEGER` | NOT NULL, FK → `seasons(id)` | Denormalised for query convenience |
| `club_id` | `INTEGER` | NOT NULL, FK → `clubs(id)` | Denormalised for query convenience |
| `ea_urn` | `INTEGER` | NOT NULL | EA URN from TRAPI API |
| `athlete_name` | `VARCHAR` | NOT NULL | As returned by EA — denormalised historical record |
| `date_of_birth` | `DATE` | NOT NULL | As returned by EA |
| `ea_age_category` | `VARCHAR` | NOT NULL | Computed at entry time: 'U9', 'U11', …, 'Veteran' |
| `is_junior` | `BOOLEAN` | NOT NULL | true if category ∈ {U9, U11, U13, U15, U17} |
| `amount_pence` | `INTEGER` | NOT NULL | Price paid for this athlete; snapshot at batch creation |
| `race_number` | `INTEGER` | NULLABLE | Assigned when batch transitions to `paid` |
| `created_at` | `TIMESTAMP` | DEFAULT `current_timestamp` | |
| UNIQUE | | `(season_id, club_id, ea_urn)` | One entry per athlete per club per season |

**Validation**:
- `ea_urn` must be a positive integer.
- `athlete_name` and `date_of_birth` must not be empty.
- `amount_pence` must match the price tier for `(season_id, fixtures_remaining_at_entry, is_junior)` at time of creation — validated server-side.
- UNIQUE constraint on `(season_id, club_id, ea_urn)` prevents a club from entering the same athlete twice in a season. The same EA athlete may be entered by a different club (both entries are valid and independently priced).
- `race_number` is auto-assigned sequentially within the season: `MAX(race_number) + 1` at the time the batch is confirmed as `paid`.

---

## Entity Relationship Summary

```
seasons ──┬─── fixtures
          ├─── season_entry_config
          ├─── entry_price_tiers
          └─── entry_batches ──── athlete_entries
                    │
                    ├── clubs ──── club_managers ──── users
                    └── users (manager_user_id)
```

---

## Pydantic Models (src/website/models.py additions)

```python
from pydantic import BaseModel
from datetime import date, datetime

class Club(BaseModel):
    id: int
    name: str
    oxl_code: str
    ea_club_id: str
    is_active: bool

class PriceTier(BaseModel):
    season_id: int
    fixtures_remaining: int
    junior_pence: int
    adult_pence: int

class EntryBatchStatus(str):
    PENDING = "pending_payment"
    INITIATED = "payment_initiated"
    PAID = "paid"
    FAILED = "payment_failed"

class AthleteEntryRow(BaseModel):
    ea_urn: int
    athlete_name: str
    date_of_birth: date
    ea_age_category: str
    is_junior: bool
    amount_pence: int

class EntryBatch(BaseModel):
    id: int
    season_id: int
    club_id: int
    manager_user_id: int
    status: str
    fixtures_remaining_at_entry: int
    total_pence: int
    stripe_checkout_session_id: str | None
    stripe_payment_intent_id: str | None
    stripe_payment_method: str | None
    paid_at: datetime | None
    created_at: datetime
```

---

## Migration SQL Sketches

### 0013_create_clubs.sql
```sql
CREATE SEQUENCE IF NOT EXISTS club_id_seq START 1;
CREATE TABLE IF NOT EXISTS clubs (
    id         INTEGER   DEFAULT nextval('club_id_seq') PRIMARY KEY,
    name       VARCHAR   NOT NULL,
    oxl_code   VARCHAR   NOT NULL UNIQUE,
    ea_club_id VARCHAR   NOT NULL,
    is_active  BOOLEAN   NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT current_timestamp
);
```

### 0014_create_club_managers.sql
```sql
CREATE SEQUENCE IF NOT EXISTS club_manager_id_seq START 1;
CREATE TABLE IF NOT EXISTS club_managers (
    id         INTEGER   DEFAULT nextval('club_manager_id_seq') PRIMARY KEY,
    user_id    INTEGER   NOT NULL UNIQUE REFERENCES users(id),
    club_id    INTEGER   NOT NULL REFERENCES clubs(id),
    is_active  BOOLEAN   NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT current_timestamp
);
```

### 0015_create_season_entry_config.sql
```sql
CREATE TABLE IF NOT EXISTS season_entry_config (
    season_id          INTEGER PRIMARY KEY REFERENCES seasons(id),
    entries_open       BOOLEAN NOT NULL DEFAULT false,
    ea_reference_date  DATE    NOT NULL,
    total_fixtures     INTEGER NOT NULL DEFAULT 5,
    created_at         TIMESTAMP DEFAULT current_timestamp
);
```

### 0016_create_entry_price_tiers.sql
```sql
CREATE SEQUENCE IF NOT EXISTS entry_price_tier_id_seq START 1;
CREATE TABLE IF NOT EXISTS entry_price_tiers (
    id                INTEGER   DEFAULT nextval('entry_price_tier_id_seq') PRIMARY KEY,
    season_id         INTEGER   NOT NULL REFERENCES seasons(id),
    fixtures_remaining INTEGER  NOT NULL CHECK (fixtures_remaining >= 1),
    junior_pence      INTEGER   NOT NULL CHECK (junior_pence >= 0),
    adult_pence       INTEGER   NOT NULL CHECK (adult_pence >= 0),
    updated_at        TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE (season_id, fixtures_remaining)
);
```

### 0017_create_entry_batches.sql
```sql
CREATE SEQUENCE IF NOT EXISTS entry_batch_id_seq START 1;
CREATE TABLE IF NOT EXISTS entry_batches (
    id                          INTEGER   DEFAULT nextval('entry_batch_id_seq') PRIMARY KEY,
    season_id                   INTEGER   NOT NULL REFERENCES seasons(id),
    club_id                     INTEGER   NOT NULL REFERENCES clubs(id),
    manager_user_id             INTEGER   NOT NULL REFERENCES users(id),
    status                      VARCHAR   NOT NULL DEFAULT 'pending_payment',
    fixtures_remaining_at_entry INTEGER   NOT NULL,
    total_pence                 INTEGER   NOT NULL DEFAULT 0,
    stripe_checkout_session_id  VARCHAR,
    stripe_payment_intent_id    VARCHAR,
    stripe_payment_method       VARCHAR,
    paid_at                     TIMESTAMP,
    created_at                  TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_entry_batches_season_club
    ON entry_batches (season_id, club_id);
CREATE INDEX IF NOT EXISTS idx_entry_batches_stripe_session
    ON entry_batches (stripe_checkout_session_id);
```

### 0018_create_athlete_entries.sql
```sql
CREATE SEQUENCE IF NOT EXISTS athlete_entry_id_seq START 1;
CREATE TABLE IF NOT EXISTS athlete_entries (
    id               INTEGER   DEFAULT nextval('athlete_entry_id_seq') PRIMARY KEY,
    batch_id         INTEGER   NOT NULL REFERENCES entry_batches(id),
    season_id        INTEGER   NOT NULL REFERENCES seasons(id),
    club_id          INTEGER   NOT NULL REFERENCES clubs(id),
    ea_urn           INTEGER   NOT NULL,
    athlete_name     VARCHAR   NOT NULL,
    date_of_birth    DATE      NOT NULL,
    ea_age_category  VARCHAR   NOT NULL,
    is_junior        BOOLEAN   NOT NULL,
    amount_pence     INTEGER   NOT NULL,
    race_number      INTEGER,
    created_at       TIMESTAMP DEFAULT current_timestamp,
    UNIQUE (season_id, club_id, ea_urn)
);

CREATE INDEX IF NOT EXISTS idx_athlete_entries_batch
    ON athlete_entries (batch_id);
CREATE INDEX IF NOT EXISTS idx_athlete_entries_season_club
    ON athlete_entries (season_id, club_id);
```
