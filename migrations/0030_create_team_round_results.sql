CREATE SEQUENCE IF NOT EXISTS team_round_result_id_seq START 1;

CREATE TABLE IF NOT EXISTS team_round_results (
    id INTEGER DEFAULT nextval('team_round_result_id_seq') PRIMARY KEY,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
    category VARCHAR NOT NULL,
    position INTEGER NOT NULL,
    team_name VARCHAR NOT NULL,
    club VARCHAR,
    team_label VARCHAR,
    score INTEGER NOT NULL,
    scoring_members VARCHAR NOT NULL DEFAULT '[]',
    UNIQUE (fixture_id, category, team_name)
);

CREATE INDEX IF NOT EXISTS idx_team_round_results_fixture_category
    ON team_round_results (fixture_id, category);
