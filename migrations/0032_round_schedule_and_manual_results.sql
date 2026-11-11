-- A fixture is a round in the public calendar.  Keep the legacy name in the
-- database for compatibility, but give each round a stable season-local number
-- and persist its schedule instead of relying only on the legacy JSON field.
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS round_number INTEGER;

WITH numbered AS (
    SELECT id,
           row_number() OVER (PARTITION BY season_id ORDER BY date, id) AS number
    FROM fixtures
)
UPDATE fixtures
SET round_number = numbered.number
FROM numbered
WHERE fixtures.id = numbered.id
  AND fixtures.round_number IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS fixtures_season_round_number
ON fixtures (season_id, round_number);

CREATE SEQUENCE IF NOT EXISTS timetable_item_id_seq START 1;

CREATE TABLE IF NOT EXISTS timetable_items (
    id            INTEGER DEFAULT nextval('timetable_item_id_seq') PRIMARY KEY,
    fixture_id    INTEGER NOT NULL REFERENCES fixtures(id),
    race_id       INTEGER REFERENCES races(id),
    time          VARCHAR NOT NULL DEFAULT '',
    event         VARCHAR NOT NULL DEFAULT '',
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS timetable_items_fixture_order
ON timetable_items (fixture_id, display_order);

-- Preserve staff corrections across subsequent imports.  Imported rows use a
-- source key so a future import can update only rows that have not been locked.
ALTER TABLE results ADD COLUMN IF NOT EXISTS source VARCHAR DEFAULT 'imported';
ALTER TABLE results ADD COLUMN IF NOT EXISTS is_locked BOOLEAN DEFAULT false;
ALTER TABLE results ADD COLUMN IF NOT EXISTS external_key VARCHAR;

-- Preserve the legacy timetable before switching reads to relational rows.
INSERT INTO timetable_items (fixture_id, event, time, display_order)
SELECT f.id, COALESCE(json_extract_string(j.value, '$.event'), ''),
       COALESCE(json_extract_string(j.value, '$.time'), ''), CAST(j.key AS INTEGER)
FROM fixtures f, json_each(CASE WHEN json_valid(f.timetable) THEN f.timetable ELSE '[]' END) j
WHERE json_type(j.value) = 'OBJECT'
  AND NOT EXISTS (SELECT 1 FROM timetable_items existing WHERE existing.fixture_id = f.id);
