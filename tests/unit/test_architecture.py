"""Structural safety-net tests guarding the public surface of the website.

These tests pin down properties that a refactor must never change silently:

* the set of HTTP routes (method + path) the application exposes, which is
  what the HTMX templates and external links depend on;
* every template name referenced from Python source actually exists;
* no Python module in ``src/website`` grows beyond the agreed size limit.
"""

import json
import re
from pathlib import Path

from fastapi.routing import APIRoute

from website.web.routes import ROUTERS

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _PROJECT_ROOT / "src" / "website"
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"
_SNAPSHOT = Path(__file__).with_name("route_snapshot.json")
_MAX_MODULE_LINES = 1000
_TEMPLATE_LITERAL = re.compile(r"""["']([\w\-/]+\.html)["']""")


def _current_routes() -> list[list[str]]:
    # FastAPI wraps included routers lazily, so read the registered routers.
    return sorted(
        [method, route.path]
        for router in ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    )


def test_route_table_matches_snapshot() -> None:
    expected = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    assert _current_routes() == expected


def test_referenced_templates_exist() -> None:
    missing: list[str] = []
    for module in _SRC_DIR.rglob("*.py"):
        for name in _TEMPLATE_LITERAL.findall(module.read_text(encoding="utf-8")):
            if not (_TEMPLATES_DIR / name).is_file():
                missing.append(f"{module.relative_to(_PROJECT_ROOT)}: {name}")
    assert missing == []


def test_python_modules_stay_below_size_limit() -> None:
    oversized = {
        str(module.relative_to(_PROJECT_ROOT)): line_count
        for module in _SRC_DIR.rglob("*.py")
        if (line_count := len(module.read_text(encoding="utf-8").splitlines()))
        > _MAX_MODULE_LINES
    }
    assert oversized == {}
