CREATE SEQUENCE IF NOT EXISTS club_id_seq START 1;

CREATE TABLE IF NOT EXISTS clubs (
    id         INTEGER   DEFAULT nextval('club_id_seq') PRIMARY KEY,
    name       VARCHAR   NOT NULL,
    oxl_code   VARCHAR   NOT NULL UNIQUE,
    ea_club_id VARCHAR   NOT NULL,
    is_active  BOOLEAN   NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT current_timestamp
);
