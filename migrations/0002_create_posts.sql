CREATE SEQUENCE IF NOT EXISTS post_id_seq START 1;

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER   DEFAULT nextval('post_id_seq') PRIMARY KEY,
    title      VARCHAR   NOT NULL,
    content    TEXT      NOT NULL,
    author_id  INTEGER   NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp,
    published  BOOLEAN   DEFAULT true
);
