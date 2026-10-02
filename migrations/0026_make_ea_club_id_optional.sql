-- Backup dependent tables
CREATE TABLE _bak_athlete_entries AS SELECT * FROM athlete_entries;
CREATE TABLE _bak_entry_batches AS SELECT * FROM entry_batches;
CREATE TABLE _bak_club_allocations AS SELECT * FROM club_allocations;
CREATE TABLE _bak_club_managers AS SELECT * FROM club_managers;
CREATE TABLE _bak_division_assignments AS SELECT * FROM division_assignments;

-- Drop dependent tables in dependency order
DROP TABLE athlete_entries CASCADE;
DROP TABLE entry_batches CASCADE;
DROP TABLE club_allocations CASCADE;
DROP TABLE club_managers CASCADE;
DROP TABLE division_assignments CASCADE;

-- Make ea_club_id nullable on clubs
ALTER TABLE clubs ALTER COLUMN ea_club_id DROP NOT NULL;

-- Recreate club_managers
CREATE TABLE club_managers (
    id         INTEGER   DEFAULT nextval('club_manager_id_seq') PRIMARY KEY,
    user_id    INTEGER   NOT NULL REFERENCES users(id),
    club_id    INTEGER   NOT NULL REFERENCES clubs(id),
    is_active  BOOLEAN   NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT current_timestamp,
    email      VARCHAR,
    UNIQUE (user_id, club_id)
);
INSERT INTO club_managers SELECT * FROM _bak_club_managers;
DROP TABLE _bak_club_managers;

-- Recreate entry_batches
CREATE TABLE entry_batches (
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
INSERT INTO entry_batches SELECT * FROM _bak_entry_batches;
DROP TABLE _bak_entry_batches;
CREATE INDEX IF NOT EXISTS idx_entry_batches_season_club
    ON entry_batches (season_id, club_id);
CREATE INDEX IF NOT EXISTS idx_entry_batches_stripe_session
    ON entry_batches (stripe_checkout_session_id);

-- Recreate athlete_entries
CREATE TABLE athlete_entries (
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
INSERT INTO athlete_entries SELECT * FROM _bak_athlete_entries;
DROP TABLE _bak_athlete_entries;
CREATE INDEX IF NOT EXISTS idx_athlete_entries_batch
    ON athlete_entries (batch_id);
CREATE INDEX IF NOT EXISTS idx_athlete_entries_season_club
    ON athlete_entries (season_id, club_id);

-- Recreate club_allocations
CREATE TABLE club_allocations (
    season_id INTEGER NOT NULL,
    club_id INTEGER NOT NULL,
    allocated_slots INTEGER NOT NULL CHECK (allocated_slots > 0),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season_id, club_id),
    FOREIGN KEY (season_id) REFERENCES seasons(id),
    FOREIGN KEY (club_id) REFERENCES clubs(id)
);
INSERT INTO club_allocations SELECT * FROM _bak_club_allocations;
DROP TABLE _bak_club_allocations;
CREATE INDEX idx_club_allocations_season ON club_allocations(season_id);
CREATE INDEX idx_club_allocations_club ON club_allocations(club_id);

-- Recreate division_assignments
CREATE TABLE division_assignments (
    id          INTEGER DEFAULT nextval('division_assignment_id_seq') PRIMARY KEY,
    season_id   INTEGER NOT NULL REFERENCES seasons(id),
    club_id     INTEGER NOT NULL REFERENCES clubs(id),
    gender      VARCHAR NOT NULL CHECK (gender IN ('women', 'men')),
    division    INTEGER NOT NULL CHECK (division BETWEEN 1 AND 3),
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    updated_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE (season_id, club_id, gender)
);
INSERT INTO division_assignments SELECT * FROM _bak_division_assignments;
DROP TABLE _bak_division_assignments;
CREATE INDEX IF NOT EXISTS idx_division_assignments_season_gender
    ON division_assignments (season_id, gender, division);
