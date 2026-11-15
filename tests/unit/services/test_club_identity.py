"""Imported names identify clubs without silently guessing."""

import pytest

from website import repository
from website.errors import ValidationError
from website.models import TeamStanding
from website.models.forms import ClubForm
from website.services.club_identity import ClubIdentityService, ClubRegistry
from website.services.clubs import ClubService
from website.services.standings import StandingsService


def test_alias_management_rejects_conflicts_and_reports_unresolved(test_db):
    club = repository.create_club(test_db, "Headington Road Runners", "HRR")
    other = repository.create_club(test_db, "Other Club", "OTH")
    service = ClubIdentityService(test_db)
    service.add(club.id, "Headington RR")
    resolved = ClubRegistry.load(test_db).resolve("  HEADINGTON   rr ")
    assert resolved is not None and resolved.id == club.id
    with pytest.raises(ValidationError):
        service.add(other.id, "headington rr")
    with pytest.raises(ValidationError):
        service.add(other.id, "Guest")
    with pytest.raises(ValidationError):
        service.add(other.id, "Headington Road Runners")
    alias = service.aliases()[0]
    service.remove(alias.id)
    assert ClubRegistry.load(test_db).resolve("Headington RR") is None


def test_aliases_combine_team_scoring_without_changing_results(test_db):
    club = repository.create_club(test_db, "Headington Road Runners", "HRR")
    ClubIdentityService(test_db).add(club.id, "Headington RR")
    season = repository.create_season(test_db, "2026-27")
    fixture = repository.create_fixture(
        test_db, season.id, "Round 1", "2026-10-04", "Park", "", [], ""
    )
    race = repository.create_race(test_db, fixture.id, "Men")
    for position, name in enumerate(["Headington RR", "Headington Road Runners"], 1):
        repository.create_result(
            test_db,
            race.id,
            position,
            f"Runner {position}",
            "00:10:00",
            "SM",
            "M",
            club=name,
        )
    test_db.execute(
        "INSERT INTO division_assignments (season_id, club_id, gender, division) VALUES (?, ?, 'men', 1)",
        [season.id, club.id],
    )
    StandingsService(test_db).recalculate(season.id)
    teams = repository.list_team_round_results_for_fixture(test_db, fixture.id, "Men")
    assert len(teams) == 1
    assert teams[0].club == "Headington Road Runners"
    assert teams[0].scoring_members[:2] == ["Runner 1 (1)", "Runner 2 (2)"]
    assert {row.club for row in repository.list_results_for_race(test_db, race.id)} == {
        "Headington RR",
        "Headington Road Runners",
    }
    table = StandingsService(test_db).table(season.id, "Men", "team")
    assert len(table.rows) == 1
    assert isinstance(table.rows[0], TeamStanding)
    assert table.rows[0].division == 1


def test_renaming_club_preserves_original_name_as_alias(test_db):
    club = repository.create_club(test_db, "Headington Road Runners", "HRR")
    ClubService(test_db).update(
        club.id, ClubForm(name="Headington Runners", oxl_code="HRR")
    )
    resolved = ClubRegistry.load(test_db).resolve("Headington Road Runners")
    assert resolved is not None and resolved.id == club.id
    assert resolved.name == "Headington Runners"
    ClubService(test_db).update(
        club.id, ClubForm(name="Headington Runners", oxl_code="HRR", ea_club_id="123")
    )
    updated = repository.get_club_by_id(test_db, club.id)
    assert updated is not None and updated.ea_club_id == "123"
