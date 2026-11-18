"""Track which results and scoring rules produced calculated standings."""

import hashlib

from website.db import Connection

# Increment whenever a scoring or eligibility rule changes.
SCORING_VERSION = 2


def input_fingerprint(db: Connection, season_id: int) -> str:
    """Fingerprint fixtures, races and all scoring inputs, in stable order."""
    rows = db.execute(
        "SELECT s.name, f.id, f.date, r.id, r.name, x.id, x.position, x.race_number, "
        "x.athlete_name, x.time, x.category, x.gender, x.club "
        "FROM fixtures f JOIN seasons s ON s.id=f.season_id "
        "LEFT JOIN races r ON r.fixture_id=f.id "
        "LEFT JOIN results x ON x.race_id=r.id WHERE f.season_id=? "
        "ORDER BY f.id, r.id, x.id",
        [season_id],
    ).fetchall()
    clubs = db.execute("SELECT id, name FROM clubs ORDER BY id").fetchall()
    aliases = db.execute(
        "SELECT club_id, name FROM club_aliases ORDER BY club_id, name"
    ).fetchall()
    return hashlib.sha256(repr((rows, clubs, aliases)).encode("utf-8")).hexdigest()


def calculated_standings_stale(db: Connection, season_id: int) -> bool:
    """Old or changed calculated rows need recalculation; imported rows are separate."""
    has_rows = db.execute(
        "SELECT EXISTS (SELECT 1 FROM individual_standings "
        "WHERE season_id=? AND NOT is_imported) "
        "OR EXISTS (SELECT 1 FROM team_standings "
        "WHERE season_id=? AND NOT is_imported)",
        [season_id, season_id],
    ).fetchone()
    if not has_rows or not has_rows[0]:
        return False
    state = db.execute(
        "SELECT scoring_version, input_fingerprint FROM standings_calculation_state "
        "WHERE season_id=?",
        [season_id],
    ).fetchone()
    return state is None or state != (SCORING_VERSION, input_fingerprint(db, season_id))


def record_calculation(db: Connection, season_id: int, fingerprint: str) -> None:
    """Record successful calculation inputs in the caller's transaction."""
    db.execute("DELETE FROM standings_calculation_state WHERE season_id=?", [season_id])
    db.execute(
        "INSERT INTO standings_calculation_state VALUES (?, ?, ?)",
        [season_id, SCORING_VERSION, fingerprint],
    )
