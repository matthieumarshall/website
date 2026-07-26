ALTER TABLE clubs ADD COLUMN IF NOT EXISTS opentrack_code VARCHAR;
ALTER TABLE clubs ADD COLUMN IF NOT EXISTS website_url VARCHAR;
ALTER TABLE clubs ADD COLUMN IF NOT EXISTS is_oxfordshire_member BOOLEAN;
UPDATE clubs SET is_oxfordshire_member = true WHERE is_oxfordshire_member IS NULL;
