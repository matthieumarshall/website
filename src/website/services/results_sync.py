"""Service for synchronising race results from Tempo Events / RaceTec into DuckDB."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict
from pyresults import get_valid_category_codes

from website import repository
from website.db import Connection
from website.errors import NotFoundError
from website.integrations.racetec import (
    RaceTecScrapeError,
    parse_csv_results,
    scrape_racetec_results,
)
from website.models import Fixture, ParsedRaceWithResults
from website.services.standings_calculator import recalculate_standings

_logger = logging.getLogger(__name__)

# Maximum hours allowed for automated polling per session (enforces 24h ceiling)
MAX_AUTO_SYNC_HOURS = 24


def _as_utc(dt_val: datetime | None) -> datetime | None:
    """Normalize a datetime (which may be naive from DuckDB) to UTC."""
    if dt_val is None:
        return None
    if dt_val.tzinfo is None:
        return dt_val.astimezone(UTC)
    return dt_val.astimezone(UTC)


_CATEGORY_NAME_MAP: dict[str, str] = {
    "senior men": "SM",
    "senior women": "SW",
    "u20 men": "U20M",
    "u20 women": "U20W",
    "u9 boys": "U9B",
    "u9 girls": "U9G",
    "u11 boys": "U11B",
    "u11 girls": "U11G",
    "u13 boys": "U13B",
    "u13 girls": "U13G",
    "u15 boys": "U15B",
    "u15 girls": "U15G",
    "u17 boys": "U17M",
    "u17 girls": "U17W",
    "u17 men": "U17M",
    "u17 women": "U17W",
}

_GENDER_CATEGORY_MAP: dict[tuple[str, str], str] = {
    ("male", "v40"): "MV40",
    ("female", "v40"): "WV40",
    ("male", "v50"): "MV50",
    ("female", "v50"): "WV50",
    ("male", "v60"): "MV60",
    ("female", "v60"): "WV60",
    ("male", "v70"): "MV70",
    ("female", "v70"): "WV70",
    ("male", "v70+"): "MV70",
    ("female", "v70+"): "WV70",
    ("male", "senior men"): "SM",
    ("female", "senior women"): "SW",
}


def normalise_category(raw_category: str, gender: str) -> str:
    """Normalise a raw category string to a pyresults category code."""
    valid = get_valid_category_codes()
    stripped = raw_category.strip()
    upper = stripped.upper()

    for code in valid:
        if str(code).upper() == upper:
            return str(code)

    cat_lower = stripped.lower()
    cat_compact = cat_lower.replace(" ", "")

    g_lower = gender.strip().lower()
    if g_lower in ("m", "male", "men"):
        gender_key = "male"
    elif g_lower in ("f", "female", "women"):
        gender_key = "female"
    else:
        gender_key = g_lower

    mapped = _GENDER_CATEGORY_MAP.get(
        (gender_key, cat_lower)
    ) or _GENDER_CATEGORY_MAP.get((gender_key, cat_compact))
    if mapped:
        return mapped

    name_mapped = _CATEGORY_NAME_MAP.get(cat_lower)
    if name_mapped:
        return name_mapped

    return stripped


class SyncSummary(BaseModel):
    """Outcome of a race results synchronisation operation."""

    model_config = ConfigDict(frozen=True)

    fixture_id: int
    races_synced: int
    finishers_synced: int
    races: list[str]
    success: bool
    error: str | None = None


class ResultsSyncService:
    """Synchronises results from RaceTec/Tempo Events and recalculates standings."""

    def __init__(self, db: Connection) -> None:
        """Bind service to a database connection."""
        self._db = db

    def update_sync_settings(
        self,
        fixture_id: int,
        tempo_results_url: str | None,
        auto_sync_enabled: bool,
        auto_sync_hours: int = 24,
        auto_sync_interval_minutes: int = 15,
    ) -> Fixture:
        """Update auto-sync settings, capping window at 24 hours."""
        fixture = repository.get_fixture_by_id(self._db, fixture_id)
        if not fixture:
            raise NotFoundError(f"Fixture {fixture_id} not found")

        # Clamp auto_sync_hours between 1 and 24
        hours = max(1, min(auto_sync_hours, MAX_AUTO_SYNC_HOURS))
        clean_url = tempo_results_url.strip() if tempo_results_url else None
        interval = max(5, min(auto_sync_interval_minutes, 1440))

        auto_sync_until = (
            datetime.now(UTC) + timedelta(hours=hours) if auto_sync_enabled else None
        )

        updated = repository.update_fixture_sync_settings(
            self._db,
            fixture_id=fixture_id,
            tempo_results_url=clean_url,
            auto_sync_enabled=auto_sync_enabled,
            auto_sync_until=auto_sync_until,
            auto_sync_interval_minutes=interval,
        )
        if not updated:
            raise NotFoundError(f"Fixture {fixture_id} not found")
        return updated

    def ingest_parsed_races(
        self,
        fixture: Fixture,
        parsed_races: list[ParsedRaceWithResults],
    ) -> SyncSummary:
        """Persist parsed races and results in a transaction and update standings."""
        now = datetime.now(UTC)
        until_utc = _as_utc(fixture.auto_sync_until)
        auto_sync_expired = until_utc is not None and now > until_utc
        repository.update_fixture_sync_status(
            self._db,
            fixture_id=fixture.id,
            sync_status="syncing",
            sync_error=None,
            last_sync_attempt_at=now,
        )

        races_with_results = [race for race in parsed_races if race.results]
        if not races_with_results:
            error = "No finisher results were found; existing results were not changed."
            repository.update_fixture_sync_status(
                self._db,
                fixture_id=fixture.id,
                sync_status="error",
                sync_error=error,
            )
            return SyncSummary(
                fixture_id=fixture.id,
                races_synced=0,
                finishers_synced=0,
                races=[],
                success=False,
                error=error,
            )

        self._db.execute("BEGIN")
        try:
            total_finishers = 0
            race_names: list[str] = []

            for pr in races_with_results:
                race = repository.get_race_by_name(self._db, fixture.id, pr.race_name)
                if not race:
                    race = repository.create_race(
                        self._db, fixture_id=fixture.id, name=pr.race_name
                    )

                repository.delete_results_for_race(self._db, race.id)

                batch_rows: list[
                    tuple[
                        int,
                        int,
                        int | None,
                        str,
                        str,
                        str,
                        int | None,
                        str,
                        int | None,
                        str | None,
                    ]
                ] = [
                    (
                        race.id,
                        r.position,
                        r.race_number,
                        r.athlete_name,
                        r.time,
                        normalise_category(r.category, r.gender),
                        r.category_position,
                        r.gender,
                        r.gender_position,
                        r.club,
                    )
                    for r in pr.results
                ]

                repository.create_results_batch(self._db, batch_rows)
                total_finishers += len(batch_rows)
                race_names.append(pr.race_name)

            repository.update_fixture_sync_status(
                self._db,
                fixture_id=fixture.id,
                sync_status="success",
                sync_error=None,
                last_synced_at=now,
            )

            if auto_sync_expired:
                repository.update_fixture_sync_settings(
                    self._db,
                    fixture_id=fixture.id,
                    tempo_results_url=fixture.tempo_results_url,
                    auto_sync_enabled=False,
                    auto_sync_until=fixture.auto_sync_until,
                    auto_sync_interval_minutes=fixture.auto_sync_interval_minutes,
                )

            self._db.execute("COMMIT")
        except Exception as exc:
            self._db.execute("ROLLBACK")
            _logger.exception("Failed to ingest results for fixture %s", fixture.id)
            repository.update_fixture_sync_status(
                self._db,
                fixture_id=fixture.id,
                sync_status="error",
                sync_error=str(exc),
            )
            return SyncSummary(
                fixture_id=fixture.id,
                races_synced=0,
                finishers_synced=0,
                races=[],
                success=False,
                error=str(exc),
            )

        # Trigger standings recalculation outside the main results transaction
        try:
            recalculate_standings(self._db, fixture.season_id)
        except Exception as exc:  # noqa: BLE001 — non-fatal standings calculation failure
            _logger.warning(
                "Standings recalculation warning for season %s after sync: %s",
                fixture.season_id,
                exc,
            )

        return SyncSummary(
            fixture_id=fixture.id,
            races_synced=len(race_names),
            finishers_synced=total_finishers,
            races=race_names,
            success=True,
        )

    def ingest_csv(
        self,
        fixture_id: int,
        race_name: str,
        csv_content: str,
    ) -> SyncSummary:
        """Parse uploaded CSV content for a single race and ingest results."""
        fixture = repository.get_fixture_by_id(self._db, fixture_id)
        if not fixture:
            raise NotFoundError(f"Fixture {fixture_id} not found")

        parsed_results = parse_csv_results(csv_content)
        if not parsed_results:
            raise ValueError("CSV contains no valid result rows")

        parsed_race = ParsedRaceWithResults(
            race_name=race_name.strip(),
            results=parsed_results,
        )
        return self.ingest_parsed_races(fixture, [parsed_race])

    async def sync_fixture_from_url(
        self,
        fixture_id: int,
        url: str | None = None,
    ) -> SyncSummary:
        """Fetch results from RaceTec/Tempo Events page via Playwright and ingest."""
        fixture = repository.get_fixture_by_id(self._db, fixture_id)
        if not fixture:
            raise NotFoundError(f"Fixture {fixture_id} not found")

        target_url = url or fixture.tempo_results_url
        if not target_url:
            raise ValueError("No results URL provided or configured for this fixture")

        repository.update_fixture_sync_status(
            self._db,
            fixture_id=fixture.id,
            sync_status="syncing",
            sync_error=None,
            last_sync_attempt_at=datetime.now(UTC),
        )

        try:
            parsed_races = await scrape_racetec_results(target_url)
        except RaceTecScrapeError as exc:
            repository.update_fixture_sync_status(
                self._db,
                fixture_id=fixture.id,
                sync_status="error",
                sync_error=str(exc),
            )
            return SyncSummary(
                fixture_id=fixture.id,
                races_synced=0,
                finishers_synced=0,
                races=[],
                success=False,
                error=str(exc),
            )

        return self.ingest_parsed_races(fixture, parsed_races)

    async def check_and_run_due_syncs(self) -> list[SyncSummary]:
        """Poll and execute due synchronisations for all active fixtures."""
        fixtures = repository.list_fixtures_needing_sync(self._db)
        summaries: list[SyncSummary] = []
        now = datetime.now(UTC)

        for fixture in fixtures:
            # Check expiration
            until_utc = _as_utc(fixture.auto_sync_until)
            if until_utc and now > until_utc:
                repository.update_fixture_sync_settings(
                    self._db,
                    fixture_id=fixture.id,
                    tempo_results_url=fixture.tempo_results_url,
                    auto_sync_enabled=False,
                    auto_sync_until=fixture.auto_sync_until,
                    auto_sync_interval_minutes=fixture.auto_sync_interval_minutes,
                )
                continue

            # Check interval
            if fixture.last_sync_attempt_at is not None:
                interval_secs = fixture.auto_sync_interval_minutes * 60
                last_attempt = _as_utc(fixture.last_sync_attempt_at)
                elapsed = (now - last_attempt).total_seconds() if last_attempt else 0
                if elapsed < interval_secs:
                    continue

            summary = await self.sync_fixture_from_url(fixture.id)
            summaries.append(summary)

        return summaries
