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
