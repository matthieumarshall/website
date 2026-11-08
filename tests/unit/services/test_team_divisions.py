"""Division rankings do not modify the stored scoring rows."""

from website.models import TeamRoundResult
from website.services.team_divisions import with_divisions


def test_senior_division_ranking_ties_and_juniors(test_db):
    test_db.execute("INSERT INTO seasons (id, name) VALUES (991, 'Division test')")
    test_db.execute(
        "INSERT INTO clubs (id, name, oxl_code) VALUES (991, 'Alpha', 'ALP')"
    )
    test_db.execute(
        "INSERT INTO division_assignments (season_id, club_id, gender, division) VALUES (991, 991, 'men', 1)"
    )

    def row(id, category, club, score):
        return TeamRoundResult(
            id=id,
            fixture_id=1,
            category=category,
            position=id,
            team_name=club,
            club=club,
            team_label=None,
            score=score,
            scoring_members=[],
        )

    original = [
        row(1, "Men", "Alpha", 20),
        row(2, "Men", "Beta", 10),
        row(3, "Men", "Gamma", 10),
        row(4, "U12B", "Alpha", 5),
    ]
    result = {r.id: r for r in with_divisions(test_db, 991, original)}
    assert (result[1].division, result[1].division_position) == (1, 1)
    assert (result[2].division, result[2].division_position) == (3, 1)
    assert (result[3].division, result[3].division_position) == (3, 1)
    assert result[4].division is None
    assert original[0].division is None
