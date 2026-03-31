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
   uv sync
   just sync
   ```

2. **Run migrations** (brings the DuckDB schema up to date)
   ```
   uv run python -m website.seed_user <username> <password>
   ```

3. **Run the server**
   ```
   uv run uvicorn website.main:app --reload
   ```

4. **Open your browser** at [http://localhost:8000](http://localhost:8000)

## Project Structure

```
src/website/          # FastAPI application
├── __init__.py
├── main.py           # FastAPI app and route wiring
├── database.py       # DuckDB connection setup
├── auth.py           # Password hashing/verification
├── identity.py       # Session and principal retrieval
├── models.py         # Pydantic schemas
├── repository.py     # Data access layer
├── helpers.py        # Shared request utilities
└── export.py         # Export functionality

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

## License

This project is licensed under the **Business Source License (BSL 1.1)**.

- ✅ **Free for**: non-commercial use, open-source projects, and learning
- ❌ **Not free for**: commercial applications or services
- 📅 **Conversion**: After 2 years, this license converts to MIT (fully permissive)

See [LICENSE.md](LICENSE.md) for details. For commercial licensing inquiries, please contact the project owner.
