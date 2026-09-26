"""Static site content: navigation, administration guides and link categories."""

from pydantic import BaseModel, ConfigDict


class SidebarItem(BaseModel):
    """A navigation entry, optionally with nested child entries."""

    model_config = ConfigDict(frozen=True)

    name: str
    route: str
    page: str
    children: tuple["SidebarItem", ...] = ()


class AdminGuide(BaseModel):
    """An editable administration guide page."""

    model_config = ConfigDict(frozen=True)

    title: str
    slug: str
    page: str
    route: str
    filename: str


class LinkCategory(BaseModel):
    """A grouping heading for external links."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str


def _guide(title: str, slug: str) -> AdminGuide:
    return AdminGuide(
        title=title,
        slug=slug,
        page=slug.replace("-", "_"),
        route=f"/administration/{slug}",
        filename=f"{slug}.pdf",
    )


ADMIN_GUIDES: dict[str, AdminGuide] = {
    guide.slug: guide
    for guide in (
        _guide("Athlete Registration Guide", "athlete-registration-guide"),
        _guide("Race Directors Guide", "race-directors-guide"),
        _guide("Suppliers List", "suppliers-list"),
        _guide("Team Managers Guide", "team-managers-guide"),
    )
}

SIDEBAR_ITEMS: tuple[SidebarItem, ...] = (
    SidebarItem(name="Home / News", route="/news", page="news"),
    SidebarItem(name="Results", route="/results", page="results"),
    SidebarItem(name="Standings", route="/standings", page="standings"),
    SidebarItem(name="Divisions", route="/divisions", page="divisions"),
    SidebarItem(name="Past Winners", route="/winners", page="winners"),
    SidebarItem(name="Member Clubs", route="/clubs", page="clubs"),
    SidebarItem(
        name="Rules and Constitution",
        route="/rules-and-constitution",
        page="rules_and_constitution",
    ),
    SidebarItem(
        name="Administration",
        route="/administration",
        page="administration",
        children=(
            SidebarItem(
                name="Documents", route="/administration", page="administration"
            ),
            SidebarItem(name="Links", route="/links", page="links"),
            *(
                SidebarItem(name=guide.title, route=guide.route, page=guide.page)
                for guide in ADMIN_GUIDES.values()
            ),
        ),
    ),
    SidebarItem(name="Fixtures", route="/fixtures", page="fixtures"),
)

LINK_CATEGORIES: tuple[LinkCategory, ...] = (
    LinkCategory(key="national", label="National athletics organisations"),
    LinkCategory(key="clubs", label="Member and local clubs"),
    LinkCategory(key="leagues", label="Other cross-country leagues"),
)

LINK_CATEGORY_LABELS: dict[str, str] = {c.key: c.label for c in LINK_CATEGORIES}

RULES_PAGE_SLUG = "rules-and-constitution"
