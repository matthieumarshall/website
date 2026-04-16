-- Individual athlete standings per season and category.
-- Calculated by pyresults IndividualScoreService from race results.
-- is_imported = true rows (historic seasons) are never overwritten by recalculation.
CREATE TABLE IF NOT EXISTS individual_standings (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES seasons(id),
    category VARCHAR NOT NULL,
    position INTEGER NOT NULL,
    athlete_name VARCHAR NOT NULL,
    club VARCHAR,
    total_score INTEGER NOT NULL,
    rounds_competed INTEGER NOT NULL DEFAULT 0,
    -- JSON object mapping fixture_id (as string) to the position scored that round,
    -- e.g. '{"1": 2, "2": 1, "3": 3}'.  Empty rounds are omitted.
    fixture_scores VARCHAR NOT NULL DEFAULT '{}',
    is_imported BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_individual_standings_season_category
    ON individual_standings (season_id, category);

-- Team standings per season and category.
-- Calculated by pyresults TeamScoreService from race results.
CREATE TABLE IF NOT EXISTS team_standings (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES seasons(id),
    category VARCHAR NOT NULL,
    position INTEGER NOT NULL,
    team_name VARCHAR NOT NULL,   -- full label e.g. "Oxford City AC A"
    club VARCHAR,                  -- club without the A/B/C label
    team_label VARCHAR,            -- "A", "B", "C" etc.
    total_score INTEGER NOT NULL,
    rounds_competed INTEGER NOT NULL DEFAULT 0,
    fixture_scores VARCHAR NOT NULL DEFAULT '{}',
    is_imported BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_team_standings_season_category
    ON team_standings (season_id, category);
