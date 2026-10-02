"""ClubService: member club validation, creation, editing, and listing."""

import duckdb
import pytest

from website import repository
from website.errors import ConflictError, ValidationError
from website.models.forms import ClubForm
from website.services.clubs import REQUIRED_FIELDS_MESSAGE, ClubService


def test_create_club_without_ea_club_id(test_db: duckdb.DuckDBPyConnection) -> None:
    service = ClubService(test_db)
    form = ClubForm(
        name="Abingdon AC",
        oxl_code="AAC",
        ea_club_id="",
        is_oxfordshire_member=True,
        is_active=True,
    )
    club = service.create(form)
    assert club.id is not None
    assert club.name == "Abingdon AC"
    assert club.oxl_code == "AAC"
    assert club.ea_club_id is None

    fetched = service.get(club.id)
    assert fetched.ea_club_id is None


def test_create_club_with_ea_club_id(test_db: duckdb.DuckDBPyConnection) -> None:
    service = ClubService(test_db)
    form = ClubForm(
        name="Witney Roadrunners",
        oxl_code="WRR",
        ea_club_id="1234",
        is_oxfordshire_member=True,
        is_active=True,
    )
    club = service.create(form)
    assert club.ea_club_id == "1234"


def test_create_club_requires_name_and_oxl_code(
    test_db: duckdb.DuckDBPyConnection,
) -> None:
    service = ClubService(test_db)
    form = ClubForm(
        name="",
        oxl_code="WRR",
        ea_club_id="",
    )
    with pytest.raises(ValidationError, match=REQUIRED_FIELDS_MESSAGE):
        service.create(form)

    form_no_code = ClubForm(
        name="Witney Roadrunners",
        oxl_code="   ",
        ea_club_id="",
    )
    with pytest.raises(ValidationError, match=REQUIRED_FIELDS_MESSAGE):
        service.create(form_no_code)


def test_create_club_duplicate_oxl_code(test_db: duckdb.DuckDBPyConnection) -> None:
    service = ClubService(test_db)
    form1 = ClubForm(name="Club One", oxl_code="DUP", ea_club_id="")
    service.create(form1)

    form2 = ClubForm(name="Club Two", oxl_code="DUP", ea_club_id="")
    with pytest.raises(ConflictError):
        service.create(form2)


def test_update_club_clears_ea_club_id(test_db: duckdb.DuckDBPyConnection) -> None:
    service = ClubService(test_db)
    club = repository.create_club(
        test_db, name="Banbury Harriers", oxl_code="BH", ea_club_id="5678"
    )
    assert club.ea_club_id == "5678"

    update_form = ClubForm(
        name="Banbury Harriers",
        oxl_code="BH",
        ea_club_id="   ",
        is_active=True,
    )
    updated = service.update(club.id, update_form)
    assert updated.ea_club_id is None
