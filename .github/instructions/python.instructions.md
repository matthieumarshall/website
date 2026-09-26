---
description: "Use when writing, reviewing, or refactoring Python files. Covers FastAPI route design, dependency injection, DuckDB data access, Pydantic models, error handling, and code style for this project."
applyTo: "**/*.py"
---

# Python Coding Standards

## Style & Formatting

- **Formatter / linter**: `ruff` — enforced by pre-commit. Never disable a rule without a comment explaining why.
- **E402 (import order)**: any non-import statement at module level (including side-effectful calls like `mimetypes.add_type()`) causes all subsequent `import` statements to trigger E402. Place all module-level side-effects **after** the last import.
- All functions and methods must have **type hints** on every parameter and the return type.
- Use `snake_case` for functions and variables, `PascalCase` for classes.
- Maximum line length: 88 characters (ruff default).
- Prefer explicit `return` types over implicit `None`.

## Module Responsibilities (SOLID)

See `src/website/README.md` for the full picture. Layers, from top to bottom
(`import-linter` enforces that each layer only imports the ones below it):

| Package | Owns |
|---------|------|
| `main.py` | `create_app()`: middleware, static mounts, exception handlers, router registration |
| `web/routes/` | One `APIRouter` per area: bind form models, call a service, render with `Renderer.page` |
| `web/` | Dependencies (`deps.py`), CSRF, ACLs (`security.py`), session identity, rendering, error handlers |
| `services/` | Business rules, one class per area; raise `website.errors` exceptions; no FastAPI imports |
| `integrations/` | England Athletics, Stripe, Nominatim adapters behind `Protocol`s |
| `repository/` | SQL only, one module per domain; `db` is always the first argument; returns pydantic models |
| `models/` | Pydantic models (read models, form models); no I/O |

Never let a route handler contain SQL, validation rules, hashing or direct
file I/O. Delegate to a service.

## FastAPI Routes

```python
# Good: a thin handler with Annotated dependencies and a form model
@router.post("/{club_id}/inline-edit", response_class=HTMLResponse)
def clubs_inline_edit(
    request: Request,
    club_id: int,
    form: Annotated[ClubForm, Form()],
    _: RequireStaff,
    _csrf: CsrfProtected,
    clubs: Clubs,
    ui: RendererDep,
) -> HTMLResponse:
    try:
        club = clubs.update(club_id, form)
    except ValidationError as exc:
        return ui.page(request, "_club_row_edit.html", "clubs", status_code=422, ...)
    return ui.page(request, "_club_row.html", "clubs", club=club, is_staff=True)
```

- Declare dependencies with the `Annotated` aliases from `web/deps.py` and
  `web/security.py`. Never open a connection or build a service inside a route.
- HTMX endpoints return a partial template (`_name.html`); full pages extend
  `base.html`. Both must use the same service method.
- Services raise domain errors; `web/handlers.py` maps them to HTTP status codes.

## Dependency Injection & Database

A single shared DuckDB connection is opened in the lifespan handler and
stored on `app.state.db`. `web.deps.get_db` yields a **cursor** per request.
This avoids OS-level file-lock conflicts on Windows while giving each request
an isolated cursor.

- **Always** use parameterised queries. SQL may only be assembled from
  constant fragments (mark those lines `# nosec B608` with a reason).
- Map rows to models with `repository._rows.fetch_one` / `fetch_all`; select
  column aliases that match the model's field names.

## Pydantic Models

- Define every shape as a `pydantic.BaseModel` in `models/<domain>.py`. That
  includes form submissions (`models/forms.py`) and service view models.
- Use `model_config = ConfigDict(frozen=True)` for read models.
- Never return `dict`, `list[dict]` or raw tuples across a layer boundary.

## Error Handling

- Raise `website.errors` exceptions from services, and `HTTPException` only in
  the web layer.
- Catch specific exceptions. Do not use bare `except Exception` (ruff `BLE`),
  unless you are wrapping a third-party call and re-raising a domain error.
- Log errors at `ERROR` level; never log passwords, tokens, or any PII.

## Testing

- `tests/unit/services/`: fast service tests with in-memory DuckDB and fakes
  for the integration `Protocol`s.
- `tests/unit/routes/`: `TestClient` route tests. Override collaborators with
  `app.dependency_overrides[get_x] = ...`; never monkeypatch module globals.
- `tests/unit/test_architecture.py` pins the route table
  (`route_snapshot.json`), checks that templates exist and enforces module size.
- Coverage must stay at or above `fail_under` in `.coveragerc`, and changed
  lines in a PR need 90% coverage (`diff-cover`).

## Security & GDPR

| Concern | Rule |
|---------|------|
| **Secrets** | Never hardcode fallback secrets as recognisable strings. In production (`PRODUCTION=true`), fail fast if `SECRET_KEY` is unset. |
| **Session cookie** | `SessionMiddleware` must set `https_only=settings.is_production` and `same_site="lax"`. Never hard-code `https_only=False` in production. |
| **CSRF** | All state-changing POST routes must declare `_csrf: CsrfProtected` (`web/csrf.py`). `Renderer.page` injects the token into every template. |
| **Security headers** | All responses must pass through `SecurityHeadersMiddleware` (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, HSTS in prod). |
| **Privacy** | The site must expose a `/privacy-policy` route. Any new data collection must be documented there and in this file. |
| **Open redirect** | Never redirect to a user-supplied or header-supplied URL without validating it is a path-relative URL on our own origin (use `website.richtext.safe_referer_path`). |
| **PII logging** | Never log passwords, session tokens, or IP addresses. |
| **Bandit** | All Python code must pass `bandit -r src/ -ll`. Add `# nosec B<code>` with an explanation only when a finding is a confirmed false positive. |
