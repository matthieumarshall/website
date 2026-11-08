# Website

A server-rendered website with FastAPI backend, DuckDB persistence, and HTMX interactivity.

## Stack

- **Backend:** FastAPI (Python)
- **Database:** DuckDB (persistent file-based)
- **Auth:** Session cookies (Starlette SessionMiddleware + passlib/bcrypt)
- **Templating:** Jinja2 (server-side rendered)
- **Frontend:** HTMX + Bootstrap 5 (self-hosted)

## Setup

1. **Install dependencies** ([uv](https://docs.astral.sh/uv/) required)
   ```
   just sync
   ```

   > **Note:** The `just` command runner is required. If you don't have it installed:
   > - **Windows (with WinGet):** `winget install Casey.Just`
   > - **Windows (with Chocolatey):** `choco install just`
   > - **Other platforms:** See [just installation guide](https://github.com/casey/just?tab=readme-ov-file#installation)
   >
   > If you prefer not to install `just`, run `uv sync --all-extras`, `npm install`,
   > `uv run python -m pre_commit install`, and copy `.env.example` to `.env`.

2. **Run migrations** (brings the DuckDB schema up to date)
   ```
   uv run python -m cli.seed_user <username> <password> --role admin
   ```

3. **Run the server**
   ```
   uv run uvicorn website.main:app --reload
   ```

4. **Open your browser** at [http://localhost:8000](http://localhost:8000)

## Seeding Data

To populate the database with sample data:

```powershell
# Create an admin user
uv run python -m cli.seed_user admin admin123 --role admin

# Create a season
uv run python -m cli.seed_season "2026 Season"

# Create a fixture
uv run python -m cli.seed_fixture "2026 Season" "Spring Race" "2026-05-15" "Central Park"

# Seed rules and constitution
uv run python -m cli.seed_rules
```

Or with `just`:
```powershell
just seed-user admin admin123 admin
just seed-season "2026 Season"
just seed-fixture "2026 Season" "Spring Race" "2026-05-15" "Central Park"
just seed-rules
```

Log in at [http://localhost:8000/login](http://localhost:8000/login) with username `admin` and password `admin123`.

## Uploading race results

Staff can add races from the fixture details and upload a CSV for each race from
either the Fixtures or Results page. A valid upload replaces all previous
results for that race; an invalid CSV leaves the existing results unchanged.
Timetable entries are suggestions when naming races, not linked records, so
later timetable edits do not rename races.

## Project Structure

```
src/website/          # FastAPI application (layered; see src/website/README.md)
├── main.py           # create_app() factory: middleware, mounts, routers
├── config.py         # Settings read from the environment
├── db.py             # DuckDB connection and migration runner
├── errors.py         # Domain exceptions (mapped to HTTP in web/handlers.py)
├── web/              # Routers (web/routes/), dependencies, rendering, CSRF, ACLs
├── services/         # Business rules, one service class per area
├── integrations/     # England Athletics, Stripe and geocoding adapters
├── repository/       # SQL data access, one module per domain
├── models/           # Pydantic models (including form models)
├── content.py        # Navigation, admin guides, link categories
├── richtext.py       # HTML sanitising and summaries
└── export.py         # CSV/PDF export

migrations/           # SQL schema migrations (applied in order)
templates/            # Jinja2 HTML templates
├── base.html         # Shared layout with navbar
├── index.html        # Home page
├── login.html        # Login form
└── ...               # Additional pages

static/               # Self-hosted CSS/JS assets
├── bootstrap.min.css
├── bootstrap.bundle.min.js
├── htmx.min.js
├── style.css         # Custom CSS overrides
└── ...               # Feature-specific JS islands

tests/
├── unit/             # pytest unit tests with mocked DB
└── ui/               # Playwright end-to-end tests

data/                 # DuckDB database and uploads (gitignored)
```

## Quality Checks

Every commit runs pre-commit (`just lint` runs it on all files). The hooks are:

| Check | Command | Enforces |
|-------|---------|----------|
| Lint + format | `uv run ruff check .` / `uv run ruff format .` | Style, docstrings, annotations, complexity (`pyproject.toml`) |
| Types | `uv run mypy`, `uv run ty check` | `mypy --strict` with the pydantic plugin on `src/website` |
| Architecture | `uv run lint-imports` | Layering: web → services → repository → models |
| Module size | `uv run python scripts/check_file_length.py src` | No module over 1000 lines (warns over 500) |
| Tests (pre-push) | `uv run pytest tests/unit -x -q` | Unit tests pass before every push (`just test-unit` adds the coverage gate) |

`just check` runs the type, architecture and size checks together. CI also
requires 90% coverage of the lines changed in a pull request (`diff-cover`).
Run `uv run pre-commit install` once to install both the commit and push hooks.

## Contributor Workflow

After cloning, run `just sync`, configure `.env` for local development, and
start the app with `just serve`. The [new machine setup guide](docs/new-machine-setup.md)
covers prerequisites, database setup, and optional Playwright browser setup.

Before submitting a change, run the checks relevant to it:

```powershell
just test-unit     # unit tests with the coverage gate
just test-ui       # browser tests (requires Playwright browsers)
just check         # type, architecture, and module-size checks
just lint          # all pre-commit hooks
```

Use `just test` to run the full test suite. See [src/website/README.md](src/website/README.md)
for the layer boundaries and feature implementation workflow.

## Repository Hygiene

Keep local configuration and runtime data out of commits. `.env`, DuckDB files,
database sidecars, uploads, and generated test artifacts are ignored by Git.
Put only placeholder values in `.env.example`; never copy real credentials into
tracked files. Before committing, `git status --short` should not show local
secrets, databases, or uploaded files.

## License

This project is licensed under the **Business Source License (BSL 1.1)**.

- ✅ **Free for**: non-commercial use, open-source projects, and learning
- ❌ **Not free for**: commercial applications or services
- 📅 **Conversion**: After 2 years, this license converts to MIT (fully permissive)

See [LICENSE.md](LICENSE.md) for details. For commercial licensing inquiries, please contact the project owner.
