"""Division rankings do not modify the stored scoring rows."""

import pytest

from website.models import TeamRoundResult, TeamStanding
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


@pytest.mark.parametrize(
    ("result_name", "assigned_name"),
    [
        ("Abingdon AC", "Abingdon Athletics Club"),
        ("Banbury harriers AC", "Banbury Harriers Athletic Club"),
        ("Headington RR", "Headington Road Runners"),
        ("Highworth RC", "Highworth Running Club"),
        ("Radley Athletic Club", "Radley AC"),
        ("Team Kennet Tri", "Team Kennet Triathlon & AC"),
    ],
)
def test_result_club_aliases_use_gender_and_season_assignments(
    test_db, result_name, assigned_name
):
    test_db.execute("INSERT INTO seasons (id, name) VALUES (991, 'Division test')")
    test_db.execute(
        "INSERT INTO clubs (id, name, oxl_code) VALUES (991, ?, 'TST')",
        [assigned_name],
    )
    test_db.execute(
        "INSERT INTO division_assignments (season_id, club_id, gender, division) "
        "VALUES (991, 991, 'men', 1), (991, 991, 'women', 2)"
    )
    round_result = TeamRoundResult(
        id=1,
        category="Men",
        position=1,
        team_name=result_name + " A",
        club=f"  {result_name.upper()}  ",
        team_label="A",
        fixture_id=1,
        score=10,
        scoring_members=[],
    )
    standing = TeamStanding(
        id=1,
        category="Women",
        position=1,
        team_name=result_name + " A",
        club=f"  {result_name.upper()}  ",
        team_label="A",
        season_id=991,
        total_score=10,
        rounds_competed=1,
        fixture_scores="{}",
        is_imported=False,
    )
    resolved_result = with_divisions(test_db, 991, [round_result])[0]
    resolved_standing = with_divisions(test_db, 991, [standing])[0]
    assert (resolved_result.division, resolved_result.division_position) == (1, 1)
    assert (resolved_standing.division, resolved_standing.division_position) == (2, 1)
    assert resolved_result.club == round_result.club
    assert resolved_standing.club == standing.club


def test_exact_assignment_takes_precedence_over_alias(test_db):
    test_db.execute("INSERT INTO seasons (id, name) VALUES (991, 'Division test')")
    test_db.execute(
        "INSERT INTO clubs (id, name, oxl_code) VALUES "
        "(991, 'Headington RR', 'HRR'), (992, 'Headington Road Runners', 'HEA')"
    )
    test_db.execute(
        "INSERT INTO division_assignments (season_id, club_id, gender, division) "
        "VALUES (991, 991, 'men', 2), (991, 992, 'men', 1)"
    )
    row = TeamRoundResult(
        id=1,
        fixture_id=1,
        category="Men",
        position=1,
        team_name="Headington RR A",
        club="Headington RR",
        team_label="A",
        score=10,
        scoring_members=[],
    )
    assert with_divisions(test_db, 991, [row])[0].division == 2
