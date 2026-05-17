-- Store the path of the original results PDF (relative to
-- data/original_website/files/results/) so users can download the source
-- document even when the parser cannot fully extract the results.
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS source_pdf VARCHAR;
