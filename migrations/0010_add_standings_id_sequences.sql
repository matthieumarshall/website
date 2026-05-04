-- Add auto-increment sequences for the standings table id columns.
-- Without these, INSERT statements that omit id get a NOT NULL constraint error.
CREATE SEQUENCE IF NOT EXISTS individual_standings_id_seq START 1;
ALTER TABLE individual_standings ALTER COLUMN id SET DEFAULT nextval('individual_standings_id_seq');

CREATE SEQUENCE IF NOT EXISTS team_standings_id_seq START 1;
ALTER TABLE team_standings ALTER COLUMN id SET DEFAULT nextval('team_standings_id_seq');
