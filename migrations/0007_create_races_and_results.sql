CREATE SEQUENCE IF NOT EXISTS race_id_seq START 1;

CREATE TABLE IF NOT EXISTS races (
    id           INTEGER   DEFAULT nextval('race_id_seq') PRIMARY KEY,
    fixture_id   INTEGER   NOT NULL REFERENCES fixtures(id),
    name         VARCHAR   NOT NULL,
    display_order INTEGER  NOT NULL DEFAULT 0,
    created_at   TIMESTAMP DEFAULT current_timestamp
);

CREATE SEQUENCE IF NOT EXISTS result_id_seq START 1;

CREATE TABLE IF NOT EXISTS results (
    id                INTEGER   DEFAULT nextval('result_id_seq') PRIMARY KEY,
    race_id           INTEGER   NOT NULL REFERENCES races(id),
    position          INTEGER   NOT NULL,
    race_number       INTEGER,
    athlete_name      VARCHAR   NOT NULL,
    time              VARCHAR   NOT NULL,
    category          VARCHAR   NOT NULL,
    category_position INTEGER,
    gender            VARCHAR   NOT NULL,
    gender_position   INTEGER,
    club              VARCHAR
);
