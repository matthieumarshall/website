CREATE SEQUENCE IF NOT EXISTS user_id_seq START 1;

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER  DEFAULT nextval('user_id_seq') PRIMARY KEY,
    username        VARCHAR  UNIQUE NOT NULL,
    hashed_password VARCHAR  NOT NULL,
    role            VARCHAR  NOT NULL DEFAULT 'content_creator',
    created_at      TIMESTAMP DEFAULT current_timestamp
);
