CREATE SEQUENCE IF NOT EXISTS fixture_id_seq START 1;

CREATE TABLE IF NOT EXISTS fixtures (
    id                  INTEGER   DEFAULT nextval('fixture_id_seq') PRIMARY KEY,
    season_id           INTEGER   NOT NULL REFERENCES seasons(id),
    title               VARCHAR   NOT NULL,
    date                DATE      NOT NULL,
    location_name       VARCHAR   NOT NULL,
    address             VARCHAR   NOT NULL,
    timetable           VARCHAR   NOT NULL DEFAULT '[]',
    travel_instructions TEXT      NOT NULL DEFAULT '',
    created_at          TIMESTAMP DEFAULT current_timestamp
);
