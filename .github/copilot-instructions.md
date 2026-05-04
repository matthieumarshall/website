# Project Guidelines

## Architecture

This is a monorepo containing a **FastAPI** backend and a server-rendered frontend using **HTMX** for interactivity.

```
src/website/          # FastAPI application (Python package)
static/               # CSS and any minimal JS
templates/            # Jinja2 HTML templates
tests/unit/           # pytest unit tests
tests/ui/             # Playwright end-to-end tests
data/                 # DuckDB database and uploads (gitignored)
data/original_website/# Read-only archive of the old PHP website (do not modify)
```

`data/original_website/` contains the old PHP + MySQL website that this project replaces. It is read-only reference material. Use the **migrate-old-website** skill for guidance on what to migrate and what to discard from that directory.

The backend owns all routing, auth, and data access. The frontend is thin: Jinja2 templates + HTMX attributes for dynamic behaviour. Reach for plain JavaScript only when HTMX cannot express the interaction.

## Python & FastAPI

- **Dependency management**: always use `uv`. Add runtime deps with `uv add <pkg>`, dev/test deps with `uv add --dev <pkg>` or `uv add --optional dev <pkg>`.
- **SOLID in practice**:
  - One responsibility per module: `auth.py` for password hashing/verification, `identity.py` for session/user/principal retrieval, `database.py` for DuckDB connection setup, `models.py` for dataclass/Pydantic schemas, `helpers.py` for shared request helpers (CSRF, page context, sanitisation), `main.py` for route wiring only.
  - Depend on abstractions: pass a `duckdb.DuckDBPyConnection` via `Depends(get_db)`, not global state.
  - Prefer small, focused functions over large route handlers; extract business logic out of route functions.
- **Type hints** on all function signatures.
- **Linting / formatting**: `ruff` (enforced by pre-commit). Do not disable rules without a comment explaining why.
- **No magic globals**: configuration comes from environment variables, never hardcoded in source.

## Database

The data layer uses **DuckDB** with a persistent database file (`data/app.duckdb`).

- **Connection**: a single shared DuckDB connection is opened at application startup (in the lifespan handler) and stored on `app.state.db`. The `get_db()` dependency in `database.py` yields a **cursor** from that shared connection — this avoids OS-level file-lock conflicts (especially on Windows) while still giving each request an isolated cursor. The cursor is closed in a `try/finally` block after the request completes.
- **Queries**: use DuckDB's parameterised queries (`cur.execute(sql, [params])`) — never f-strings or string concatenation in SQL.
- **Writes**: use `INSERT INTO … VALUES (?, ?)` via DuckDB; keep write helpers in `repository.py`.
- **Schema evolution**: version schema changes with plain SQL migration scripts in `migrations/` (e.g. `0001_add_users.sql`). Apply them in order; do not use Alembic (no SQLAlchemy ORM in this project).
- **Testing**: use an in-memory DuckDB database (`:memory:`) in unit tests; never read or write the real `data/` directory in tests.
- **`data/` hygiene**: `*.duckdb` files and `data/uploads/` are gitignored. Do not commit database files.

## Frontend

This project uses an **Islands Architecture**: pages are server-rendered Jinja2 HTML; JavaScript is introduced only as isolated islands of interactivity where HTMX cannot express the interaction.

- Use **HTMX** attributes (`hx-get`, `hx-post`, `hx-target`, `hx-swap`) for partial page updates before writing custom JS.
- Return HTML fragments from FastAPI endpoints that are intended for HTMX responses.
- Keep `static/style.css` minimal — prefer semantic HTML and browser defaults over heavy styling frameworks.
- JavaScript islands live in `static/<feature>.js`. Each island is self-contained, initialised via a sentinel `<div id="...">` in the template, and communicates back to the server through a hidden form field or `fetch`. Existing islands: `post-editor.js` (Quill), `timetable-editor.js` (custom drag UI).
- Only add a JS file when there is no HTMX alternative (e.g. third-party SDKs like Stripe.js, rich client-side state, drag-and-drop).
- **Mobile-first responsive design**: website must be mobile-friendly and fully functional across all device sizes (mobile, tablet, desktop). Use responsive CSS and test on common mobile devices.
- **WCAG 2.1 Level AA accessibility**: Ensure keyboard navigation, semantic HTML, ARIA labels where needed, sufficient colour contrast (4.5:1), alt text on images, accessible form labels, and screen reader compatibility. Run automated accessibility tests in CI/CD.

## Security

Follow OWASP Top 10 mitigations by default:

| Concern | Convention in this project |
|---|---|
| **Secrets** | All secrets via environment variables. In production (`PRODUCTION=true`) the app will refuse to start if `SECRET_KEY` is unset. Never commit real values. |
| **Passwords** | bcrypt via `auth.py` (`hash_password` / `verify_password`). Never roll a custom scheme. |
| **Session cookies** | `SessionMiddleware` with `https_only=_IS_PRODUCTION` and `same_site="lax"`. The `https_only` flag is env-gated so local dev works over HTTP. |
| **SQL injection** | DuckDB parameterised queries only (`con.execute(sql, [params])`). Never use f-strings or `%`-formatting in SQL. |
| **XSS** | Jinja2 auto-escaping is always on. Avoid `| safe` on user-supplied data. When rendering server-sanitised HTML (e.g. post content cleaned by `nh3`), `| safe` is acceptable — but never apply it to raw user input. |
| **CSRF** | All state-changing POST routes validate a CSRF token via `_validate_csrf(request, form_token)`. Templates receive the token through `_page_context` and render it as `<input type="hidden" name="csrf_token" value="{{ csrf_token }}">`. |
| **Security headers** | `SecurityHeadersMiddleware` in `main.py` sets CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, and (in production) HSTS on every response. |
| **No CDN** | All static assets (Bootstrap CSS/JS) are self-hosted under `static/`. Never add CDN links — they leak user IPs to third parties. |
| **GDPR** | A cookie notice banner is rendered by `base.html` unless dismissed. A `/privacy-policy` route explains data handling. Any new data collection or cookies must be added to `templates/privacy.html` before deployment. See `templates/privacy.html` for the current data inventory. |
| **SAST** | `bandit -r src/ -ll` must pass with zero findings (or documented `# nosec` suppressions). Runs in pre-commit and CI. |
| **Dependencies** | Run `uv run pip-audit` before releases to catch known CVEs. |
| **Input validation** | Validate all user input with Pydantic models or FastAPI's built-in form validation. |

## Testing

- **Unit tests** in `tests/unit/` using `pytest`. Cover auth, models, and route logic with mocked DB sessions.
- **UI tests** in `tests/ui/` using Playwright (`pytest-playwright`).
- Run all tests: `uv run pytest`
- Run with coverage: `uv run pytest --cov=src/website`

## Build & Dev Commands

All common tasks use [Just](https://github.com/casey/just):

```sh
just sync   # install Python + Node deps and set up pre-commit hooks
just lint   # run all pre-commit hooks (ruff, etc.)
```

Start the dev server:
```sh
uv run uvicorn website.main:app --reload
```

## Conventions

- Keep routes thin: validate input → call a service/helper → return a response.
- Avoid adding new dependencies without justification; prefer the standard library or existing project deps.
- Database schema changes go in numbered SQL scripts under `migrations/`; never mutate the schema inside application code at startup.
- Log at `WARNING` or above in production; never log passwords, tokens, or PII.
