"""FastAPI dependency providers: database, settings, renderer and services.

Routes depend on these ``Annotated`` aliases rather than constructing
collaborators themselves, so tests can swap any of them through
``app.dependency_overrides``.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict

from website.config import Settings
from website.db import Connection
from website.integrations.england_athletics import (
    AthleteDirectory,
    EnglandAthleticsDirectory,
)
from website.integrations.geocoding import Geocoder, NominatimGeocoder
from website.integrations.stripe_payments import PaymentGateway, StripeGateway
from website.models import ClubManager, CurrentUser
from website.services.accounts import AccountService
from website.services.administration import AdministrationService
from website.services.clubs import ClubService
from website.services.content import PageService, PostService
from website.services.divisions import DivisionService
from website.services.entries import EntryService
from website.services.entry_admin import EntryAdminService
from website.services.fixtures import FixtureService
from website.services.links import LinkService
from website.services.results import ResultsService
from website.services.standings import StandingsService
from website.services.uploads import DOCUMENT_POLICY, IMAGE_POLICY, FileStore
from website.services.winners import WinnerService
from website.web.identity import get_current_user
from website.web.receipts import ReceiptRenderer
from website.web.rendering import Renderer
from website.web.security import Permission, PostResource


def get_db(request: Request) -> Iterator[Connection]:
    """Yield a per-request cursor on the application's shared DuckDB connection.

    Using a cursor() avoids opening a second OS-level file lock per request,
    which would cause 'file being used by another process' errors on Windows.
    """
    cursor = request.app.state.db.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def get_settings(request: Request) -> Settings:
    """Return the application settings."""
    settings: Settings = request.app.state.settings
    return settings


def get_renderer(request: Request) -> Renderer:
    """Return the application's template renderer."""
    renderer: Renderer = request.app.state.renderer
    return renderer


DbDep = Annotated[Connection, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
RendererDep = Annotated[Renderer, Depends(get_renderer)]
CurrentUserDep = Annotated[CurrentUser | None, Depends(get_current_user)]


# -- integrations --------------------------------------------------------------


def get_geocoder() -> Geocoder:
    """Return the address geocoder."""
    return NominatimGeocoder()


def get_athlete_directory() -> AthleteDirectory:
    """Return the England Athletics athlete directory."""
    return EnglandAthleticsDirectory()


def get_payment_gateway() -> PaymentGateway:
    """Return the payment gateway."""
    return StripeGateway()


def get_image_store(settings: SettingsDep) -> FileStore:
    """Return the store for fixture map images."""
    return FileStore(settings.fixture_maps_dir, IMAGE_POLICY)


def get_upload_store(settings: SettingsDep) -> FileStore:
    """Return the store for images embedded in rich-text content."""
    return FileStore(settings.uploads_dir, IMAGE_POLICY)


def get_document_store(settings: SettingsDep) -> FileStore:
    """Return the store for administration documents."""
    return FileStore(settings.admin_docs_dir, DOCUMENT_POLICY)


def get_receipt_renderer(
    renderer: RendererDep, settings: SettingsDep
) -> ReceiptRenderer:
    """Return the receipt HTML/PDF renderer."""
    return ReceiptRenderer(renderer.templates.env, settings.templates_dir)


ImageStoreDep = Annotated[FileStore, Depends(get_image_store)]
UploadStoreDep = Annotated[FileStore, Depends(get_upload_store)]
DocumentStoreDep = Annotated[FileStore, Depends(get_document_store)]
ReceiptRendererDep = Annotated[ReceiptRenderer, Depends(get_receipt_renderer)]


# -- services ------------------------------------------------------------------


def get_account_service(db: DbDep) -> AccountService:
    """Provide an :class:`AccountService`."""
    return AccountService(db)


def get_administration_service(
    db: DbDep, documents: DocumentStoreDep
) -> AdministrationService:
    """Provide an :class:`AdministrationService`."""
    return AdministrationService(db, documents)


def get_club_service(db: DbDep) -> ClubService:
    """Provide a :class:`ClubService`."""
    return ClubService(db)


def get_division_service(db: DbDep) -> DivisionService:
    """Provide a :class:`DivisionService`."""
    return DivisionService(db)


def get_entry_service(
    db: DbDep,
    athletes: Annotated[AthleteDirectory, Depends(get_athlete_directory)],
    payments: Annotated[PaymentGateway, Depends(get_payment_gateway)],
) -> EntryService:
    """Provide an :class:`EntryService`."""
    return EntryService(db, athletes, payments)


def get_entry_admin_service(db: DbDep) -> EntryAdminService:
    """Provide an :class:`EntryAdminService`."""
    return EntryAdminService(db)


def get_fixture_service(
    db: DbDep,
    geocoder: Annotated[Geocoder, Depends(get_geocoder)],
    images: ImageStoreDep,
) -> FixtureService:
    """Provide a :class:`FixtureService`."""
    return FixtureService(db, geocoder, images)


def get_link_service(db: DbDep) -> LinkService:
    """Provide a :class:`LinkService`."""
    return LinkService(db)


def get_page_service(db: DbDep) -> PageService:
    """Provide a :class:`PageService`."""
    return PageService(db)


def get_post_service(db: DbDep) -> PostService:
    """Provide a :class:`PostService`."""
    return PostService(db)


def get_results_service(db: DbDep) -> ResultsService:
    """Provide a :class:`ResultsService`."""
    return ResultsService(db)


def get_standings_service(db: DbDep) -> StandingsService:
    """Provide a :class:`StandingsService`."""
    return StandingsService(db)


def get_winner_service(db: DbDep) -> WinnerService:
    """Provide a :class:`WinnerService`."""
    return WinnerService(db)


Accounts = Annotated[AccountService, Depends(get_account_service)]
Administration = Annotated[AdministrationService, Depends(get_administration_service)]
Clubs = Annotated[ClubService, Depends(get_club_service)]
Divisions = Annotated[DivisionService, Depends(get_division_service)]
Entries = Annotated[EntryService, Depends(get_entry_service)]
EntryAdmin = Annotated[EntryAdminService, Depends(get_entry_admin_service)]
Fixtures = Annotated[FixtureService, Depends(get_fixture_service)]
Links = Annotated[LinkService, Depends(get_link_service)]
Pages = Annotated[PageService, Depends(get_page_service)]
Posts = Annotated[PostService, Depends(get_post_service)]
Results = Annotated[ResultsService, Depends(get_results_service)]
Standings = Annotated[StandingsService, Depends(get_standings_service)]
Winners = Annotated[WinnerService, Depends(get_winner_service)]


# -- access --------------------------------------------------------------------


class ClubManagerSession(BaseModel):
    """A signed-in club manager and the club they look after."""

    model_config = ConfigDict(frozen=True)

    user: CurrentUser
    club_manager: ClubManager


def require_club_manager(
    user: CurrentUserDep, accounts: Accounts
) -> ClubManagerSession:
    """Dependency: require an active club manager session (403 otherwise)."""
    club_manager = accounts.active_club_manager(user)
    assert user is not None  # noqa: S101 — guaranteed by active_club_manager  # nosec B101
    return ClubManagerSession(user=user, club_manager=club_manager)


def get_post_resource(post_id: int, posts: Posts) -> PostResource:
    """Dependency: load a post (404 if missing) wrapped for ACL checks."""
    return PostResource(posts.get(post_id))


ClubManagerDep = Annotated[ClubManagerSession, Depends(require_club_manager)]
PostEditor = Annotated[PostResource, Permission("edit", get_post_resource)]
PostDeleter = Annotated[PostResource, Permission("delete", get_post_resource)]
