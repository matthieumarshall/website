CREATE SEQUENCE IF NOT EXISTS fixture_document_id_seq START 1;

CREATE TABLE IF NOT EXISTS fixture_documents (
    id             INTEGER   DEFAULT nextval('fixture_document_id_seq') PRIMARY KEY,
    fixture_id     INTEGER   NOT NULL REFERENCES fixtures(id),
    doc_type       VARCHAR   NOT NULL
        CHECK (doc_type IN ('event_licence', 'risk_assessment', 'medical_assessment')),
    filename       VARCHAR   NOT NULL,
    original_name  VARCHAR   NOT NULL,
    file_type      VARCHAR   NOT NULL,
    size_bytes     INTEGER   NOT NULL,
    uploaded_at    TIMESTAMP NOT NULL DEFAULT current_timestamp,
    uploaded_by_id INTEGER   REFERENCES users(id),
    UNIQUE (fixture_id, doc_type)
);
