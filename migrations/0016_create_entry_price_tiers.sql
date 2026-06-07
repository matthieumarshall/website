CREATE SEQUENCE IF NOT EXISTS entry_price_tier_id_seq START 1;

CREATE TABLE IF NOT EXISTS entry_price_tiers (
    id                 INTEGER   DEFAULT nextval('entry_price_tier_id_seq') PRIMARY KEY,
    season_id          INTEGER   NOT NULL REFERENCES seasons(id),
    fixtures_remaining INTEGER   NOT NULL CHECK (fixtures_remaining >= 1),
    junior_pence       INTEGER   NOT NULL CHECK (junior_pence >= 0),
    adult_pence        INTEGER   NOT NULL CHECK (adult_pence >= 0),
    updated_at         TIMESTAMP NOT NULL DEFAULT current_timestamp,
    UNIQUE (season_id, fixtures_remaining)
);
