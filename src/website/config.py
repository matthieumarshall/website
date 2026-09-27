"""Application settings, read once from the environment at start-up."""

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEV_SECRET_KEY = "dev-only-insecure-key-do-not-use-in-prod"  # noqa: S105  # nosec B105


def _env_flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() == "true"


class Settings(BaseModel):
    """Immutable runtime configuration for the website."""

    model_config = ConfigDict(frozen=True)

    is_production: bool = False
    is_testing: bool = False
    secret_key: str = _DEV_SECRET_KEY
    database_path: str = "data/app.duckdb"
    migrations_dir: Path = Path("migrations")
    templates_dir: Path = Path("templates")
    static_dir: Path = Path("static")
    uploads_dir: Path = Path("data/uploads")
    fixture_maps_dir: Path = Path("data/fixture-maps")
    admin_docs_dir: Path = Path("data/uploads/administration")
    results_pdf_root: Path = _PROJECT_ROOT / "data" / "uploads"
    stripe_publishable_key: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables.

        Raises:
            RuntimeError: If running in production without a ``SECRET_KEY``.
        """
        is_production = _env_flag("PRODUCTION")
        secret_key = os.environ.get("SECRET_KEY", "")
        if is_production and not secret_key:
            raise RuntimeError(
                "SECRET_KEY environment variable must be set in production"
            )
        return cls(
            is_production=is_production,
            is_testing=_env_flag("TESTING"),
            secret_key=secret_key or _DEV_SECRET_KEY,
            database_path=os.environ.get("DATABASE_URL", "data/app.duckdb"),
            stripe_publishable_key=os.environ.get("STRIPE_PUBLISHABLE_KEY", ""),
        )

    def data_directories(self) -> tuple[Path, ...]:
        """Return the writable data directories the app serves files from."""
        return (self.uploads_dir, self.fixture_maps_dir, self.admin_docs_dir)
