"""Apply pending migrations to data/app.duckdb (run before seed_rules.py)."""

from pathlib import Path
import duckdb
from website.database import run_migrations

db_path = Path("data/app.duckdb")
con = duckdb.connect(str(db_path))
run_migrations(con)
con.close()
print("Migrations applied.")
