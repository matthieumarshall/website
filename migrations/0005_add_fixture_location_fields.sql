ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS latitude DOUBLE;
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS longitude DOUBLE;
-- Reserved for future What3Words auto-generation; not populated by application yet.
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS what3words VARCHAR;
