CREATE SEQUENCE IF NOT EXISTS entry_batch_id_seq START 1;

CREATE TABLE IF NOT EXISTS entry_batches (
    id                          INTEGER   DEFAULT nextval('entry_batch_id_seq') PRIMARY KEY,
    season_id                   INTEGER   NOT NULL REFERENCES seasons(id),
    club_id                     INTEGER   NOT NULL REFERENCES clubs(id),
    manager_user_id             INTEGER   NOT NULL REFERENCES users(id),
    status                      VARCHAR   NOT NULL DEFAULT 'pending_payment',
    fixtures_remaining_at_entry INTEGER   NOT NULL,
    total_pence                 INTEGER   NOT NULL DEFAULT 0,
    stripe_checkout_session_id  VARCHAR,
    stripe_payment_intent_id    VARCHAR,
    stripe_payment_method       VARCHAR,
    paid_at                     TIMESTAMP,
    created_at                  TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_entry_batches_season_club
    ON entry_batches (season_id, club_id);

CREATE INDEX IF NOT EXISTS idx_entry_batches_stripe_session
    ON entry_batches (stripe_checkout_session_id);
