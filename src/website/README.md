# `website` package architecture

The site is a server-rendered FastAPI + Jinja2 + HTMX application backed by
DuckDB. Code is layered, and each layer may only import the layers below it.
`import-linter` enforces this (see `[tool.importlinter]` in `pyproject.toml`).

```
main.py            create_app(): middleware, static mounts, exception handlers, routers
web/               HTTP only: routers, dependencies, rendering, CSRF, ACLs
services/          business rules; one class per area; raises website.errors.*
integrations/      England Athletics, Stripe, Nominatim, each behind a Protocol
repository/        SQL; one module per domain; returns pydantic models
models/            pydantic data models, including form models (no I/O)
```

Framework-free support modules sit beside the layers: `config.py` (settings
from env), `db.py` (connection and migrations), `errors.py` (domain
exceptions), `content.py` (navigation and guides), `richtext.py` (HTML
sanitising) and `export.py` (CSV and PDF building).

## Rules of thumb

- **Routes are thin.** A handler binds input (a form model via
  `Annotated[XForm, Form()]`), calls one service method and renders the result
  with `Renderer.page(...)`. Handlers contain no SQL, validation or file I/O.
- **HTMX.** Full pages and their HTMX partials keep separate URLs and
  templates (`_name.html` partials). Both call the same service method, so a
  swap always shows what a full reload would. Out-of-band swaps are templates
  too (for example `_link_item_added.html`).
- **Errors.** Services raise `website.errors` exceptions (`NotFoundError`,
  `ValidationError`, `ConflictError`, ...). `web/handlers.py` maps each one to
  an HTTP status. In-page editors catch `ValidationError` to re-render the
  form with a 422 response.
- **Dependencies.** `web/deps.py` provides every collaborator (`DbDep`,
  `Clubs`, `Fixtures`, `ImageStoreDep`, ...). Tests replace them with
  `app.dependency_overrides` instead of monkeypatching module globals.
- **CSRF.** Every state-changing form route declares `_csrf: CsrfProtected`
  after its permission requirement (`_: RequireStaff`, ...).
- **Typing.** Every signature is annotated and `mypy --strict` passes.
  Functions return pydantic models, never bare `dict` or `tuple` rows.
- **Size.** Keep modules under 500 lines. CI fails any module over 1000.

## Adding a feature

1. Add the model(s) in `models/<domain>.py` and the queries in
   `repository/<domain>.py`. Export new functions from `repository/__init__.py`.
2. Put the rules in a service method and cover it with a test in
   `tests/unit/services/`.
3. Add a provider in `web/deps.py` if the service is new, then a thin route in
   `web/routes/<area>.py`, registered in `web/routes/__init__.py`.
4. Add route tests in `tests/unit/routes/`, and regenerate
   `tests/unit/route_snapshot.json` when you intentionally add a route.
