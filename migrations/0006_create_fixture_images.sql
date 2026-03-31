CREATE SEQUENCE IF NOT EXISTS fixture_image_id_seq START 1;

CREATE TABLE IF NOT EXISTS fixture_images (
    id          INTEGER   DEFAULT nextval('fixture_image_id_seq') PRIMARY KEY,
    fixture_id  INTEGER   NOT NULL REFERENCES fixtures(id),
    filename    VARCHAR   NOT NULL,
    uploaded_at TIMESTAMP DEFAULT current_timestamp
);
