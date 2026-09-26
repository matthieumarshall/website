"""AccountService: authentication and club manager administration."""

import duckdb
import pytest

from website import repository
from website.errors import ConflictError, ForbiddenError, ValidationError
from website.models import CurrentUser, UserRole
from website.models.forms import ClubManagerForm
from website.passwords import hash_password
from website.services.accounts import AccountService

_PASSWORD = "a-long-enough-password"


def _club_id(db: duckdb.DuckDBPyConnection) -> int:
    return repository.create_club(db, name="Club", oxl_code="CLB", ea_club_id="9").id


class TestAuthenticate:
    def test_valid_and_invalid_credentials(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        repository.create_user(test_db, "alice", hash_password("pw"), UserRole.admin)
        accounts = AccountService(test_db)
        user = accounts.authenticate("alice", "pw")
        assert user is not None
        assert user.username == "alice"
        assert accounts.authenticate("alice", "wrong") is None
        assert accounts.authenticate("nobody", "pw") is None


class TestClubManagers:
    def test_create_and_toggle(self, test_db: duckdb.DuckDBPyConnection) -> None:
        accounts = AccountService(test_db)
        accounts.create_club_manager(
            ClubManagerForm(
                username=" mgr ",
                email="mgr@example.com",
                password=_PASSWORD,
                club_id=_club_id(test_db),
            )
        )
        (listing,) = accounts.list_club_managers()
        assert listing.username == "mgr"
        assert listing.email == "mgr@example.com"
        assert listing.is_active is True
        accounts.toggle_club_manager(listing.manager_id)
        assert accounts.list_club_managers()[0].is_active is False

    @pytest.mark.parametrize(
        ("username", "password", "message"),
        [
            ("", _PASSWORD, "required"),
            ("mgr", "short", "at least 12"),
        ],
    )
    def test_rejects_invalid_input(
        self,
        test_db: duckdb.DuckDBPyConnection,
        username: str,
        password: str,
        message: str,
    ) -> None:
        form = ClubManagerForm(
            username=username, password=password, club_id=_club_id(test_db)
        )
        with pytest.raises(ValidationError, match=message):
            AccountService(test_db).create_club_manager(form)

    def test_rejects_unknown_club(self, test_db: duckdb.DuckDBPyConnection) -> None:
        form = ClubManagerForm(username="mgr", password=_PASSWORD, club_id=404)
        with pytest.raises(ValidationError, match="Invalid club"):
            AccountService(test_db).create_club_manager(form)

    def test_rejects_duplicate_username(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        repository.create_user(test_db, "taken", "hash", UserRole.admin)
        form = ClubManagerForm(
            username="taken", password=_PASSWORD, club_id=_club_id(test_db)
        )
        with pytest.raises(ConflictError):
            AccountService(test_db).create_club_manager(form)


class TestActiveClubManager:
    def test_requires_an_active_club_manager(
        self, test_db: duckdb.DuckDBPyConnection
    ) -> None:
        accounts = AccountService(test_db)
        with pytest.raises(ForbiddenError):
            accounts.active_club_manager(None)
        with pytest.raises(ForbiddenError):
            accounts.active_club_manager(CurrentUser(id=1, username="a", role="admin"))

        accounts.create_club_manager(
            ClubManagerForm(
                username="mgr", password=_PASSWORD, club_id=_club_id(test_db)
            )
        )
        (listing,) = accounts.list_club_managers()
        manager_user = CurrentUser(
            id=listing.user_id, username="mgr", role=UserRole.club_manager.value
        )
        assert accounts.active_club_manager(manager_user).club_name == "Club"

        accounts.toggle_club_manager(listing.manager_id)
        with pytest.raises(ForbiddenError, match="inactive"):
            accounts.active_club_manager(manager_user)
