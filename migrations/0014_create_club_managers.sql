CREATE SEQUENCE IF NOT EXISTS club_manager_id_seq START 1;

CREATE TABLE IF NOT EXISTS club_managers (
    id         INTEGER   DEFAULT nextval('club_manager_id_seq') PRIMARY KEY,
    user_id    INTEGER   NOT NULL UNIQUE REFERENCES users(id),
    club_id    INTEGER   NOT NULL REFERENCES clubs(id),
    is_active  BOOLEAN   NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT current_timestamp
);
