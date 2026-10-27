-- Fields for external results synchronization (Tempo Events / RaceTec Results).
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS tempo_results_url VARCHAR;
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS auto_sync_enabled BOOLEAN DEFAULT false;
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS auto_sync_until TIMESTAMP;
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS auto_sync_interval_minutes INTEGER DEFAULT 15;
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP;
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS last_sync_attempt_at TIMESTAMP;
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS sync_status VARCHAR DEFAULT 'idle';
ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS sync_error TEXT;
