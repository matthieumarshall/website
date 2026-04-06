# Keep command behavior consistent on Windows.
set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# Sync Python and Node dependencies used by this project.
sync:
    uv sync --all-extras
    npm install
    uv run python -m pre_commit install
    if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created .env from .env.example — edit SECRET_KEY before deploying to production." }

# Run Python dependency sync only
sync-python:
    uv sync --all-extras

# Run pre-commit hooks on all files.
lint:
    uv run python -m pre_commit run --all-files

# Start the development server with auto-reload.
serve:
    uv run uvicorn website.main:app --reload --env-file .env

test-ui:
    uv run pytest tests/ui -v

test-unit:
    uv run pytest tests/unit -v --tb=short

test:
    uv run pytest tests/ -v --tb=short
