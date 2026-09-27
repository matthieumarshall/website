"""Raw form submissions, bound by FastAPI via ``Annotated[Form, Form()]``.

Field names mirror the HTML form inputs.  Checkbox fields are booleans:
browsers send ``"on"`` when ticked and omit the field otherwise.  Values are
kept as submitted; services own normalisation and business validation.
"""

from pydantic import BaseModel, ConfigDict


class _Form(BaseModel):
    model_config = ConfigDict(extra="ignore")


class LoginForm(_Form):
    """Credentials posted from the login page."""

    username: str
    password: str
    next_path: str = "/news"


class PostForm(_Form):
    """A news post create or edit submission."""

    title: str
    content: str


class RichTextForm(_Form):
    """Rich-text content for an editable static page."""

    content: str


class SeasonForm(_Form):
    """A new season submission."""

    name: str


class FixtureForm(_Form):
    """A fixture create or edit submission."""

    title: str
    date: str
    location_name: str
    address: str
    timetable_json: str = "[]"
    travel_instructions: str = ""
    what3words_word1: str = ""
    what3words_word2: str = ""
    what3words_word3: str = ""


class FixtureCopyForm(FixtureForm):
    """A fixture copied into a (possibly different) season."""

    season_id: int


class ClubForm(_Form):
    """A club create or edit submission."""

    name: str
    oxl_code: str
    ea_club_id: str
    opentrack_code: str = ""
    website_url: str = ""
    is_oxfordshire_member: bool = False
    is_active: bool = False


class AdminClubCreateForm(ClubForm):
    """The admin "new club" form, where membership defaults to ticked."""

    is_oxfordshire_member: bool = True


class LinkForm(_Form):
    """An external link create or edit submission."""

    title: str
    url: str
    category: str
    description: str = ""
    sort_order: int = 0
    is_active: bool = False


class DivisionAssignForm(_Form):
    """Assign a club to a division."""

    season_id: int
    club_id: int
    gender: str
    division: int


class DivisionMoveForm(_Form):
    """Move an existing assignment to another division."""

    division: int
    season_id: int


class SeasonScopeForm(_Form):
    """A form that only identifies the season being edited."""

    season_id: int


class WinnerOverrideForm(_Form):
    """A winner override create or edit submission."""

    season_id: int
    winner_type: str
    category: str
    winner_name: str
    club: str = ""
    total_score: str = ""
    note: str = ""
    mode: str


class AdministrationSectionForm(_Form):
    """A new administration section."""

    title: str
    description: str = ""
    slug: str


class EntryConfigForm(_Form):
    """Season entry settings; prices are entered in pounds."""

    entries_open: bool = False
    ea_reference_date: str
    total_fixtures: int
    junior_pence_per_fixture_display: float = 0.0
    adult_pence_per_fixture_display: float = 0.0


class ClubManagerForm(_Form):
    """A new club manager account."""

    username: str
    email: str = ""
    password: str
    club_id: int


class EntryBatchForm(_Form):
    """The athletes selected for a new entry batch."""

    ea_urns: list[int] = []
