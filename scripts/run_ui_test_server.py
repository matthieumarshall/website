"""Bootstrap server used by the Node/@playwright/test accessibility & mobile suite.

Seeds a fresh temp DuckDB file with the same dataset used by the Python
pytest-playwright suite (see tests/ui/seed_data.py), then starts uvicorn in
the foreground. Playwright's `webServer` config invokes this script and waits
for it to respond on the configured URL before running tests/a11y/*.spec.ts.

Run from repo root:
    uv run python scripts/run_ui_test_server.py
"""

import atexit
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "ui"))

import duckdb  # noqa: E402
import uvicorn  # noqa: E402
from seed_data import seed_full_dataset  # noqa: E402

DB_PATH = os.environ.get("UI_TEST_DB_PATH", "test_ui_node.duckdb")
PORT = int(os.environ.get("UI_TEST_SERVER_PORT", "8000"))
SEED_IDS_PATH = REPO_ROOT / "tests" / "a11y" / ".seed-ids.json"


def _cleanup() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


def main() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    atexit.register(_cleanup)

    con = duckdb.connect(DB_PATH)
    seeded = seed_full_dataset(con)
    con.close()

    os.environ["DATABASE_URL"] = DB_PATH
    os.environ["UI_TEST_BATCH_ID"] = str(seeded.entry_batch_id)
    os.environ["UI_TEST_SEASON_ID"] = str(seeded.entries_season_id)

    SEED_IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEED_IDS_PATH.write_text(
        json.dumps(
            {
                "seasonId": seeded.season_id,
                "fixtureId": seeded.fixture_id,
                "entriesSeasonId": seeded.entries_season_id,
                "entryBatchId": seeded.entry_batch_id,
            }
        )
    )

    uvicorn.run("website.main:app", host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
