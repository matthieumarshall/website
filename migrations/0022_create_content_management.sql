CREATE SEQUENCE IF NOT EXISTS external_link_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS division_assignment_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS winner_override_id_seq START 1;

CREATE TABLE IF NOT EXISTS external_links (
    id          INTEGER DEFAULT nextval('external_link_id_seq') PRIMARY KEY,
    title       VARCHAR NOT NULL,
    url         VARCHAR NOT NULL,
    category    VARCHAR NOT NULL CHECK (category IN ('national', 'clubs', 'leagues')),
    description VARCHAR,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    updated_at  TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_external_links_category_order
    ON external_links (category, sort_order, title);

CREATE TABLE IF NOT EXISTS division_assignments (
    id          INTEGER DEFAULT nextval('division_assignment_id_seq') PRIMARY KEY,
    season_id   INTEGER NOT NULL REFERENCES seasons(id),
    club_id     INTEGER NOT NULL REFERENCES clubs(id),
    gender      VARCHAR NOT NULL CHECK (gender IN ('women', 'men')),
    division    INTEGER NOT NULL CHECK (division BETWEEN 1 AND 3),
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    updated_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE (season_id, club_id, gender)
);

CREATE INDEX IF NOT EXISTS idx_division_assignments_season_gender
    ON division_assignments (season_id, gender, division);

CREATE TABLE IF NOT EXISTS winner_overrides (
    id            INTEGER DEFAULT nextval('winner_override_id_seq') PRIMARY KEY,
    season_id     INTEGER NOT NULL REFERENCES seasons(id),
    winner_type   VARCHAR NOT NULL CHECK (winner_type IN ('individual', 'team')),
    category      VARCHAR NOT NULL,
    winner_name   VARCHAR NOT NULL,
    club          VARCHAR,
    total_score   INTEGER,
    note          VARCHAR,
    mode          VARCHAR NOT NULL DEFAULT 'replace'
                  CHECK (mode IN ('replace', 'supplement')),
    is_active     BOOLEAN NOT NULL DEFAULT true,
    updated_by_id INTEGER REFERENCES users(id),
    created_at    TIMESTAMP NOT NULL DEFAULT current_timestamp,
    updated_at    TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_winner_overrides_lookup
    ON winner_overrides (season_id, winner_type, category, is_active);
