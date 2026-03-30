CREATE SEQUENCE IF NOT EXISTS season_id_seq START 1;

CREATE TABLE IF NOT EXISTS seasons (
    id         INTEGER   DEFAULT nextval('season_id_seq') PRIMARY KEY,
    name       VARCHAR   NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT current_timestamp
);
