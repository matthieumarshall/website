-- Store an independent Tempo Events / RaceTec results URL for each race.
ALTER TABLE races ADD COLUMN IF NOT EXISTS racetec_url VARCHAR;
