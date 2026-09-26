"""Jinja2 page rendering with the context every template expects."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from website.content import SIDEBAR_ITEMS
from website.models import UserRole
from website.richtext import post_summary
from website.web.csrf import get_csrf_token
from website.web.identity import get_current_user

COOKIE_NOTICE_COOKIE = "cookie_notice_dismissed"


def fields(model: BaseModel) -> dict[str, object]:
    """Return a model's fields as template variables (values are not copied)."""
    return dict(model)


class Renderer:
    """Renders full pages and HTMX fragments from the ``templates`` directory."""

    def __init__(self, templates_dir: Path, stripe_publishable_key: str = "") -> None:
        """Create the Jinja environment and register filters and globals."""
        self.templates = Jinja2Templates(directory=str(templates_dir))
        env = self.templates.env
        env.filters["fromjson"] = json.loads
        env.filters["post_summary"] = post_summary
        # Jinja types its globals narrowly; any value is allowed at runtime.
        cast("dict[str, object]", env.globals)["STRIPE_PUBLISHABLE_KEY"] = (
            stripe_publishable_key
        )

    @staticmethod
    def context(
        request: Request, current_page: str, extra: Mapping[str, object]
    ) -> dict[str, object]:
        """Return the base context (user, navigation, CSRF token) plus *extra*."""
        return {
            "current_user": get_current_user(request),
            "current_page": current_page,
            "sidebar_items": SIDEBAR_ITEMS,
            "csrf_token": get_csrf_token(request),
            "show_cookie_notice": not request.cookies.get(COOKIE_NOTICE_COOKIE),
            "UserRole": UserRole,
            **extra,
        }

    def page(
        self,
        request: Request,
        template: str,
        current_page: str,
        *,
        view: BaseModel | None = None,
        status_code: int = 200,
        **extra: object,
    ) -> HTMLResponse:
        """Render *template* (a full page or an HTMX fragment) as a response.

        The fields of *view* (a service's view model) and *extra* become
        template variables alongside the base context.
        """
        variables = {**fields(view), **extra} if view is not None else extra
        return self.templates.TemplateResponse(
            request,
            template,
            self.context(request, current_page, variables),
            status_code=status_code,
        )

    @staticmethod
    def is_htmx(request: Request) -> bool:
        """Return True if the request was made by HTMX (not a full page load)."""
        return "HX-Request" in request.headers
