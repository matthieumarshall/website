-- Create table to track athlete entry allocations per club per season
CREATE TABLE club_allocations (
    season_id INTEGER NOT NULL,
    club_id INTEGER NOT NULL,
    allocated_slots INTEGER NOT NULL CHECK (allocated_slots > 0),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season_id, club_id),
    FOREIGN KEY (season_id) REFERENCES seasons(id),
    FOREIGN KEY (club_id) REFERENCES clubs(id)
);

CREATE INDEX idx_club_allocations_season ON club_allocations(season_id);
CREATE INDEX idx_club_allocations_club ON club_allocations(club_id);
