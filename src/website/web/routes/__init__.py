"""All HTTP routers, in registration order.

Order matters where a literal path would otherwise be captured by a path
parameter: ``administration`` (``/administration/manage``) must come before
``pages`` (``/administration/{slug}``).
"""

from fastapi import APIRouter

from website.web.routes import (
    administration,
    auth,
    clubs,
    divisions,
    entries,
    fixtures,
    links,
    news,
    pages,
    public,
    results,
    standings,
    webhooks,
    winners,
)
from website.web.routes.admin import club_managers as admin_club_managers
from website.web.routes.admin import clubs as admin_clubs
from website.web.routes.admin import entries as admin_entries
from website.web.routes.admin import links as admin_links
from website.web.routes.admin import public_content as admin_public_content

ROUTERS: tuple[APIRouter, ...] = (
    public.router,
    auth.router,
    results.router,
    entries.router,
    standings.router,
    clubs.router,
    links.router,
    divisions.router,
    winners.router,
    administration.router,
    pages.router,
    fixtures.router,
    news.router,
    admin_entries.router,
    admin_clubs.router,
    admin_links.router,
    admin_public_content.router,
    admin_club_managers.router,
    webhooks.router,
)
