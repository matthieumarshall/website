CREATE SEQUENCE IF NOT EXISTS static_page_id_seq START 1;

CREATE TABLE IF NOT EXISTS static_pages (
    id            INTEGER   DEFAULT nextval('static_page_id_seq') PRIMARY KEY,
    slug          VARCHAR   NOT NULL UNIQUE,
    content       TEXT      NOT NULL DEFAULT '',
    updated_at    TIMESTAMP DEFAULT current_timestamp,
    updated_by_id INTEGER   REFERENCES users(id)
);
