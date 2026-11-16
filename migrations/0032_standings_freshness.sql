-- Calculated standings are valid only for the input and scoring version recorded here.
CREATE TABLE IF NOT EXISTS standings_calculation_state (
    season_id INTEGER PRIMARY KEY REFERENCES seasons(id),
    scoring_version INTEGER NOT NULL,
    input_fingerprint VARCHAR NOT NULL
);

-- Correct the known wording without overwriting other edits to the live manual.
UPDATE static_pages SET content = replace(content,
    'first 3 athletes (juniors and women) or first 7 athletes (men)',
    'first 3 athletes (juniors), first 4 athletes (women) or first 7 athletes (men)')
WHERE slug = 'rules-and-constitution';
