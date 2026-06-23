CREATE TABLE IF NOT EXISTS season_entry_config (
    season_id         INTEGER   PRIMARY KEY REFERENCES seasons(id),
    entries_open      BOOLEAN   NOT NULL DEFAULT false,
    ea_reference_date DATE      NOT NULL,
    total_fixtures    INTEGER   NOT NULL DEFAULT 5,
    created_at        TIMESTAMP DEFAULT current_timestamp
);
