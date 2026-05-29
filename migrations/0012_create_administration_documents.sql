CREATE SEQUENCE IF NOT EXISTS administration_section_id_seq START 1;
CREATE SEQUENCE IF NOT EXISTS administration_document_id_seq START 1;

CREATE TABLE IF NOT EXISTS administration_sections (
    id          INTEGER   DEFAULT nextval('administration_section_id_seq') PRIMARY KEY,
    slug        VARCHAR   NOT NULL UNIQUE,
    title       VARCHAR   NOT NULL,
    description VARCHAR   NOT NULL DEFAULT '',
    sort_order  INTEGER   NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS administration_documents (
    id             INTEGER   DEFAULT nextval('administration_document_id_seq') PRIMARY KEY,
    section_id     INTEGER   NOT NULL REFERENCES administration_sections(id),
    display_name   VARCHAR   NOT NULL,
    filename       VARCHAR   NOT NULL,
    file_type      VARCHAR   NOT NULL DEFAULT 'PDF',
    sort_order     INTEGER   NOT NULL DEFAULT 0,
    uploaded_at    TIMESTAMP NOT NULL DEFAULT current_timestamp,
    uploaded_by_id INTEGER   REFERENCES users(id)
);
