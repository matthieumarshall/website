---
description: "Use when writing, reviewing, or refactoring Python files. Covers FastAPI route design, dependency injection, DuckDB data access, Pydantic models, error handling, and code style for this project."
applyTo: "**/*.py"
---

# Python Coding Standards

## Style & Formatting

- **Formatter / linter**: `ruff` — enforced by pre-commit. Never disable a rule without a comment explaining why.
- All functions and methods must have **type hints** on every parameter and the return type.
- Use `snake_case` for functions and variables, `PascalCase` for classes.
- Maximum line length: 88 characters (ruff default).
- Prefer explicit `return` types over implicit `None`.

## Module Responsibilities (SOLID)

| Module | Owns |
|--------|------|
| `main.py` | Route declarations, middleware wiring — no business logic |
| `auth.py` | Password hashing and verification only |
| `identity.py` | Session user retrieval (`get_current_user`) and principal lists (`get_active_principals`) |
| `helpers.py` | Shared request helpers: CSRF token handling, page context builder, HTML sanitisation, safe redirect paths |
| `database.py` | DuckDB connection factory (`get_db`) and migration runner |
| `models.py` | Pydantic schemas and dataclasses — no I/O |
| `repository.py` | Data-access functions (queries/writes) — one per domain entity |

Never let a route handler contain SQL, hashing, or direct file I/O — delegate to the appropriate module.

## FastAPI Routes

```python
# Good — thin handler
@app.post("/login")
def login(form: LoginForm, db: duckdb.DuckDBPyConnection = Depends(get_db)) -> HTMLResponse:
    user = get_user_by_username(db, form.username)
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401)
    ...
```

- One route per handler function; no shared mutable state between requests.
- Always use `Depends(get_db)` — never open a connection directly inside a route.
- Return `HTMLResponse` or an HTML fragment for HTMX endpoints; use `RedirectResponse` for post-login/logout flows.
- Raise `HTTPException` with appropriate status codes rather than returning error dicts.

## Dependency Injection & Database

A single shared DuckDB connection is opened at startup and stored on `app.state.db`. The `get_db()` dependency yields a **cursor** from that connection — this avoids OS-level file-lock conflicts on Windows while giving each request an isolated cursor.

```python
# database.py — cursor factory
def get_db(request: Request) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    cursor = request.app.state.db.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
```

- Every route that touches data must receive a cursor via `Depends(get_db)`.
- **Always** use parameterised queries. Never use f-strings or `%`-formatting in SQL:
  ```python
  # Good
  cur.execute("SELECT * FROM users WHERE username = ?", [username])
  # Bad — SQL injection risk
  cur.execute(f"SELECT * FROM users WHERE username = '{username}'")
  ```
- Writes must use `INSERT INTO … VALUES (?, ?)`; keep them in `repository.py`.

## Pydantic Models

- Define all request/response shapes as `pydantic.BaseModel` subclasses in `models.py`.
- Validate at the boundary — do not re-validate inside service functions that receive already-validated models.
- Use `model_config = ConfigDict(frozen=True)` for read-only value objects.

## Error Handling

- Raise `HTTPException` for client errors (4xx); let FastAPI's exception handler render them.
- Let unexpected exceptions propagate to a global exception handler — do not silence them with bare `except Exception`.
- Log errors at `ERROR` level; never log passwords, tokens, or any PII.

## Testing

- Unit tests live in `tests/unit/`; use `pytest` with an in-memory DuckDB connection (`:memory:`).
- Mock the database connection using `monkeypatch` or `pytest` fixtures — never touch `data/` in tests.
- Aim for one test file per source module (e.g. `test_auth.py` tests `auth.py`).
- Use `fastapi.testclient.TestClient` for synchronous route-level tests.

## Security & GDPR

| Concern | Rule |
|---------|------|
| **Secrets** | Never hardcode fallback secrets as recognisable strings. In production (`PRODUCTION=true`), fail fast if `SECRET_KEY` is unset. |
| **Session cookie** | `SessionMiddleware` must set `https_only=_IS_PRODUCTION` and `same_site="lax"`. Never hard-code `https_only=False` in production. |
| **CSRF** | All state-changing POST routes must call `_validate_csrf(request, form_token)`. The CSRF token is obtained via `_get_csrf_token(request)` and injected via `_page_context`. |
| **Security headers** | All responses must pass through `SecurityHeadersMiddleware` (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, HSTS in prod). |
| **Privacy** | The site must expose a `/privacy-policy` route. Any new data collection must be documented there and in this file. |
| **Open redirect** | Never redirect to a user-supplied or header-supplied URL without validating it is a path-relative URL on our own origin (use `_safe_referer_path`). |
| **PII logging** | Never log passwords, session tokens, or IP addresses. |
| **Bandit** | All Python code must pass `bandit -r src/ -ll`. Add `# nosec B<code>` with an explanation only when a finding is a confirmed false positive. |
