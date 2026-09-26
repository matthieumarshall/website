"""Typed helpers that turn DuckDB query results into pydantic models.

Column names in the SELECT (use ``AS`` aliases where needed) must match the
target model's field names.
"""

from collections.abc import Sequence
from typing import TypeVar

import duckdb
from pydantic import BaseModel

from website.db import Connection

# Raised on unique/foreign-key violations; services catch this, not duckdb.
IntegrityError = duckdb.ConstraintException

ModelT = TypeVar("ModelT", bound=BaseModel)
SqlParam = str | int | float | bool | None | object
Params = Sequence[SqlParam]


def _columns(db: Connection) -> list[str]:
    description = db.description or []
    return [column[0] for column in description]


def fetch_one(
    db: Connection, model: type[ModelT], sql: str, params: Params = ()
) -> ModelT | None:
    """Run *sql* and return the first row as *model*, or None."""
    row = db.execute(sql, list(params)).fetchone()
    if row is None:
        return None
    return model.model_validate(dict(zip(_columns(db), row, strict=True)))


def fetch_all(
    db: Connection, model: type[ModelT], sql: str, params: Params = ()
) -> list[ModelT]:
    """Run *sql* and return every row as *model*."""
    rows = db.execute(sql, list(params)).fetchall()
    columns = _columns(db)
    return [model.model_validate(dict(zip(columns, row, strict=True))) for row in rows]


def fetch_value(db: Connection, sql: str, params: Params = ()) -> object:
    """Run *sql* and return the first column of the first row, or None."""
    row = db.execute(sql, list(params)).fetchone()
    return row[0] if row else None


def fetch_count(db: Connection, sql: str, params: Params = ()) -> int:
    """Run a ``SELECT COUNT(...)`` query and return the count."""
    value = fetch_value(db, sql, params)
    return int(value) if isinstance(value, int) else 0


def require(value: ModelT | None, what: str) -> ModelT:
    """Return *value*, failing loudly if a row that was just written is missing.

    Raises:
        RuntimeError: If *value* is None.
    """
    if value is None:
        raise RuntimeError(f"Failed to load created {what}")
    return value
